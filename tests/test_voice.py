"""Voice subsystem with mocked backends (no hardware, no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_agent.config import AgentSettings, VoiceSettings
from memory_agent.core.exceptions import (
    CloudTranscriptionConsentError,
    MicrophoneUnavailableError,
    SpeechSynthesisError,
    TranscriptionError,
)
from memory_agent.security.consent_manager import ConsentManager, ConsentScope
from memory_agent.voice.audio_manager import AudioManager
from memory_agent.voice.speech_to_text import (
    AudioClip,
    DisabledSTT,
    GeminiSTT,
    MockSTT,
)
from memory_agent.voice.text_to_speech import MockTTS, NullTTS


class FakeRecorder:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.recording = False
        self.started = 0

    @property
    def is_available(self) -> bool:
        return self.available

    @property
    def unavailable_reason(self) -> str:
        return "" if self.available else "No microphone detected."

    @property
    def is_recording(self) -> bool:
        return self.recording

    def start(self) -> None:
        if not self.available:
            raise MicrophoneUnavailableError(self.unavailable_reason)
        self.recording = True
        self.started += 1

    def stop(self) -> AudioClip:
        self.recording = False
        return AudioClip(data=b"RIFFfake-wav-bytes", duration_s=1.5)

    def cancel(self) -> None:
        self.recording = False


def _settings(**voice) -> AgentSettings:
    return AgentSettings(voice=VoiceSettings(enabled=True, **voice))


def _manager(tmp_path: Path, *, stt=None, tts=None, recorder=None, settings=None, consent=None):
    consent = consent or ConsentManager(tmp_path / "consent.json")
    return (
        AudioManager(
            settings=settings or _settings(),
            consent=consent,
            stt=stt or MockSTT("Where did I keep my wallet?"),
            tts=tts or MockTTS(),
            recorder=recorder or FakeRecorder(),
        ),
        consent,
    )


def test_mock_transcription_returns_preview_text(tmp_path):
    manager, _ = _manager(tmp_path)
    manager.start_recording()
    assert manager.is_recording is True
    result = manager.stop_and_transcribe()
    assert result.text == "Where did I keep my wallet?"
    assert result.is_cloud is False
    assert manager.is_recording is False


def test_voice_disabled_rejects_recording(tmp_path):
    settings = _settings()
    settings.voice.enabled = False
    manager, _ = _manager(tmp_path, settings=settings)
    with pytest.raises(MicrophoneUnavailableError):
        manager.start_recording()


def test_missing_microphone_is_reported(tmp_path):
    manager, _ = _manager(tmp_path, recorder=FakeRecorder(available=False))
    with pytest.raises(MicrophoneUnavailableError):
        manager.start_recording()
    status = manager.status()
    assert status["recording_available"] is False
    assert status["recording_reason"]


def test_cloud_transcription_requires_consent(tmp_path):
    consent = ConsentManager(tmp_path / "consent.json")
    manager, _ = _manager(
        tmp_path,
        stt=GeminiSTT("not-a-real-key"),
        consent=consent,
    )
    with pytest.raises(CloudTranscriptionConsentError):
        manager.start_recording()

    clip = AudioClip(data=b"bytes", duration_s=1.0)
    with pytest.raises(CloudTranscriptionConsentError):
        manager.transcribe(clip)


def test_cloud_transcription_allowed_after_consent_but_no_network_in_test(tmp_path):
    consent = ConsentManager(tmp_path / "consent.json")
    consent.grant(ConsentScope.CLOUD_TRANSCRIPTION, categories=["audio"])
    stt = GeminiSTT("not-a-real-key")
    manager, _ = _manager(tmp_path, stt=stt, consent=consent)
    # Consent is granted, so recording is allowed; transcription would use the
    # network and is covered by the skipped live tests instead.
    manager.start_recording()
    assert manager.is_recording is True


def test_disabled_stt_reports_reason(tmp_path):
    manager, _ = _manager(tmp_path, stt=DisabledSTT())
    with pytest.raises(TranscriptionError):
        manager.transcribe(AudioClip(data=b"x", duration_s=0.5))
    assert manager.status()["stt_available"] is False


def test_tts_disabled_raises_clear_error(tmp_path):
    manager, _ = _manager(tmp_path, tts=NullTTS("Spoken answers are off."), settings=_settings(speak_responses=True))
    with pytest.raises(SpeechSynthesisError):
        manager.speak("Hello")
    manager.set_tts(MockTTS())
    manager.speak("Hello")
    assert manager.tts.spoken == ["Hello"]


def test_status_reports_backends_and_consent(tmp_path):
    manager, _ = _manager(tmp_path)
    status = manager.status()
    assert status["voice_enabled"] is True
    assert status["stt_backend"] == "mock"
    assert status["tts_backend"] == "mock"
    assert status["cloud_consent"] is False


def test_audio_is_not_written_to_disk(tmp_path):
    manager, _ = _manager(tmp_path)
    manager.start_recording()
    manager.stop_and_transcribe()
    files = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert files == []


def test_streaming_clip_type_is_in_memory_bytes():
    clip = AudioClip(data=b"abc")
    assert isinstance(clip.data, bytes)
    assert clip.size_kb() >= 0
