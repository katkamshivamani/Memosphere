"""Speech-to-text interfaces and backends.

Audio is only captured after the user presses the microphone button, is held in
memory, and is discarded after transcription.  Cloud transcription is opt-in and
requires recorded consent (enforced by :class:`AudioManager`).
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, ConfigDict

from memory_agent.core.exceptions import (
    MissingApiKeyError,
    TranscriptionError,
)

logger = logging.getLogger("memory_agent.voice.stt")


@dataclass
class AudioClip:
    """In-memory audio. Never written to disk by default."""

    data: bytes
    mime_type: str = "audio/wav"
    sample_rate: int = 16000
    duration_s: float = 0.0

    def size_kb(self) -> float:
        return round(len(self.data) / 1024, 1)


class TranscriptionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    backend: str
    is_cloud: bool = False
    duration_s: float = 0.0


class SpeechToText(abc.ABC):
    name: str = "unknown"
    requires_cloud: bool = False

    @property
    @abc.abstractmethod
    def is_available(self) -> bool: ...

    @property
    @abc.abstractmethod
    def unavailable_reason(self) -> str: ...

    @abc.abstractmethod
    def transcribe(self, clip: AudioClip) -> TranscriptionResult: ...


class DisabledSTT(SpeechToText):
    """Explicitly disabled backend. Reports why instead of pretending to work."""

    name = "disabled"
    requires_cloud = False

    @property
    def is_available(self) -> bool:
        return False

    @property
    def unavailable_reason(self) -> str:
        return "Speech recognition is turned off in Assistant settings."

    def transcribe(self, clip: AudioClip) -> TranscriptionResult:
        raise TranscriptionError(self.unavailable_reason)


class MockSTT(SpeechToText):
    """Deterministic backend for tests and UI development."""

    name = "mock"
    requires_cloud = False

    def __init__(self, text: str = "Where did I keep my wallet?") -> None:
        self.text = text
        self.calls: list[AudioClip] = []

    @property
    def is_available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str:
        return ""

    def transcribe(self, clip: AudioClip) -> TranscriptionResult:
        self.calls.append(clip)
        return TranscriptionResult(
            text=self.text, backend=self.name, is_cloud=False, duration_s=clip.duration_s
        )


class GeminiSTT(SpeechToText):
    """Cloud transcription through Gemini.

    Requires an API key and explicit consent; the AudioManager refuses to call
    this backend without both.  The model id is configurable - no model id is
    assumed to be permanently current.
    """

    name = "gemini"
    requires_cloud = True

    def __init__(
        self,
        api_key: Optional[str],
        *,
        model: str = "gemini-2.5-flash",
        prompt: str = (
            "Transcribe this audio exactly as spoken. Return only the transcription "
            "text, without commentary."
        ),
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._prompt = prompt

    @property
    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import google.genai  # noqa: F401
        except ImportError:
            return False
        return True

    @property
    def unavailable_reason(self) -> str:
        if not self._api_key:
            return "A Gemini API key is required for cloud transcription."
        try:
            import google.genai  # noqa: F401
        except ImportError:
            return "The Gemini SDK is not installed."
        return ""

    def transcribe(self, clip: AudioClip) -> TranscriptionResult:
        if not self._api_key:
            raise MissingApiKeyError("Gemini transcription requires an API key.")
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise TranscriptionError(f"Gemini SDK unavailable: {exc}") from exc

        try:
            client = genai.Client(api_key=self._api_key)
            response = client.models.generate_content(
                model=self._model,
                contents=[
                    types.Part.from_bytes(data=clip.data, mime_type=clip.mime_type),
                    self._prompt,
                ],
                config=types.GenerateContentConfig(temperature=0.0),
            )
            text = (getattr(response, "text", None) or "").strip()
        except Exception as exc:
            logger.warning("Gemini transcription failed: %s", type(exc).__name__)
            raise TranscriptionError(
                "The cloud transcription service could not process the recording."
            ) from exc

        if not text:
            raise TranscriptionError("No speech was recognised in the recording.")
        return TranscriptionResult(
            text=text, backend=self.name, is_cloud=True, duration_s=clip.duration_s
        )


class LocalWhisperSTT(SpeechToText):
    """Optional local transcription via faster-whisper (offline)."""

    name = "whisper"
    requires_cloud = False

    def __init__(self, model_size: str = "base") -> None:
        self._model_size = model_size
        self._model = None
        self._import_error: Optional[str] = None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            self._import_error = str(exc)
            raise TranscriptionError(
                "Local speech recognition requires the optional faster-whisper package. "
                "Install requirements-voice.txt or use cloud transcription."
            ) from exc
        self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
        return self._model

    @property
    def is_available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False
        return True

    @property
    def unavailable_reason(self) -> str:
        if self.is_available:
            return ""
        return (
            "Local transcription requires the optional faster-whisper package "
            "(pip install faster-whisper)."
        )

    def transcribe(self, clip: AudioClip) -> TranscriptionResult:
        import io
        import wave

        model = self._ensure_model()
        try:
            with wave.open(io.BytesIO(clip.data), "rb") as handle:
                frames = handle.readframes(handle.getnframes())
                sample_rate = handle.getframerate()
            import numpy as np

            audio = np.frombuffer(frames, dtype=np.int16).astype("float32") / 32768.0
            segments, _info = model.transcribe(audio, language=None, vad_filter=True)
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:
            logger.warning("Local transcription failed: %s", type(exc).__name__)
            raise TranscriptionError("Local transcription failed.") from exc
        if not text:
            raise TranscriptionError("No speech was recognised in the recording.")
        return TranscriptionResult(
            text=text, backend=self.name, is_cloud=False, duration_s=clip.duration_s
        )
