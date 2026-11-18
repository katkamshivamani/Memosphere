"""Suggestions inbox: the only place where agent-proposed changes are approved."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from memory_agent.core.exceptions import AgentError
from memory_agent.ui.suggestion_card import SuggestionCard


class SuggestionsPage(QWidget):
    """Lists pending suggestions with approve / reject / edit actions."""

    changed = Signal()

    def __init__(self, service, user_id: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._service = service
        self._user_id = user_id
        self._cards: dict[str, SuggestionCard] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Suggestions")
        title.setProperty("h1", True)
        header.addWidget(title)
        header.addStretch(1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)
        layout.addLayout(header)

        subtitle = QLabel(
            "The assistant can propose new memories, updates or reminders, but it "
            "cannot change anything itself. Review each proposal and approve, edit "
            "or reject it. Approved changes are applied by the application, never "
            "by the AI model."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", True)
        layout.addWidget(subtitle)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        host = QWidget()
        self._cards_layout = QVBoxLayout(host)
        self._cards_layout.setContentsMargins(0, 0, 8, 0)
        self._cards_layout.setSpacing(10)
        self._cards_layout.addStretch(1)
        self._scroll.setWidget(host)
        layout.addWidget(self._scroll, 1)

        self._empty = QLabel("No suggestions are waiting for you.")
        self._empty.setProperty("muted", True)
        layout.addWidget(self._empty)

        self.refresh()

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        for card in self._cards.values():
            card.deleteLater()
        self._cards.clear()
        try:
            pending = self._service.list_pending_suggestions(self._user_id)
        except AgentError:
            pending = []
        for suggestion in pending:
            card = SuggestionCard(suggestion)
            card.approve_requested.connect(self._approve)
            card.reject_requested.connect(self._reject)
            card.edit_requested.connect(self._edit)
            self._cards[suggestion.id] = card
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)
        self._empty.setVisible(not pending)

    # ------------------------------------------------------------------ #
    def _approve(self, suggestion_id: str) -> None:
        try:
            updated = self._service.approve_suggestion(self._user_id, suggestion_id)
        except AgentError as exc:
            QMessageBox.warning(self, "Could not approve", exc.user_message)
            return
        if updated.status.value == "completed":
            QMessageBox.information(self, "Applied", "The change was applied.")
        elif updated.error:
            QMessageBox.warning(self, "Not applied", updated.error)
        self.refresh()
        self.changed.emit()

    def _reject(self, suggestion_id: str) -> None:
        try:
            self._service.reject_suggestion(self._user_id, suggestion_id)
        except AgentError as exc:
            QMessageBox.warning(self, "Could not reject", exc.user_message)
            return
        self.refresh()
        self.changed.emit()

    def _edit(self, suggestion_id: str, updates: dict) -> None:
        try:
            self._service.edit_suggestion(
                self._user_id,
                suggestion_id,
                title=updates.get("title"),
                description=updates.get("description"),
                payload_updates=updates.get("payload_updates"),
            )
        except AgentError as exc:
            QMessageBox.warning(self, "Could not edit", exc.user_message)
            return
        self.refresh()
        self.changed.emit()
