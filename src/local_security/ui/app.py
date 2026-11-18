"""
Main desktop UI application runner.
"""
import sys

from PySide6.QtWidgets import QApplication, QDialog

from local_security.core.configuration import SecurityConfig
from local_security.core.security_manager import SecurityManager
from local_security.ui.dialogs.setup_dialog import SetupDialog
from local_security.ui.windows.dashboard_window import SecurityDashboardWindow


def run_desktop_app(config: SecurityConfig | None = None) -> int:
    """Initializes SecurityManager and launches the PySide6 security dashboard UI."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    app.setApplicationName("Personal Memory Companion Security Center")
    app.setOrganizationName("MemoryCompanionSecurity")

    sec_mgr = SecurityManager(config)
    sec_mgr.initialize()

    # Check first-time setup
    if not sec_mgr.auth.is_setup_completed():
        setup_dlg = SetupDialog(sec_mgr)
        if setup_dlg.exec() != QDialog.DialogCode.Accepted:
            sec_mgr.shutdown()
            return 0

    window = SecurityDashboardWindow(sec_mgr)
    window.show()

    exit_code = app.exec()
    sec_mgr.shutdown()
    return exit_code


if __name__ == "__main__":
    sys.exit(run_desktop_app())
