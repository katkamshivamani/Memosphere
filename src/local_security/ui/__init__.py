"""Desktop user interface package."""
from local_security.ui.app import run_desktop_app
from local_security.ui.windows.dashboard_window import SecurityDashboardWindow

__all__ = ["run_desktop_app", "SecurityDashboardWindow"]
