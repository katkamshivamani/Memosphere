"""Main application window: sidebar navigation and all feature pages."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from memory_agent.ui.agent_settings import AgentSettingsWidget

from memory_companion.security.auth import Session
from memory_companion.ui.assistant_page import AssistantPage
from memory_companion.ui.data_pages import DataTablePage
from memory_companion.ui.privacy_page import PrivacyPage
from memory_companion.ui.suggestions_page import SuggestionsPage

logger = logging.getLogger("memory_companion.ui")


class MainWindow(QMainWindow):
    signed_out = Signal()

    NAV = (
        ("assistant", "Assistant"),
        ("memories", "Memories"),
        ("people", "People"),
        ("places", "Places"),
        ("activities", "Activities"),
        ("routines", "Routines"),
        ("reminders", "Reminders"),
        ("suggestions", "Suggestions"),
        ("privacy", "Privacy & security"),
        ("settings", "Assistant settings"),
    )

    def __init__(self, ctx, session: Session, audio, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._session = session
        self._audio = audio
        self.setWindowTitle("Personal Memory Companion")
        self.resize(1240, 820)
        self.setMinimumSize(980, 640)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self._build_topbar())

        self._stack = QStackedWidget()
        right.addWidget(self._stack, 1)

        right_host = QWidget()
        right_host.setLayout(right)
        root.addWidget(right_host, 1)
        self.setCentralWidget(central)

        self._build_pages()
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(
            "Encrypted database ready · " + ctx.encryption.describe()
        )
        self._nav_button("assistant").setChecked(True)

    # ------------------------------------------------------------------ #
    # Chrome
    # ------------------------------------------------------------------ #
    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(214)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(3)

        brand = QLabel("Memory Companion")
        brand.setObjectName("brand")
        layout.addWidget(brand)
        sub = QLabel("Personal memory assistant")
        sub.setObjectName("brandSub")
        layout.addWidget(sub)

        self._buttons: dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for key, label in self.NAV:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, name=key: self._show_page(name))
            self._group.addButton(button)
            self._buttons[key] = button
            layout.addWidget(button)

        layout.addStretch(1)
        self._user_label = QLabel(self._session.display_name or self._session.username)
        self._user_label.setStyleSheet("color: #d0d5dd; padding: 6px 8px;")
        self._user_label.setWordWrap(True)
        layout.addWidget(self._user_label)

        sign_out = QPushButton("Sign out")
        sign_out.clicked.connect(self._sign_out)
        layout.addWidget(sign_out)
        return sidebar

    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(52)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 8, 24, 8)
        self._page_title = QLabel("Assistant")
        self._page_title.setStyleSheet("font-weight: 600; color: #101828;")
        layout.addWidget(self._page_title)
        layout.addStretch(1)
        encryption = QLabel("🔒 Encrypted locally")
        encryption.setProperty("muted", True)
        layout.addWidget(encryption)
        return bar

    # ------------------------------------------------------------------ #
    # Pages
    # ------------------------------------------------------------------ #
    def _build_pages(self) -> None:
        ctx = self._ctx
        user_id = self._session.user_id

        self.assistant_page = AssistantPage(ctx=ctx, user_id=user_id, audio=self._audio)
        self._pages: dict[str, QWidget] = {"assistant": self.assistant_page}

        self._pages["memories"] = DataTablePage(
            title="Memories",
            subtitle=(
                "Facts and notes you have chosen to remember. The assistant can read "
                "these when you ask, but it cannot change them without your approval."
            ),
            columns=[
                ("title", "Title"),
                ("category", "Category"),
                ("content", "Content"),
                ("updated_at", "Updated"),
            ],
            loader=lambda query: (
                ctx.memories.search_memories(user_id, query)
                if query
                else ctx.memories.list_recent(user_id, limit=200)
            ),
            add_title="memory",
            add_fields=[
                {"key": "title", "label": "Title", "required": True},
                {"key": "category", "label": "Category", "placeholder": "general"},
                {"key": "content", "label": "Content", "kind": "multiline", "required": True},
            ],
            add_handler=lambda values: ctx.memories.create_memory(user_id, values),
            empty_text="No memories saved yet. Use “Add memory” to create one.",
        )

        self._pages["people"] = DataTablePage(
            title="People",
            subtitle="People you know and how you are connected to them.",
            columns=[
                ("name", "Name"),
                ("relationship", "Relationship"),
                ("notes", "Notes"),
                ("updated_at", "Updated"),
            ],
            loader=lambda query: ctx.people.search_people(user_id, query),
            add_title="person",
            add_fields=[
                {"key": "name", "label": "Name", "required": True},
                {"key": "relationship", "label": "Relationship", "placeholder": "friend"},
                {"key": "notes", "label": "Notes", "kind": "multiline"},
            ],
            add_handler=lambda values: ctx.people.create_person(user_id, values),
            empty_text="No people saved yet.",
        )

        self._pages["places"] = DataTablePage(
            title="Places",
            subtitle="Rooms, clinics, shops and other places you refer to.",
            columns=[
                ("name", "Name"),
                ("category", "Category"),
                ("description", "Description"),
                ("updated_at", "Updated"),
            ],
            loader=lambda query: ctx.places.search_places(user_id, query),
            add_title="place",
            add_fields=[
                {"key": "name", "label": "Name", "required": True},
                {"key": "category", "label": "Category", "placeholder": "room"},
                {"key": "description", "label": "Description", "kind": "multiline"},
            ],
            add_handler=lambda values: ctx.places.create_place(user_id, values),
            empty_text="No places saved yet.",
        )

        self._pages["activities"] = DataTablePage(
            title="Activity history",
            subtitle="Things that happened, with the time you recorded.",
            columns=[
                ("name", "Activity"),
                ("description", "Details"),
                ("occurred_at", "When"),
            ],
            loader=lambda query: (
                ctx.activities.search_activities(user_id, query)
                if query
                else ctx.activities.get_activity_history(user_id)
            ),
            add_title="activity",
            add_fields=[
                {"key": "name", "label": "Activity", "required": True},
                {"key": "description", "label": "Details", "kind": "multiline"},
                {
                    "key": "occurred_at",
                    "label": "When (ISO date/time)",
                    "kind": "datetime",
                    "placeholder": "2026-11-18T09:30",
                },
            ],
            add_handler=self._add_activity,
            empty_text="No activities recorded yet.",
        )

        self._pages["routines"] = DataTablePage(
            title="Routines",
            subtitle="Repeating habits. History is recorded only when you log a completion.",
            columns=[
                ("name", "Routine"),
                ("schedule_hint", "Schedule"),
                ("description", "Description"),
            ],
            loader=lambda query: ctx.routines.get_routines(user_id),
            add_title="routine",
            add_fields=[
                {"key": "name", "label": "Name", "required": True},
                {"key": "schedule_hint", "label": "Schedule", "placeholder": "Every day at 08:00"},
                {"key": "description", "label": "Description", "kind": "multiline"},
            ],
            add_handler=lambda values: ctx.routines.create_routine(user_id, values),
            empty_text="No routines saved yet.",
        )

        self._pages["reminders"] = DataTablePage(
            title="Reminders",
            subtitle="Upcoming reminders. The assistant can suggest new ones, but only you can approve them.",
            columns=[
                ("title", "Reminder"),
                ("due_at", "Due"),
                ("status", "Status"),
                ("description", "Details"),
            ],
            loader=lambda query: ctx.reminders.list_all(user_id, limit=200),
            add_title="reminder",
            add_fields=[
                {"key": "title", "label": "Title", "required": True},
                {
                    "key": "due_at",
                    "label": "Due (ISO date/time)",
                    "kind": "datetime",
                    "required": True,
                    "placeholder": "2026-11-21T10:30",
                },
                {"key": "description", "label": "Details", "kind": "multiline"},
            ],
            add_handler=self._add_reminder,
            empty_text="No reminders yet.",
        )

        self.suggestions_page = SuggestionsPage(ctx.agent_runtime.service, user_id)
        self._pages["suggestions"] = self.suggestions_page

        self.privacy_page = PrivacyPage(ctx, user_id)
        self._pages["privacy"] = self.privacy_page

        self.settings_page = AgentSettingsWidget(
            service=ctx.agent_runtime.service,
            audio=self._audio,
            user_id=user_id,
        )
        self.settings_page.settings_saved.connect(self._on_settings_saved)
        self.settings_page.clear_history_requested.connect(self._clear_conversation)
        self._pages["settings"] = self.settings_page

        for key, _label in self.NAV:
            self._stack.addWidget(self._pages[key])

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #
    def _nav_button(self, key: str) -> QPushButton:
        return self._buttons[key]

    def _show_page(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None:
            return
        self._stack.setCurrentWidget(page)
        self._page_title.setText(dict(self.NAV).get(key, key))
        self._buttons[key].setChecked(True)
        refresh = getattr(page, "refresh", None)
        if callable(refresh) and key != "assistant":
            refresh()
        if key == "assistant":
            self.assistant_page.refresh_status()

    def _on_settings_saved(self) -> None:
        new_audio = self._build_audio()
        self._audio = new_audio
        self.assistant_page.set_audio(new_audio)
        self.settings_page.set_audio(new_audio)
        self.assistant_page.refresh_status()
        self.statusBar().showMessage("Settings saved. Voice backends refreshed.", 5000)

    def _build_audio(self):
        from memory_agent.voice.audio_manager import AudioManager

        settings = self._ctx.agent_runtime.service.settings()
        try:
            key = self._ctx.key_manager.get_key("gemini")
        except Exception:
            key = None
        return AudioManager(
            settings=settings,
            consent=self._ctx.consent,
            gemini_api_key=key,
            gemini_model=settings.model_for("gemini"),
        )

    def _clear_conversation(self) -> None:
        conversation_id = self.assistant_page.chat.conversation_id
        if not conversation_id:
            return
        confirm = QMessageBox.question(
            self,
            "Clear conversation",
            "Delete every message in the current conversation? This cannot be undone.",
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self._ctx.agent_runtime.service.clear_conversation(
                self._session.user_id, conversation_id
            )
        except Exception as exc:
            QMessageBox.warning(self, "Not cleared", f"The conversation was not cleared: {exc}")
            return
        self.assistant_page.chat.start_new_conversation()

    def _sign_out(self) -> None:
        self._ctx.auth.logout(self._session.user_id)
        self.signed_out.emit()
        self.close()

    # ------------------------------------------------------------------ #
    # Add handlers
    # ------------------------------------------------------------------ #
    def _add_activity(self, values: dict) -> None:
        from memory_companion.modules.common import parse_datetime

        occurred = parse_datetime(values.get("occurred_at")) or datetime.now(timezone.utc)
        self._ctx.activities.create_activity(
            self._session.user_id,
            {
                "name": values.get("name"),
                "description": values.get("description"),
                "occurred_at": occurred.isoformat(),
            },
        )

    def _add_reminder(self, values: dict) -> None:
        self._ctx.reminders.create_reminder(
            self._session.user_id,
            {
                "title": values.get("title"),
                "description": values.get("description"),
                "due_at": values.get("due_at"),
                "source": "manual",
            },
        )

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        try:
            self._ctx.auth.logout(self._session.user_id)
        except Exception:
            pass
        super().closeEvent(event)
