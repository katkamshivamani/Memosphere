"""The assistant chat interface."""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from memory_agent.core.exceptions import AgentError, ResponseCancelledError
from memory_agent.core.orchestrator import AgentTurnResult
from memory_agent.models.suggestion import Suggestion
from memory_agent.services.agent_service import ChatOutcome
from memory_agent.ui.chat_message import EmptyState, MessageBubble, TypingIndicator
from memory_agent.ui.suggestion_card import SuggestionCard
from memory_agent.ui.voice_controls import VoiceControls
from memory_agent.ui.workers import ChatController

logger = logging.getLogger("memory_agent.ui.chat")


class ErrorBanner(QFrame):
    dismissed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty("banner", True)
        self.setProperty("error", True)
        self.setVisible(False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 8)
        self._label = QLabel("")
        self._label.setWordWrap(True)
        layout.addWidget(self._label, 1)
        close = QPushButton("Dismiss")
        close.setProperty("flat", True)
        close.clicked.connect(self._dismiss)
        layout.addWidget(close)

    def show_message(self, text: str) -> None:
        self._label.setText(text)
        self.setVisible(True)

    def _dismiss(self) -> None:
        self.setVisible(False)
        self.dismissed.emit()


class ChatWindow(QWidget):
    conversation_changed = Signal(str)
    suggestions_changed = Signal()

    def __init__(
        self,
        *,
        controller: ChatController,
        service,
        user_id: str,
        conversation_id: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._service = service
        self._user_id = user_id
        self._conversation_id = conversation_id
        self._typing: Optional[TypingIndicator] = None
        self._suggestion_cards: dict[str, SuggestionCard] = {}
        self._pending_text = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # Header ------------------------------------------------------- #
        header = QHBoxLayout()
        title = QLabel("Personal Memory Assistant")
        title.setProperty("h2", True)
        header.addWidget(title)
        header.addStretch(1)
        self._status_label = QLabel("")
        self._status_label.setProperty("muted", True)
        header.addWidget(self._status_label)
        self._new_chat_button = QPushButton("New chat")
        self._new_chat_button.setProperty("flat", True)
        self._new_chat_button.clicked.connect(self.start_new_conversation)
        header.addWidget(self._new_chat_button)
        root.addLayout(header)

        # Messages ----------------------------------------------------- #
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._messages_host = QWidget()
        self._messages_layout = QVBoxLayout(self._messages_host)
        self._messages_layout.setContentsMargins(4, 4, 8, 4)
        self._messages_layout.setSpacing(10)
        self._messages_layout.addStretch(1)
        self._scroll.setWidget(self._messages_host)
        root.addWidget(self._scroll, 1)

        self._empty_state = EmptyState(self._messages_host)
        self._messages_layout.insertWidget(0, self._empty_state)

        # Suggestions -------------------------------------------------- #
        self._suggestions_host = QWidget()
        self._suggestions_layout = QVBoxLayout(self._suggestions_host)
        self._suggestions_layout.setContentsMargins(4, 0, 8, 4)
        self._suggestions_layout.setSpacing(8)
        self._suggestions_host.setVisible(False)
        root.addWidget(self._suggestions_host)

        # Errors ------------------------------------------------------- #
        self._error = ErrorBanner(self)
        root.addWidget(self._error)

        # Voice -------------------------------------------------------- #
        self._voice = VoiceControls(self)
        root.addWidget(self._voice)
        self._configure_voice()

        # Composer ----------------------------------------------------- #
        composer = QFrame()
        composer.setProperty("composer", True)
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(10, 8, 10, 8)
        composer_layout.setSpacing(8)
        self._input = QPlainTextEdit()
        self._input.setPlaceholderText("Ask about your memories…")
        self._input.setFixedHeight(64)
        self._input.installEventFilter(self)
        composer_layout.addWidget(self._input, 1)

        actions = QVBoxLayout()
        actions.setSpacing(6)
        self._send_button = QPushButton("Send")
        self._send_button.setProperty("primary", True)
        self._send_button.clicked.connect(self._send_current)
        actions.addWidget(self._send_button)
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setVisible(False)
        self._cancel_button.clicked.connect(self._cancel)
        actions.addWidget(self._cancel_button)
        composer_layout.addLayout(actions)
        root.addWidget(composer)

        # Controller wiring ------------------------------------------- #
        self._controller.started.connect(self._on_started)
        self._controller.finished.connect(self._on_finished)
        self._controller.failed.connect(self._on_failed)
        self._controller.transcription_ready.connect(self._on_transcription)
        self._controller.transcription_failed.connect(self._on_voice_error)
        self._controller.recording_started.connect(lambda: self._voice.set_recording(True))
        self._controller.recording_stopped.connect(lambda: self._voice.set_recording(False))
        self._controller.speech_failed.connect(self._on_speech_failed)

        self._voice.start_requested.connect(self._controller.start_recording)
        self._voice.stop_requested.connect(self._controller.stop_recording)
        self._voice.cancel_requested.connect(self._controller.cancel_recording)
        self._voice.text_accepted.connect(self._use_transcription)

        if conversation_id:
            self.load_conversation(conversation_id)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    @property
    def conversation_id(self) -> Optional[str]:
        return self._conversation_id

    def refresh_voice(self) -> None:
        self._voice.reset()
        self._configure_voice()

    def set_context_status(self, text: str) -> None:
        self._status_label.setText(text)

    def load_conversation(self, conversation_id: str) -> None:
        self._conversation_id = conversation_id
        self._clear_messages()
        try:
            messages = self._service.conversation_messages(self._user_id, conversation_id)
        except AgentError as exc:
            self._error.show_message(exc.user_message)
            return
        for message in messages:
            self._append_bubble(
                role=message.role.value,
                text=message.content,
                evidence=message.evidence,
                timestamp=message.created_at.astimezone().strftime("%H:%M"),
                error_code=message.error_code,
            )
        self._empty_state.setVisible(not messages)

    def start_new_conversation(self) -> None:
        self._conversation_id = None
        self._clear_messages()
        self._empty_state.setVisible(True)
        self._suggestion_cards.clear()
        self._suggestions_host.setVisible(False)
        self._error.setVisible(False)
        self._input.setFocus()
        self.conversation_changed.emit("")

    def focus_input(self) -> None:
        self._input.setFocus()

    # ------------------------------------------------------------------ #
    # Sending
    # ------------------------------------------------------------------ #
    def _send_current(self) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._submit(text)

    def _submit(self, text: str) -> None:
        if self._controller.busy:
            return
        self._error.setVisible(False)
        self._input.clear()
        self._pending_text = text
        self._append_bubble(role="user", text=text, timestamp="now")
        self._show_typing()
        self._controller.send(text, self._conversation_id)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt API)
        if obj is self._input and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ShiftModifier:
                    return False
                self._send_current()
                return True
        return super().eventFilter(obj, event)

    def _on_started(self) -> None:
        self._set_busy(True)
        self._typing_stage = 0
        self._stage_timer = QTimer(self)
        self._stage_timer.setInterval(1400)
        self._stage_timer.timeout.connect(self._advance_typing_stage)
        self._stage_timer.start()

    def _advance_typing_stage(self) -> None:
        if self._typing is None:
            return
        messages = [
            "Searching your records…",
            "Checking permissions and privacy settings…",
            "Reading the matching records…",
            "Preparing a grounded answer…",
        ]
        self._typing_stage = min(self._typing_stage + 1, len(messages) - 1)
        self._typing.set_text(messages[self._typing_stage])

    def _on_finished(self, outcome: ChatOutcome) -> None:
        self._stop_stage_timer()
        self._hide_typing()
        self._set_busy(False)
        self._conversation_id = outcome.conversation_id
        turn: AgentTurnResult = outcome.turn
        self._append_bubble(
            role="assistant",
            text=turn.text,
            evidence=turn.evidence_dict(),
            timestamp="now",
            error_code=turn.error_code,
        )
        for suggestion in outcome.suggestions:
            self._add_suggestion_card(suggestion)
        if outcome.suggestions:
            self.suggestions_changed.emit()
        self.conversation_changed.emit(outcome.conversation_id)

    def _on_failed(self, error: object) -> None:
        self._stop_stage_timer()
        self._hide_typing()
        self._set_busy(False)
        if isinstance(error, ResponseCancelledError):
            self._error.show_message("Request cancelled. You can ask again.")
        elif isinstance(error, AgentError):
            self._error.show_message(error.user_message)
        else:
            logger.error("Chat failure: %s", type(error).__name__)
            self._error.show_message("Something went wrong. Please try again.")
        if self._pending_text and not self._input.toPlainText():
            self._input.setPlainText(self._pending_text)
        self._pending_text = ""

    def _cancel(self) -> None:
        self._controller.cancel()
        self._cancel_button.setEnabled(False)
        self._cancel_button.setText("Cancelling…")

    # ------------------------------------------------------------------ #
    # Message rendering
    # ------------------------------------------------------------------ #
    def _append_bubble(self, *, role: str, text: str, evidence=None, timestamp: str = "", error_code=None) -> None:
        bubble = MessageBubble(
            role=role,
            text=text,
            evidence=evidence,
            timestamp=timestamp,
            error_code=error_code,
        )
        bubble.speak_requested.connect(self._speak)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        if role == "user":
            row.addStretch(1)
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch(1)
        container = QWidget()
        container.setLayout(row)
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, container)
        self._empty_state.setVisible(False)
        self._scroll_to_bottom()

    def _clear_messages(self) -> None:
        while self._messages_layout.count() > 1:
            item = self._messages_layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self._empty_state:
                widget.deleteLater()
        self._empty_state.setVisible(True)
        self._messages_layout.insertWidget(0, self._empty_state)
        self._typing = None

    def _show_typing(self) -> None:
        if self._typing is not None:
            return
        self._typing = TypingIndicator(self)
        row = QHBoxLayout()
        row.addWidget(self._typing)
        row.addStretch(1)
        container = QWidget()
        container.setLayout(row)
        container.setObjectName("typingContainer")
        self._typing_container = container
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, container)
        self._scroll_to_bottom()

    def _hide_typing(self) -> None:
        container = getattr(self, "_typing_container", None)
        if container is not None:
            container.deleteLater()
        self._typing = None
        self._typing_container = None

    def _set_busy(self, busy: bool) -> None:
        self._input.setEnabled(not busy)
        self._send_button.setVisible(not busy)
        self._cancel_button.setVisible(busy)
        self._cancel_button.setEnabled(True)
        self._cancel_button.setText("Cancel")
        self._new_chat_button.setEnabled(not busy)
        if not busy:
            self._input.setFocus()

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(30, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    # ------------------------------------------------------------------ #
    # Suggestions
    # ------------------------------------------------------------------ #
    def _add_suggestion_card(self, suggestion: Suggestion) -> None:
        existing = self._suggestion_cards.pop(suggestion.id, None)
        if existing is not None:
            existing.deleteLater()
        card = SuggestionCard(suggestion, self._suggestions_host)
        card.approve_requested.connect(self._approve_suggestion)
        card.reject_requested.connect(self._reject_suggestion)
        card.edit_requested.connect(self._edit_suggestion)
        self._suggestion_cards[suggestion.id] = card
        self._suggestions_layout.addWidget(card)
        self._suggestions_host.setVisible(True)

    def _approve_suggestion(self, suggestion_id: str) -> None:
        try:
            updated = self._service.approve_suggestion(self._user_id, suggestion_id)
        except AgentError as exc:
            self._error.show_message(exc.user_message)
            return
        self._replace_card(updated)
        if updated.status.value == "completed":
            self._error.setVisible(False)
        elif updated.error:
            self._error.show_message(updated.error)
        self.suggestions_changed.emit()

    def _reject_suggestion(self, suggestion_id: str) -> None:
        try:
            updated = self._service.reject_suggestion(self._user_id, suggestion_id)
        except AgentError as exc:
            self._error.show_message(exc.user_message)
            return
        self._replace_card(updated)
        self.suggestions_changed.emit()

    def _edit_suggestion(self, suggestion_id: str, updates: dict) -> None:
        try:
            updated = self._service.edit_suggestion(
                self._user_id,
                suggestion_id,
                title=updates.get("title"),
                description=updates.get("description"),
                payload_updates=updates.get("payload_updates"),
            )
        except AgentError as exc:
            self._error.show_message(exc.user_message)
            return
        self._replace_card(updated)
        self.suggestions_changed.emit()

    def _replace_card(self, suggestion: Suggestion) -> None:
        self._add_suggestion_card(suggestion)
        if not any(card.isVisible() for card in self._suggestion_cards.values()):
            self._suggestions_host.setVisible(False)

    # ------------------------------------------------------------------ #
    # Voice
    # ------------------------------------------------------------------ #
    def _configure_voice(self) -> None:
        status = self._controller.audio.status()
        if not status["voice_enabled"]:
            self._voice.show_unavailable("Voice input is turned off in Assistant settings.")
            return
        if not status["recording_available"]:
            self._voice.show_unavailable(status["recording_reason"])
        elif not status["stt_available"]:
            self._voice.show_unavailable(status["stt_reason"])

    def _on_transcription(self, result) -> None:
        self._voice.set_recording(False)
        self._voice.show_transcription(result.text, is_cloud=result.is_cloud)

    def _on_voice_error(self, error: object) -> None:
        message = error.user_message if isinstance(error, AgentError) else "Voice input failed."
        self._voice.show_error(message)

    def _on_speech_failed(self, error: object) -> None:
        message = error.user_message if isinstance(error, AgentError) else "Reading aloud failed."
        self._error.show_message(message)

    def _use_transcription(self, text: str) -> None:
        self._voice.reset()
        self._input.setPlainText(text)
        self._input.setFocus()

    def _speak(self, text: str) -> None:
        self._controller.speak(text)

    def _stop_stage_timer(self) -> None:
        timer = getattr(self, "_stage_timer", None)
        if timer is not None:
            timer.stop()
