"""Qt worker plumbing: all network, audio and long-running work off the GUI thread.

Pattern: :class:`FunctionWorker` (QRunnable) runs a callable in the global
QThreadPool and emits results through a QObject signal holder.  Cancellation is
cooperative via the agent's :class:`CancellationToken`.
"""

from __future__ import annotations

import logging
import traceback
from typing import Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from memory_agent.core.exceptions import AgentError, ResponseCancelledError
from memory_agent.core.orchestrator import CancellationToken
from memory_agent.services.agent_service import ChatOutcome
from memory_agent.voice.audio_manager import AudioManager

logger = logging.getLogger("memory_agent.ui.workers")


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(object)
    started = Signal()


class FunctionWorker(QRunnable):
    """Runs ``fn(*args, **kwargs)`` in the global thread pool."""

    def __init__(
        self,
        fn: Callable,
        *args,
        cancel_token: Optional[CancellationToken] = None,
        **kwargs,
    ) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._token = cancel_token
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        self.signals.started.emit()
        try:
            if self._token is not None:
                self._token.check()
            result = self._fn(*self._args, **self._kwargs)
            if self._token is not None:
                self._token.check()
            self.signals.finished.emit(result)
        except ResponseCancelledError:
            self.signals.failed.emit(ResponseCancelledError("Cancelled"))
        except AgentError as exc:
            self.signals.failed.emit(exc)
        except Exception as exc:
            logger.error("Unhandled worker error: %s", type(exc).__name__)
            logger.debug("Worker traceback: %s", traceback.format_exc())
            self.signals.failed.emit(exc)


class ChatController(QObject):
    """Bridges :class:`AgentService` and the chat widgets."""

    started = Signal()
    finished = Signal(object)  # ChatOutcome
    failed = Signal(object)  # AgentError or Exception
    transcription_ready = Signal(object)  # TranscriptionResult
    transcription_failed = Signal(object)
    recording_started = Signal()
    recording_stopped = Signal()
    speech_failed = Signal(object)

    def __init__(
        self,
        *,
        service,
        audio: AudioManager,
        user_id: str,
        pool: Optional[QThreadPool] = None,
    ) -> None:
        super().__init__()
        self._service = service
        self._audio = audio
        self._user_id = user_id
        self._pool = pool or QThreadPool.globalInstance()
        self._token: Optional[CancellationToken] = None
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def audio(self) -> AudioManager:
        return self._audio

    def set_audio(self, audio: AudioManager) -> None:
        self._audio = audio

    # ------------------------------------------------------------------ #
    # Chat
    # ------------------------------------------------------------------ #
    def send(self, text: str, conversation_id: Optional[str] = None) -> None:
        if self._busy:
            return
        self._busy = True
        self._token = CancellationToken()
        self.started.emit()
        worker = FunctionWorker(
            self._service.send_message,
            user_id=self._user_id,
            text=text,
            conversation_id=conversation_id,
            token=self._token,
            cancel_token=self._token,
        )
        worker.signals.finished.connect(self._on_finished)
        worker.signals.failed.connect(self._on_failed)
        self._pool.start(worker)

    def cancel(self) -> None:
        if self._token is not None:
            self._token.cancel()

    def _on_finished(self, outcome: ChatOutcome) -> None:
        self._busy = False
        self.finished.emit(outcome)

    def _on_failed(self, error: object) -> None:
        self._busy = False
        self.failed.emit(error)

    # ------------------------------------------------------------------ #
    # Voice
    # ------------------------------------------------------------------ #
    def start_recording(self) -> None:
        try:
            self._audio.start_recording()
            self.recording_started.emit()
        except AgentError as exc:
            self.transcription_failed.emit(exc)

    def stop_recording(self) -> None:
        try:
            clip = self._audio.stop_recording()
            self.recording_stopped.emit()
        except AgentError as exc:
            self.transcription_failed.emit(exc)
            return
        worker = FunctionWorker(self._audio.transcribe, clip)
        worker.signals.finished.connect(self.transcription_ready.emit)
        worker.signals.failed.connect(self.transcription_failed.emit)
        self._pool.start(worker)

    def cancel_recording(self) -> None:
        self._audio.cancel_recording()
        self.recording_stopped.emit()

    def speak(self, text: str) -> None:
        worker = FunctionWorker(self._audio.speak, text)
        worker.signals.failed.connect(self.speech_failed.emit)
        self._pool.start(worker)

    def stop_speaking(self) -> None:
        self._audio.stop_speaking()
