"""Audio capture and the voice subsystem coordinator.

Privacy rules implemented here:

* recording starts only on an explicit ``start_recording()`` call (the UI
  microphone button);
* audio is kept in memory as a byte string and discarded after transcription;
* cloud transcription requires both an API key and recorded user consent;
* failures are surfaced with actionable messages, never silent fallbacks.
"""

from __future__ import annotations

import io
import logging
import threading
import time
import wave
from typing import Optional, Protocol

from memory_agent.config import AgentSettings, VoiceSettings
from memory_agent.core.exceptions import (
    CloudTranscriptionConsentError,
    MicrophoneUnavailableError,
    RecordingError,
    SpeechSynthesisError,
    TranscriptionError,
)
from memory_agent.security.consent_manager import ConsentManager, ConsentScope
from memory_agent.voice.speech_to_text import (
    AudioClip,
    DisabledSTT,
    GeminiSTT,
    LocalWhisperSTT,
    SpeechToText,
    TranscriptionResult,
)
from memory_agent.voice.text_to_speech import TextToSpeech, create_default_tts

logger = logging.getLogger("memory_agent.voice")


class AudioRecorder(Protocol):
    def start(self) -> None: ...
    def stop(self) -> AudioClip: ...
    @property
    def is_recording(self) -> bool: ...
    @property
    def is_available(self) -> bool: ...
    @property
    def unavailable_reason(self) -> str: ...


class SoundDeviceRecorder:
    """Microphone capture via the optional ``sounddevice`` package."""

    def __init__(self, *, sample_rate: int = 16000, max_seconds: int = 60) -> None:
        self._sample_rate = sample_rate
        self._max_seconds = max_seconds
        self._stream = None
        self._chunks: list[bytes] = []
        self._lock = threading.Lock()
        self._started_at = 0.0
        self._recording = False

    @property
    def is_available(self) -> bool:
        try:
            import sounddevice  # noqa: F401
        except ImportError:
            return False
        try:
            import sounddevice as sd

            return sd.query_devices(kind="input") is not None
        except Exception:
            return False

    @property
    def unavailable_reason(self) -> str:
        try:
            import sounddevice  # noqa: F401
        except ImportError:
            return (
                "Microphone support requires the optional sounddevice package "
                "(pip install -r requirements-voice.txt)."
            )
        return "No input microphone was detected, or microphone permission was denied."

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        if self._recording:
            return
        if not self.is_available:
            raise MicrophoneUnavailableError(self.unavailable_reason)
        import sounddevice as sd

        self._chunks = []
        self._started_at = time.monotonic()
        try:
            self._stream = sd.RawInputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:
            self._stream = None
            raise MicrophoneUnavailableError(
                f"Could not open the microphone: {type(exc).__name__}"
            ) from exc
        self._recording = True

    def _callback(self, indata, frames, time_info, status) -> None:  # pragma: no cover - hardware
        if status:
            logger.warning("Audio stream status: %s", status)
        with self._lock:
            self._chunks.append(bytes(indata))
        if time.monotonic() - self._started_at > self._max_seconds:
            # Hard stop; the UI also enforces the limit.
            try:
                self.stop()
            except Exception:
                pass

    def stop(self) -> AudioClip:
        if not self._recording:
            raise RecordingError("No recording is in progress.")
        self._recording = False
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        finally:
            self._stream = None
        with self._lock:
            raw = b"".join(self._chunks)
            self._chunks = []
        duration = time.monotonic() - self._started_at
        if not raw:
            raise RecordingError("The microphone did not capture any audio.")
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(self._sample_rate)
            handle.writeframes(raw)
        return AudioClip(
            data=buffer.getvalue(),
            mime_type="audio/wav",
            sample_rate=self._sample_rate,
            duration_s=round(duration, 2),
        )

    def cancel(self) -> None:
        self._recording = False
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None
        with self._lock:
            self._chunks = []


class AudioManager:
    """Coordinates recording, transcription and speech output."""

    def __init__(
        self,
        *,
        settings: AgentSettings,
        consent: ConsentManager,
        stt: Optional[SpeechToText] = None,
        tts: Optional[TextToSpeech] = None,
        recorder: Optional[AudioRecorder] = None,
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
    ) -> None:
        self._settings = settings
        self._consent = consent
        self._recorder = recorder or SoundDeviceRecorder(
            max_seconds=settings.voice.max_recording_seconds
        )
        self._stt = stt or self._build_stt(settings.voice, gemini_api_key, gemini_model)
        self._tts = tts or create_default_tts(settings.voice.speak_responses)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Backend selection
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_stt(
        voice: VoiceSettings, api_key: Optional[str], model: Optional[str]
    ) -> SpeechToText:
        if not voice.enabled:
            return DisabledSTT()
        if voice.stt_backend == "local":
            return LocalWhisperSTT()
        if voice.stt_backend == "gemini":
            return GeminiSTT(api_key, model=model or "gemini-2.5-flash")
        # auto: prefer local, then cloud (cloud still consent-gated at call time)
        local = LocalWhisperSTT()
        if local.is_available:
            return local
        if api_key and voice.cloud_transcription_allowed:
            return GeminiSTT(api_key, model=model or "gemini-2.5-flash")
        return DisabledSTT()

    def update_settings(self, settings: AgentSettings) -> None:
        self._settings = settings
        self._tts = create_default_tts(settings.voice.speak_responses)

    def set_stt(self, stt: SpeechToText) -> None:
        self._stt = stt

    def set_tts(self, tts: TextToSpeech) -> None:
        self._tts = tts

    # ------------------------------------------------------------------ #
    # Status
    # ------------------------------------------------------------------ #
    @property
    def stt(self) -> SpeechToText:
        return self._stt

    @property
    def tts(self) -> TextToSpeech:
        return self._tts

    @property
    def recorder(self) -> AudioRecorder:
        return self._recorder

    def status(self) -> dict:
        return {
            "voice_enabled": self._settings.voice.enabled,
            "recording_available": self._recorder.is_available,
            "recording_reason": self._recorder.unavailable_reason,
            "stt_backend": self._stt.name,
            "stt_available": self._stt.is_available,
            "stt_reason": self._stt.unavailable_reason,
            "stt_is_cloud": self._stt.requires_cloud,
            "cloud_consent": self._consent.is_granted(ConsentScope.CLOUD_TRANSCRIPTION),
            "tts_backend": self._tts.name,
            "tts_available": self._tts.is_available,
            "tts_reason": self._tts.unavailable_reason,
        }

    # ------------------------------------------------------------------ #
    # Recording / transcription
    # ------------------------------------------------------------------ #
    @property
    def is_recording(self) -> bool:
        return self._recorder.is_recording

    def start_recording(self) -> None:
        if not self._settings.voice.enabled:
            raise MicrophoneUnavailableError(
                "Voice input is turned off in Assistant settings."
            )
        if self._stt.requires_cloud and not self._consent.is_granted(
            ConsentScope.CLOUD_TRANSCRIPTION
        ):
            raise CloudTranscriptionConsentError(
                "Cloud transcription consent is required before recording with a cloud backend."
            )
        self._recorder.start()

    def stop_recording(self) -> AudioClip:
        return self._recorder.stop()

    def transcribe(self, clip: AudioClip) -> TranscriptionResult:
        """Transcribe an in-memory clip; consent is re-checked at call time."""
        if not self._stt.is_available:
            raise TranscriptionError(self._stt.unavailable_reason)
        if self._stt.requires_cloud and not self._consent.is_granted(
            ConsentScope.CLOUD_TRANSCRIPTION
        ):
            raise CloudTranscriptionConsentError(
                "Cloud transcription requires explicit consent in Assistant settings."
            )
        with self._lock:
            result = self._stt.transcribe(clip)
        logger.info("Transcribed audio backend=%s cloud=%s", result.backend, result.is_cloud)
        return result

    def stop_and_transcribe(self) -> TranscriptionResult:
        clip = self.stop_recording()
        return self.transcribe(clip)

    def cancel_recording(self) -> None:
        cancel = getattr(self._recorder, "cancel", None)
        if callable(cancel):
            cancel()

    # ------------------------------------------------------------------ #
    # Speech output
    # ------------------------------------------------------------------ #
    def speak(self, text: str) -> None:
        if not self._settings.voice.speak_responses:
            raise SpeechSynthesisError("Spoken answers are turned off in Assistant settings.")
        if not self._tts.is_available:
            raise SpeechSynthesisError(self._tts.unavailable_reason)
        self._tts.speak(text)

    def stop_speaking(self) -> None:
        try:
            self._tts.stop()
        except Exception:
            pass
