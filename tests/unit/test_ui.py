"""
UI integration tests verifying PySide6 widgets and dashboard loading.
"""
import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from local_security.core.configuration import SecurityConfig
from local_security.core.security_manager import SecurityManager
from local_security.ui.dialogs.setup_dialog import SetupDialog
from local_security.ui.windows.dashboard_window import SecurityDashboardWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        # Offscreen platform for reliable headless execution if needed
        os.environ.setdefault("QT_QPA_PLATFORM", "windows")
        app = QApplication([])
    return app


@pytest.fixture
def test_sec_mgr(tmp_path: Path) -> SecurityManager:
    cfg = SecurityConfig(
        app_data_dir=tmp_path / "ui_test_data",
        database_filename="ui_vault.db",
        key_identifier="UITestKeyIdentifier",
    )
    mgr = SecurityManager(cfg)
    mgr.initialize()
    yield mgr
    mgr.shutdown()


def test_setup_dialog_creation(qapp, test_sec_mgr: SecurityManager):
    dlg = SetupDialog(test_sec_mgr)
    assert dlg.windowTitle() == "Welcome to Personal Memory Companion"
    assert dlg.name_edit is not None
    assert dlg.pin_edit is not None
    dlg.close()


def test_dashboard_window_creation(qapp, test_sec_mgr: SecurityManager):
    # Setup user first
    test_sec_mgr.auth.setup_initial_user(
        username="test_ui_user",
        display_name="Test UI User",
        pin="839201",
        confirm_pin="839201",
        enable_biometrics=False,
    )
    # Unlock
    test_sec_mgr.unlock_with_pin("test_ui_user", "839201")

    win = SecurityDashboardWindow(test_sec_mgr)
    assert "Security & Privacy Center" in win.windowTitle()
    assert win.tabs.count() == 4
    win.close()
