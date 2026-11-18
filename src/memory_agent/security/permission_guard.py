"""Permission enforcement adapter.

The agent does not own a security system.  It calls the application's existing
session and permission service through the :class:`PermissionChecker` contract,
and fails closed if that service is missing or raises.
"""

from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable

from memory_agent.core.exceptions import (
    AuthenticationRequiredError,
    PermissionDeniedError,
    SessionExpiredError,
)
from memory_agent.security.permissions import Permission


@runtime_checkable
class PermissionChecker(Protocol):
    """Implemented by the host application's security module."""

    def validate_session(self, user_id: str) -> bool:
        """Return True if the user's session is authenticated and unexpired."""
        ...

    def has_permission(self, user_id: str, permission: str) -> bool:
        """Return True if the user currently holds ``permission``."""
        ...


class PermissionGuard:
    """Session + permission checks used before any data access."""

    def __init__(self, checker: PermissionChecker) -> None:
        self._checker = checker

    def ensure_session(self, user_id: str) -> None:
        if not user_id:
            raise AuthenticationRequiredError("No authenticated user id was supplied.")
        try:
            valid = self._checker.validate_session(user_id)
        except AuthenticationRequiredError:
            raise
        except Exception as exc:
            raise AuthenticationRequiredError(
                f"Session validation failed: {exc}",
                user_message="Your session could not be verified. Please sign in again.",
            ) from exc
        if not valid:
            raise SessionExpiredError("Session is invalid or expired for the active user.")

    def has_permission(self, user_id: str, permission: Permission | str) -> bool:
        value = permission.value if isinstance(permission, Permission) else str(permission)
        try:
            return bool(self._checker.has_permission(user_id, value))
        except Exception:
            # Fail closed: an error must never be interpreted as "allowed".
            return False

    def require(self, user_id: str, permission: Permission | str, *, purpose: str = "") -> None:
        self.ensure_session(user_id)
        if not self.has_permission(user_id, permission):
            value = permission.value if isinstance(permission, Permission) else str(permission)
            raise PermissionDeniedError(
                f"Permission {value!r} not granted for user {user_id!r}"
                + (f" (purpose: {purpose})" if purpose else ""),
                details={"permission": value},
            )

    def require_any(self, user_id: str, permissions: Iterable[Permission]) -> Permission:
        self.ensure_session(user_id)
        for permission in permissions:
            if self.has_permission(user_id, permission):
                return permission
        raise PermissionDeniedError(
            "None of the required permissions are granted.",
            details={"permissions": [p.value for p in permissions]},
        )

    def granted_permissions(self, user_id: str) -> list[str]:
        from memory_agent.security.permissions import ALL_PERMISSIONS

        self.ensure_session(user_id)
        return [p.value for p in ALL_PERMISSIONS if self.has_permission(user_id, p)]
