"""Assistant page: chat window plus its worker-backed controller."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QVBoxLayout, QWidget

from memory_agent.config import ContextMode
from memory_agent.ui.chat_window import ChatWindow
from memory_agent.ui.workers import ChatController
from memory_agent.voice.audio_manager import AudioManager


class AssistantPage(QWidget):
    def __init__(
        self,
        *,
        ctx,
        user_id: str,
        audio: AudioManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._user_id = user_id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)

        self.controller = ChatController(
            service=ctx.agent_runtime.service,
            audio=audio,
            user_id=user_id,
        )
        self.chat = ChatWindow(
            controller=self.controller,
            service=ctx.agent_runtime.service,
            user_id=user_id,
        )
        layout.addWidget(self.chat)
        self.refresh_status()

    def refresh_status(self) -> None:
        settings = self._ctx.agent_runtime.service.settings()
        if not settings.enabled:
            self.chat.set_context_status("Assistant is turned off")
            return
        mode = settings.context_mode
        if mode is ContextMode.LOCAL_ONLY:
            label = "Local only · nothing leaves this computer"
        elif mode is ContextMode.FULL_AUTHORIZED:
            label = "Full context (consent granted)"
        else:
            label = "Minimal context"
        self.chat.set_context_status(f"{label} · {settings.provider_id}")

    def set_audio(self, audio: AudioManager) -> None:
        self.controller.set_audio(audio)
        self.chat.refresh_voice()
