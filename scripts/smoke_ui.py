"""Headless UI smoke test (Qt offscreen). No network, no microphone required."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtWidgets import QApplication

from memory_agent.security.api_key_manager import InMemoryCredentialStore
from memory_agent.voice.audio_manager import AudioManager
from memory_companion.composition import build_context
from memory_companion.config import AppPaths
from memory_companion.demo_data import ensure_demo_user
from memory_companion.ui.main_window import MainWindow
from memory_companion.ui.styles import STYLESHEET


def main() -> int:
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLESHEET)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        ctx = build_context(paths=AppPaths(data_dir=Path(tmp)), credential_store=InMemoryCredentialStore())
        try:
            user_id, _ = ensure_demo_user(ctx)
            session = ctx.auth.login("demo", "demo-pass-1234")
            assert session.user_id == user_id
            audio = AudioManager(
                settings=ctx.agent_runtime.service.settings(), consent=ctx.consent
            )
            window = MainWindow(ctx, session, audio)
            window.show()
            app.processEvents()

            for key, _label in MainWindow.NAV:
                window._show_page(key)
                app.processEvents()
            print("pages:", len(MainWindow.NAV))

            window._show_page("memories")
            page = window._pages["memories"]
            assert page._table.rowCount() == 4, page._table.rowCount()
            print("memories rows:", page._table.rowCount())

            window._show_page("reminders")
            assert window._pages["reminders"]._table.rowCount() == 2

            window._show_page("assistant")
            window.assistant_page.chat._input.setPlainText("Where is my wallet?")
            # Do not send: no API key / provider in the smoke test.

            window.close()
            app.processEvents()
            print("UI OK")
        finally:
            ctx.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
