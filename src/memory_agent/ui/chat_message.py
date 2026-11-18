"""Chat message bubbles with evidence display."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

GROUNDING_LABELS = {
    "recorded": "Recorded",
    "inferred": "Inferred",
    "missing": "Not recorded",
    "conflicting": "Conflicting records",
}


class EvidenceList(QWidget):
    """Small provenance chips shown under an assistant answer."""

    def __init__(self, evidence: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(3)

        grounding = str(evidence.get("grounding", ""))
        summary = evidence.get("summary") or GROUNDING_LABELS.get(grounding, "")
        if summary:
            badge = QLabel(summary)
            badge.setWordWrap(True)
            badge.setProperty("chip", True)
            badge.setProperty("grounding", grounding)
            layout.addWidget(badge)

        sources = evidence.get("sources") or []
        if sources:
            names = []
            for source in sources[:5]:
                title = source.get("title") or source.get("record_id") or "Record"
                names.append(str(title))
            label = QLabel("Sources: " + " · ".join(names))
            label.setWordWrap(True)
            label.setProperty("muted", True)
            layout.addWidget(label)

        conflicts = evidence.get("conflicts") or []
        if conflicts:
            label = QLabel("Conflicting records: " + "; ".join(str(c) for c in conflicts[:3]))
            label.setWordWrap(True)
            label.setProperty("warning", True)
            layout.addWidget(label)


class MessageBubble(QFrame):
    """One conversation message. User messages align right, assistant left."""

    speak_requested = Signal(str)

    def __init__(
        self,
        *,
        role: str,
        text: str,
        evidence: Optional[dict] = None,
        timestamp: str = "",
        error_code: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._role = role
        self._text = text
        is_user = role == "user"
        self.setProperty("bubble", True)
        self.setProperty("role", role)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        sender = QLabel("You" if is_user else "Memory Assistant")
        sender.setProperty("sender", True)
        header.addWidget(sender)
        if timestamp:
            stamp = QLabel(timestamp)
            stamp.setProperty("muted", True)
            header.addWidget(stamp)
        header.addStretch(1)

        if not is_user:
            speak = QPushButton("Read aloud")
            speak.setProperty("flat", True)
            speak.setToolTip("Read this answer aloud")
            speak.clicked.connect(lambda: self.speak_requested.emit(self._text))
            header.addWidget(speak)

        layout.addLayout(header)

        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setProperty("body", True)
        layout.addWidget(body)

        if error_code:
            error = QLabel(f"Technical code: {error_code}")
            error.setProperty("muted", True)
            layout.addWidget(error)

        if evidence and not is_user:
            layout.addWidget(EvidenceList(evidence))

        self.setMaximumWidth(720)


class TypingIndicator(QFrame):
    """Visible loading state while the agent works."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty("bubble", True)
        self.setProperty("role", "assistant")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        self._label = QLabel("Searching your records…")
        self._label.setProperty("muted", True)
        layout.addWidget(self._label)
        self.setMaximumWidth(320)

    def set_text(self, text: str) -> None:
        self._label.setText(text)


class EmptyState(QWidget):
    """Friendly guidance shown in an empty conversation."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        title = QLabel("Ask about your own memories")
        title.setProperty("h2", True)
        subtitle = QLabel(
            "For example: “Where did I keep my wallet?”, “Who is Sarah?”, or "
            "“What did I do yesterday?”\n\nAnswers come only from records you have saved. "
            "If something is not recorded, the assistant will say so."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch(1)
