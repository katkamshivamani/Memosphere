"""Privacy and security dashboard for the signed-in user."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from memory_agent.security.consent_manager import ConsentScope
from memory_agent.security.permissions import ALL_PERMISSIONS
from memory_companion.modules.common import parse_datetime

PERMISSION_LABELS = {
    "memory.read": "Read memories",
    "memory.suggest_create": "Suggest saving a memory",
    "memory.suggest_update": "Suggest updating a memory",
    "people.read": "Read people and relationships",
    "places.read": "Read places",
    "activities.read": "Read activity history",
    "routines.read": "Read routines and routine history",
    "reminders.read": "Read reminders",
    "reminders.suggest_create": "Suggest creating a reminder",
}


class PrivacyPage(QWidget):
    def __init__(self, ctx, user_id: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._user_id = user_id

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        scroll.setWidget(content)

        title = QLabel("Privacy & security")
        title.setProperty("h1", True)
        layout.addWidget(title)

        # Encryption ---------------------------------------------------- #
        encryption_group = QGroupBox("Encrypted storage")
        form = QFormLayout(encryption_group)
        self._encryption_status = QLabel(ctx.encryption.describe())
        self._encryption_status.setWordWrap(True)
        form.addRow("Database", self._encryption_status)
        location = QLabel(str(ctx.paths.database_path))
        location.setWordWrap(True)
        location.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow("Location", location)
        verify_row = QHBoxLayout()
        verify = QPushButton("Verify encryption now")
        verify.clicked.connect(self._verify_encryption)
        verify_row.addWidget(verify)
        verify_row.addStretch(1)
        form.addRow("", self._wrap(verify_row))
        note = QLabel(
            "The database is encrypted with SQLCipher and unlocked by a random key "
            "kept in the Windows Data Protection API. There is no unencrypted "
            "fallback: if the key store is unavailable the app refuses to open."
        )
        note.setWordWrap(True)
        note.setProperty("muted", True)
        form.addRow("", note)
        layout.addWidget(encryption_group)

        # Consent ------------------------------------------------------- #
        consent_group = QGroupBox("Sharing and consent")
        consent_layout = QVBoxLayout(consent_group)
        self._full_context = QLabel("")
        self._full_context.setWordWrap(True)
        consent_layout.addWidget(self._full_context)
        self._cloud_audio = QLabel("")
        self._cloud_audio.setWordWrap(True)
        consent_layout.addWidget(self._cloud_audio)
        consent_buttons = QHBoxLayout()
        withdraw_context = QPushButton("Withdraw full-context consent")
        withdraw_context.clicked.connect(self._withdraw_context)
        consent_buttons.addWidget(withdraw_context)
        withdraw_audio = QPushButton("Withdraw cloud audio consent")
        withdraw_audio.clicked.connect(self._withdraw_audio)
        consent_buttons.addWidget(withdraw_audio)
        consent_buttons.addStretch(1)
        consent_layout.addLayout(consent_buttons)
        layout.addWidget(consent_group)

        # Permissions --------------------------------------------------- #
        permissions_group = QGroupBox("Assistant permissions")
        permissions_layout = QVBoxLayout(permissions_group)
        hint = QLabel(
            "Turning a permission off blocks the corresponding assistant tool "
            "immediately. The assistant can never grant its own permissions."
        )
        hint.setWordWrap(True)
        hint.setProperty("muted", True)
        permissions_layout.addWidget(hint)
        self._permission_boxes: dict[str, QCheckBox] = {}
        for permission in ALL_PERMISSIONS:
            box = QCheckBox(PERMISSION_LABELS.get(permission.value, permission.value))
            box.setChecked(ctx.auth.has_permission(user_id, permission.value))
            box.toggled.connect(
                lambda checked, p=permission.value: self._set_permission(p, checked)
            )
            self._permission_boxes[permission.value] = box
            permissions_layout.addWidget(box)
        layout.addWidget(permissions_group)

        # Audit --------------------------------------------------------- #
        audit_group = QGroupBox("Recent activity")
        audit_layout = QVBoxLayout(audit_group)
        audit_hint = QLabel(
            "Security-relevant actions are recorded here. Memory contents and "
            "credentials are never written to this log."
        )
        audit_hint.setWordWrap(True)
        audit_hint.setProperty("muted", True)
        audit_layout.addWidget(audit_hint)
        self._audit_table = QTableWidget(0, 3)
        self._audit_table.setHorizontalHeaderLabels(["When", "Action", "Details"])
        self._audit_table.verticalHeader().setVisible(False)
        self._audit_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._audit_table.setAlternatingRowColors(True)
        self._audit_table.horizontalHeader().setStretchLastSection(True)
        audit_layout.addWidget(self._audit_table)
        refresh = QPushButton("Refresh log")
        refresh.clicked.connect(self._refresh_audit)
        audit_layout.addWidget(refresh, 0)
        layout.addWidget(audit_group)
        layout.addStretch(1)

        self.refresh()

    def _wrap(self, layout) -> QWidget:
        widget = QWidget()
        widget.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        return widget

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        self._full_context.setText(
            "Full personal context for the AI provider: "
            + (
                "consent granted"
                if self._ctx.consent.is_granted(ConsentScope.FULL_CONTEXT)
                else "not granted"
            )
        )
        self._cloud_audio.setText(
            "Cloud audio transcription: "
            + (
                "consent granted"
                if self._ctx.consent.is_granted(ConsentScope.CLOUD_TRANSCRIPTION)
                else "not granted"
            )
        )
        for permission, box in self._permission_boxes.items():
            box.blockSignals(True)
            box.setChecked(self._ctx.auth.has_permission(self._user_id, permission))
            box.blockSignals(False)
        self._refresh_audit()

    def _refresh_audit(self) -> None:
        try:
            events = self._ctx.audit.recent(self._user_id, limit=40)
        except Exception:
            events = []
        self._audit_table.setRowCount(len(events))
        for row, event in enumerate(events):
            parsed = parse_datetime(event["created_at"])
            when = parsed.astimezone().strftime("%d %b %H:%M") if parsed else event["created_at"]
            details = event["target_type"] or ""
            if event.get("target_id"):
                details += f" · {event['target_id']}"
            self._audit_table.setItem(row, 0, QTableWidgetItem(when))
            self._audit_table.setItem(row, 1, QTableWidgetItem(event["action"]))
            self._audit_table.setItem(row, 2, QTableWidgetItem(details))
        self._audit_table.resizeColumnsToContents()

    def _verify_encryption(self) -> None:
        status = self._ctx.db.verify_encryption()
        self._encryption_status.setText(status.describe())
        if not status.encrypted:
            QMessageBox.critical(self, "Encryption problem", status.detail or "Not encrypted.")

    def _set_permission(self, permission: str, granted: bool) -> None:
        self._ctx.auth.set_permission(self._user_id, permission, granted)

    def _withdraw_context(self) -> None:
        self._ctx.agent_runtime.service.withdraw_full_context_consent()
        self.refresh()

    def _withdraw_audio(self) -> None:
        self._ctx.agent_runtime.service.withdraw_cloud_transcription_consent()
        self.refresh()
