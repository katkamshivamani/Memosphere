"""
Unit tests for PermissionManager and role-based access control.
"""
import pytest

from local_security.access_control.permission_manager import PermissionManager
from local_security.core.exceptions import PermissionDeniedError
from local_security.models.permissions import SecurityAction, SecurityModule
from local_security.models.users import UserRole


@pytest.fixture
def perms() -> PermissionManager:
    return PermissionManager()


def test_owner_full_permissions(perms: PermissionManager):
    for mod in SecurityModule:
        for act in SecurityAction:
            assert perms.check_access(mod, act, role=UserRole.OWNER) is True


def test_caregiver_permissions(perms: PermissionManager):
    # Caregiver can read shared memories
    assert perms.check_access(
        SecurityModule.MEMORIES,
        SecurityAction.READ,
        role=UserRole.CAREGIVER,
        is_shared_with_caregiver=True,
    ) is True

    # Caregiver cannot delete memories
    with pytest.raises(PermissionDeniedError) as exc:
        perms.check_access(
            SecurityModule.MEMORIES,
            SecurityAction.DELETE,
            role=UserRole.CAREGIVER,
        )
    assert "not granted 'delete'" in str(exc.value)

    # Caregiver can update routines
    assert perms.check_access(
        SecurityModule.ROUTINES,
        SecurityAction.UPDATE,
        role=UserRole.CAREGIVER,
        is_shared_with_caregiver=True,
    ) is True


def test_selective_caregiver_sharing_enforcement(perms: PermissionManager):
    # Caregiver reading an unshared memory is rejected
    with pytest.raises(PermissionDeniedError) as exc:
        perms.check_access(
            SecurityModule.MEMORIES,
            SecurityAction.READ,
            role=UserRole.CAREGIVER,
            is_shared_with_caregiver=False,
        )
    assert "not been explicitly authorized" in str(exc.value)

    # Owner reading unshared memory is permitted
    assert perms.check_access(
        SecurityModule.MEMORIES,
        SecurityAction.READ,
        role=UserRole.OWNER,
        is_shared_with_caregiver=False,
    ) is True


def test_guest_permissions_denied(perms: PermissionManager):
    with pytest.raises(PermissionDeniedError):
        perms.check_access(SecurityModule.MEMORIES, SecurityAction.READ, role=UserRole.GUEST)

    with pytest.raises(PermissionDeniedError):
        perms.check_access(SecurityModule.ROUTINES, SecurityAction.CREATE, role=UserRole.GUEST)
