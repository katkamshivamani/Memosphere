"""PySide6 user-interface tests (offscreen)."""

from __future__ import annotations

import pytest

from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton

from memory_agent.config import AgentSettings
from memory_agent.models.suggestion import Suggestion, SuggestionStatus, SuggestionType
from memory_agent.security.api_key_manager import InMemoryCredentialStore
from memory_agent.ui.chat_message import MessageBubble
from memory_agent.ui.suggestion_card import SuggestionCard
from memory_agent.ui.voice_controls import VoiceControls
from memory_agent.ui.workers import FunctionWorker
from memory_agent.voice.audio_manager import AudioManager
from memory_agent.voice.speech_to_text import AudioClip, MockSTT
from memory_agent.voice.text_to_speech import MockTTS
from memory_companion.composition import build_context
from memory_companion.config import AppPaths
from memory_companion.demo_data import ensure_demo_user
from memory_companion.ui.data_pages import AddRecordDialog
from memory_companion.ui.main_window import MainWindow
from memory_companion.ui.styles import STYLESHEET

pytestmark = pytest.mark.ui


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLESHEET)
    return app


class _Recorder:
    def __init__(self):
        self.recording = False

    @property
    def is_available(self):
        return True

    @property
    def unavailable_reason(self):
        return ""

    @property
    def is_recording(self):
        return self.recording

    def start(self):
        self.recording = True

    def stop(self):
        self.recording = False
        return AudioClip(data=b"wav", duration_s=1.0)

    def cancel(self):
        self.recording = False


@pytest.fixture
def window(qt_app, tmp_path):
    ctx = build_context(
        paths=AppPaths(data_dir=tmp_path), credential_store=InMemoryCredentialStore()
    )
    user_id, _ = ensure_demo_user(ctx)
    session = ctx.auth.login("demo", "demo-pass-1234")
    audio = AudioManager(
        settings=AgentSettings(),
        consent=ctx.consent,
        stt=MockSTT(),
        tts=MockTTS(),
        recorder=_Recorder(),
    )
    win = MainWindow(ctx, session, audio)
    win.show()
    qt_app.processEvents()
    yield win, ctx, user_id
    win.close()
    win.deleteLater()
    qt_app.processEvents()
    ctx.close()
    qt_app.processEvents()


def test_all_pages_load(window, qt_app):
    win, _ctx, _user = window
    for key, _label in MainWindow.NAV:
        win._show_page(key)
        qt_app.processEvents()
        assert win._stack.currentWidget() is win._pages[key]


def test_data_pages_show_seeded_records(window, qt_app):
    win, _ctx, _user = window
    assert win._pages["memories"]._table.rowCount() == 4
    assert win._pages["people"]._table.rowCount() == 2
    assert win._pages["places"]._table.rowCount() == 3
    assert win._pages["activities"]._table.rowCount() == 3
    assert win._pages["routines"]._table.rowCount() == 2
    assert win._pages["reminders"]._table.rowCount() == 2


def test_privacy_page_reports_encryption_and_permissions(window):
    win, _ctx, _user = window
    page = win._pages["privacy"]
    assert "Encrypted" in page._encryption_status.text()
    assert len(page._permission_boxes) == 9


def test_suggestion_card_actions_and_status(qt_app):
    pending = Suggestion(
        user_id="user_001",
        type=SuggestionType.SAVE_MEMORY,
        title="Umbrella",
        description="Umbrella by the door.",
        status=SuggestionStatus.PENDING_APPROVAL,
    )
    card = SuggestionCard(pending)
    buttons = {button.text(): button for button in card.findChildren(QPushButton)}
    assert buttons["Approve"].isEnabled()
    assert buttons["Reject"].isEnabled()

    completed = pending.model_copy(update={"status": SuggestionStatus.COMPLETED})
    done_card = SuggestionCard(completed)
    done_buttons = {button.text(): button for button in done_card.findChildren(QPushButton)}
    assert done_buttons["Approve"].isEnabled() is False


def test_message_bubble_displays_grounding_and_sources(qt_app):
    bubble = MessageBubble(
        role="assistant",
        text="Your wallet is in the study desk drawer.",
        evidence={
            "grounding": "recorded",
            "summary": "Recorded information · 1 record",
            "sources": [{"title": "Wallet location"}],
            "conflicts": [],
        },
        timestamp="10:15",
    )
    labels = [label.text() for label in bubble.findChildren(QLabel)]
    text = " ".join(labels)
    assert "Recorded information" in text
    assert "Wallet location" in text
    # Deleting explicitly keeps Python's signal/lambda reference cycle from
    # being collected after Qt shuts down, which aborts on Windows.
    bubble.deleteLater()
    qt_app.processEvents()


def test_voice_controls_show_editable_transcript(qt_app):
    controls = VoiceControls()
    controls.show_transcription("Where is my passport?", is_cloud=False)
    assert controls._editor.toPlainText() == "Where is my passport?"
    accepted: list[str] = []
    controls.text_accepted.connect(accepted.append)
    controls._accept_text()
    assert accepted == ["Where is my passport?"]


def test_add_record_dialog_validates_required_fields(qt_app):
    dialog = AddRecordDialog(
        "Add memory",
        [
            {"key": "title", "label": "Title", "required": True},
            {"key": "content", "label": "Content", "kind": "multiline", "required": True},
        ],
    )
    dialog._accept()
    assert dialog.result() != QDialog.Accepted
    dialog._widgets["title"].setText("Spare glasses")
    dialog._widgets["content"].setPlainText("Glasses are in the bedside table.")
    dialog._accept()
    assert dialog.result() == QDialog.Accepted


def test_worker_emits_success_and_failure(qt_app):
    results: list[object] = []
    errors: list[object] = []
    worker = FunctionWorker(lambda value: value * 2, 21)
    worker.signals.finished.connect(results.append)
    worker.signals.failed.connect(errors.append)
    worker.run()
    assert results == [42]

    failing = FunctionWorker(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    failing.signals.failed.connect(errors.append)
    failing.run()
    assert isinstance(errors[-1], RuntimeError)


def test_chat_page_has_voice_controls_and_empty_state(window):
    win, _ctx, _user = window
    chat = win.assistant_page.chat
    assert chat._voice is not None
    assert chat._empty_state.isVisible() is True
