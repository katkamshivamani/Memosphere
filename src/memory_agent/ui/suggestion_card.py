"""Suggestion cards: review, edit and explicitly approve or reject."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from memory_agent.models.suggestion import Suggestion, SuggestionStatus, SuggestionType

TYPE_LABELS = {
    SuggestionType.SAVE_MEMORY: "Save memory",
    SuggestionType.UPDATE_MEMORY: "Update memory",
    SuggestionType.CREATE_REMINDER: "Create reminder",
    SuggestionType.ADD_ACTIVITY: "Add activity",
    SuggestionType.CLARIFY_RECORD: "Clarify record",
}

STATUS_LABELS = {
    SuggestionStatus.PENDING_APPROVAL: "Waiting for your approval",
    SuggestionStatus.APPROVED: "Approved - applying",
    SuggestionStatus.REJECTED: "Rejected",
    SuggestionStatus.COMPLETED: "Completed",
    SuggestionStatus.FAILED: "Failed",
}


class SuggestionEditDialog(QDialog):
    """Edit title/description (and reminder time) before approval."""

    def __init__(self, suggestion: Suggestion, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit suggestion")
        self.setMinimumWidth(440)
        self._suggestion = suggestion

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.title_edit = QLineEdit(suggestion.title)
        form.addRow("Title", self.title_edit)

        self.description_edit = QTextEdit(suggestion.description)
        self.description_edit.setFixedHeight(90)
        form.addRow("Details", self.description_edit)

        self.due_edit: Optional[QLineEdit] = None
        if "due_at" in suggestion.payload:
            self.due_edit = QLineEdit(str(suggestion.payload.get("due_at") or ""))
            self.due_edit.setPlaceholderText("2026-11-21T10:30:00+05:30")
            form.addRow("Due (ISO date/time)", self.due_edit)

        layout.addLayout(form)
        self.error = QLabel("")
        self.error.setProperty("warning", True)
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def updates(self) -> dict:
        payload_updates = {}
        if self.due_edit is not None:
            payload_updates["due_at"] = self.due_edit.text().strip()
        return {
            "title": self.title_edit.text().strip(),
            "description": self.description_edit.toPlainText().strip(),
            "payload_updates": payload_updates,
        }

    def _accept(self) -> None:
        if not self.title_edit.text().strip():
            self.error.setText("A title is required.")
            return
        if self.due_edit is not None and self.due_edit.text().strip():
            try:
                datetime.fromisoformat(self.due_edit.text().strip().replace("Z", "+00:00"))
            except ValueError:
                self.error.setText("Use an ISO date/time such as 2026-11-21T10:30:00+05:30.")
                return
        self.accept()


class SuggestionCard(QFrame):
    approve_requested = Signal(str)
    reject_requested = Signal(str)
    edit_requested = Signal(str, dict)

    def __init__(self, suggestion: Suggestion, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._suggestion = suggestion
        self.setProperty("card", True)
        self.setProperty("suggestion", True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        badge = QLabel(TYPE_LABELS.get(suggestion.type, suggestion.type.value))
        badge.setProperty("chip", True)
        header.addWidget(badge)
        status = QLabel(STATUS_LABELS.get(suggestion.status, suggestion.status.value))
        status.setProperty("muted", True)
        header.addWidget(status)
        header.addStretch(1)
        layout.addLayout(header)

        title = QLabel(suggestion.title)
        title.setWordWrap(True)
        title.setProperty("h3", True)
        layout.addWidget(title)

        if suggestion.description:
            description = QLabel(suggestion.description)
            description.setWordWrap(True)
            layout.addWidget(description)

        if suggestion.reason:
            reason = QLabel("Why: " + suggestion.reason)
            reason.setWordWrap(True)
            reason.setProperty("muted", True)
            layout.addWidget(reason)

        if suggestion.error:
            error = QLabel(suggestion.error)
            error.setWordWrap(True)
            error.setProperty("warning", True)
            layout.addWidget(error)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._edit_button = QPushButton("Edit")
        self._edit_button.clicked.connect(self._on_edit)
        self._reject_button = QPushButton("Reject")
        self._reject_button.clicked.connect(lambda: self.reject_requested.emit(suggestion.id))
        self._approve_button = QPushButton("Approve")
        self._approve_button.setProperty("primary", True)
        self._approve_button.clicked.connect(lambda: self.approve_requested.emit(suggestion.id))
        buttons.addWidget(self._edit_button)
        buttons.addWidget(self._reject_button)
        buttons.addWidget(self._approve_button)
        layout.addLayout(buttons)

        self.set_actions_enabled(suggestion.status is SuggestionStatus.PENDING_APPROVAL)

    def set_actions_enabled(self, enabled: bool) -> None:
        for button in (self._edit_button, self._reject_button, self._approve_button):
            button.setEnabled(enabled)

    def _on_edit(self) -> None:
        dialog = SuggestionEditDialog(self._suggestion, self)
        if dialog.exec() == QDialog.Accepted:
            self.edit_requested.emit(self._suggestion.id, dialog.updates())
