"""
Centralized Permission Manager enforcing explicit module and action authorization.
"""

from local_security.access_control.policies import DEFAULT_ROLE_POLICIES
from local_security.core.exceptions import PermissionDeniedError
from local_security.models.permissions import SecurityAction, SecurityModule
from local_security.models.users import UserRole


class PermissionManager:
    """
    Evaluates authorization policies for callers before allowing access to records.
    Enforces role permissions and selective sharing constraints.
    """

    def __init__(self, custom_policies: dict | None = None):
        self._policies = custom_policies or DEFAULT_ROLE_POLICIES

    def _normalize_module(self, module: SecurityModule | str) -> SecurityModule:
        if isinstance(module, SecurityModule):
            return module
        try:
            return SecurityModule(module.lower())
        except ValueError:
            raise ValueError(f"Unknown module '{module}'. Valid modules: {[m.value for m in SecurityModule]}") from None

    def _normalize_action(self, action: SecurityAction | str) -> SecurityAction:
        if isinstance(action, SecurityAction):
            return action
        try:
            return SecurityAction(action.lower())
        except ValueError:
            raise ValueError(f"Unknown action '{action}'. Valid actions: {[a.value for a in SecurityAction]}") from None

    def _normalize_role(self, role: UserRole | str) -> UserRole:
        if isinstance(role, UserRole):
            return role
        try:
            return UserRole(role.lower())
        except ValueError:
            return UserRole.GUEST

    def check_access(
        self,
        module: SecurityModule | str,
        action: SecurityAction | str,
        role: UserRole | str = UserRole.OWNER,
        is_shared_with_caregiver: bool | None = None,
        raise_exception: bool = True,
    ) -> bool:
        """
        Evaluates whether an actor with a given role can perform 'action' on 'module'.
        If the role is CAREGIVER or ACCOUNTABILITY_PARTNER and the target record is not shared,
        access is denied.
        """
        mod = self._normalize_module(module)
        act = self._normalize_action(action)
        usr_role = self._normalize_role(role)

        role_permissions = self._policies.get(usr_role, {})
        allowed_actions: set[SecurityAction] = role_permissions.get(mod, set())

        # 1. Base action check
        if act not in allowed_actions:
            if raise_exception:
                raise PermissionDeniedError(
                    module=mod.value,
                    action=act.value,
                    reason=f"Role '{usr_role.value}' is not granted '{act.value}' permission on '{mod.value}'."
                )
            return False

        # 2. Selective sharing check for Caregivers / Accountability Partners
        if usr_role in (UserRole.CAREGIVER, UserRole.ACCOUNTABILITY_PARTNER) and is_shared_with_caregiver is False:
            if raise_exception:
                raise PermissionDeniedError(
                    module=mod.value,
                    action=act.value,
                    reason="Record has not been explicitly authorized by the user for caregiver sharing."
                )
            return False

        return True
