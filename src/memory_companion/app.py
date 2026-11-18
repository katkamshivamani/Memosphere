"""Desktop entry point.

Run with ``python -m memory_companion`` (or ``scripts/run_app.py``).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from memory_agent.core.exceptions import CredentialStoreUnavailableError
from memory_agent.voice.audio_manager import AudioManager

from memory_companion.composition import AppContext, build_context, setup_logging
from memory_companion.config import AppPaths
from memory_companion.ui.login import LoginDialog
from memory_companion.ui.main_window import MainWindow
from memory_companion.ui.styles import STYLESHEET

logger = logging.getLogger("memory_companion.app")


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Personal Memory Companion")
    parser.add_argument("--data-dir", type=Path, default=None, help="Override the data folder")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Create the demo account and sample records on first run",
    )
    parser.add_argument("--reset-demo-password", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def _build_audio(ctx: AppContext) -> AudioManager:
    settings = ctx.agent_runtime.service.settings()
    try:
        key = ctx.key_manager.get_key("gemini")
    except Exception:
        key = None
    return AudioManager(
        settings=settings,
        consent=ctx.consent,
        gemini_api_key=key,
        gemini_model=settings.model_for("gemini"),
    )


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    paths = AppPaths(data_dir=args.data_dir) if args.data_dir else AppPaths.default()
    setup_logging(paths, level=getattr(logging, str(args.log_level).upper(), logging.INFO))

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Personal Memory Companion")
    app.setStyleSheet(STYLESHEET)

    try:
        ctx = build_context(paths=paths)
    except CredentialStoreUnavailableError as exc:
        QMessageBox.critical(
            None,
            "Secure storage unavailable",
            "The application cannot start because secure credential storage is "
            "unavailable on this system.\n\n"
            f"{exc}\n\n"
            "Encrypted storage is never silently downgraded to an unencrypted "
            "database. Install or enable the Windows Data Protection API and try "
            "again.",
        )
        return 2
    except Exception as exc:
        logger.exception("Startup failed")
        QMessageBox.critical(
            None,
            "Startup failed",
            f"The encrypted database could not be opened ({type(exc).__name__}).\n\n"
            "See the log file in the data folder for details. No unencrypted "
            "fallback was used.",
        )
        return 3

    try:
        if args.demo:
            from memory_companion.demo_data import ensure_demo_user

            ensure_demo_user(ctx)

        audio = _build_audio(ctx)
        while True:
            dialog = LoginDialog(ctx.auth)
            dialog.set_database_note(
                f"Data folder: {ctx.paths.data_dir} · {ctx.encryption.describe()}"
            )
            if not ctx.auth.has_any_user():
                dialog.prefill_username("")
            if dialog.exec() != LoginDialog.Accepted or dialog.session is None:
                return 0
            session = dialog.session
            window = MainWindow(ctx, session, audio)
            signed_out = {"value": False}

            def _on_signed_out() -> None:
                signed_out["value"] = True

            window.signed_out.connect(_on_signed_out)
            window.show()
            app.exec()
            if not signed_out["value"]:
                return 0
    finally:
        ctx.close()
        app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
