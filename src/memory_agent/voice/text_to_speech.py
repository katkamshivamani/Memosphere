"""Text-to-speech interfaces and backends (optional dependencies)."""

from __future__ import annotations

import abc
import logging

from memory_agent.core.exceptions import SpeechSynthesisError

logger = logging.getLogger("memory_agent.voice.tts")


class TextToSpeech(abc.ABC):
    name: str = "unknown"

    @property
    @abc.abstractmethod
    def is_available(self) -> bool: ...

    @property
    @abc.abstractmethod
    def unavailable_reason(self) -> str: ...

    @abc.abstractmethod
    def speak(self, text: str) -> None:
        """Blocking speech. Call from a worker thread, never the GUI thread."""

    def stop(self) -> None:
        """Stop speaking if possible."""


class NullTTS(TextToSpeech):
    """No speech output; reports why instead of failing silently."""

    name = "disabled"

    def __init__(self, reason: str = "Spoken answers are turned off.") -> None:
        self._reason = reason

    @property
    def is_available(self) -> bool:
        return False

    @property
    def unavailable_reason(self) -> str:
        return self._reason

    def speak(self, text: str) -> None:
        raise SpeechSynthesisError(self._reason)


class MockTTS(TextToSpeech):
    """Records what would have been spoken (tests/UI development)."""

    name = "mock"

    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.stopped = False

    @property
    def is_available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str:
        return ""

    def speak(self, text: str) -> None:
        self.spoken.append(text)

    def stop(self) -> None:
        self.stopped = True


class WindowsSapiTTS(TextToSpeech):
    """Windows SAPI speech via the optional ``pyttsx3`` package.

    The engine is created lazily inside the worker thread that speaks, because
    COM objects are thread-affine.  Hardware playback is not verified by the
    automated test suite.
    """

    name = "sapi"

    def __init__(self) -> None:
        self._engine = None

    @property
    def is_available(self) -> bool:
        try:
            import pyttsx3  # noqa: F401
        except ImportError:
            return False
        return True

    @property
    def unavailable_reason(self) -> str:
        if self.is_available:
            return ""
        return (
            "Spoken answers require the optional pyttsx3 package "
            "(pip install -r requirements-voice.txt)."
        )

    def speak(self, text: str) -> None:
        if not text.strip():
            return
        try:
            import pyttsx3
        except ImportError as exc:
            raise SpeechSynthesisError(self.unavailable_reason) from exc
        try:
            if self._engine is None:
                self._engine = pyttsx3.init()
                self._engine.setProperty("rate", 165)
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception as exc:
            logger.warning("Speech synthesis failed: %s", type(exc).__name__)
            raise SpeechSynthesisError("The answer could not be read aloud.") from exc

    def stop(self) -> None:
        try:
            if self._engine is not None:
                self._engine.stop()
        except Exception:
            pass


def create_default_tts(enabled: bool) -> TextToSpeech:
    """Pick an available local TTS backend, or a clearly-unavailable one."""
    if not enabled:
        return NullTTS("Spoken answers are turned off in Assistant settings.")
    candidate = WindowsSapiTTS()
    if candidate.is_available:
        return candidate
    return NullTTS(candidate.unavailable_reason)
