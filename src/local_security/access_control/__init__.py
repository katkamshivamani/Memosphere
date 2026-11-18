"""Access control package initialization."""
from local_security.access_control.permission_manager import PermissionManager
from local_security.access_control.policies import DEFAULT_ROLE_POLICIES

__all__ = ["DEFAULT_ROLE_POLICIES", "PermissionManager"]
