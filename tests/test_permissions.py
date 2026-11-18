"""Permission categories and PermissionGuard enforcement."""

from __future__ import annotations

import pytest

from memory_agent.core.exceptions import PermissionDeniedError, SessionExpiredError
from memory_agent.security.permission_guard import PermissionGuard
from memory_agent.security.permissions import (
    ALL_PERMISSIONS,
    READ_PERMISSIONS,
    SUGGESTION_PERMISSIONS,
    Permission,
)

from tests.helpers import Checker


def test_permission_identifiers_match_the_specified_set():
    assert {p.value for p in ALL_PERMISSIONS} == {
        "memory.read",
        "memory.suggest_create",
        "memory.suggest_update",
        "people.read",
        "places.read",
        "activities.read",
        "routines.read",
        "reminders.read",
        "reminders.suggest_create",
    }
    assert len(READ_PERMISSIONS) == 6
    assert len(SUGGESTION_PERMISSIONS) == 3
    assert all(permission.is_read for permission in READ_PERMISSIONS)
    assert all(permission.is_suggestion for permission in SUGGESTION_PERMISSIONS)


def test_guard_rejects_unknown_session():
    guard = PermissionGuard(Checker(valid_users=()))
    with pytest.raises(SessionExpiredError):
        guard.ensure_session("user_001")


def test_guard_requires_permission():
    guard = PermissionGuard(Checker(denied={"people.read"}))
    with pytest.raises(PermissionDeniedError):
        guard.require("user_001", Permission.PEOPLE_READ, purpose="search_people")
    assert guard.has_permission("user_001", Permission.MEMORY_READ) is True


def test_guard_has_and_require_any():
    guard = PermissionGuard(Checker(denied={"activities.read"}))
    assert guard.has_permission("user_001", Permission.MEMORY_READ) is True
    assert guard.has_permission("user_001", Permission.ACTIVITIES_READ) is False
    chosen = guard.require_any(
        "user_001",
        [Permission.ACTIVITIES_READ, Permission.MEMORY_READ],
    )
    assert chosen is Permission.MEMORY_READ
    with pytest.raises(PermissionDeniedError):
        guard.require_any("user_001", [Permission.ACTIVITIES_READ])


def test_permission_denial_message_is_safe():
    guard = PermissionGuard(Checker(denied={"memory.read"}))
    with pytest.raises(PermissionDeniedError) as info:
        guard.require("user_001", Permission.MEMORY_READ)
    assert "traceback" not in str(info.value).lower()
