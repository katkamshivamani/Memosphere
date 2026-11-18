# memosphere/models/user.py
# Data model for a trusted contact / user.

from memosphere.config import (
    ROLE_FAMILY,
    ROLE_CAREGIVER,
    ROLE_STUDY_BUDDY,
    ROOMMATE,
    VALID_ROLES,
)


class User:
    """Represents a trusted contact with a role and permission set."""

    def __init__(self, user_id, name, role, permission_level="view"):
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role '{role}'. Must be one of {VALID_ROLES}")
        self.id = user_id
        self.name = name
        self.role = role
        self.permission_level = permission_level  # view, share, admin

    def can(self, action):
        """Check if this user is allowed the given action."""
        # Simple policy: admin can do anything, share can view+share, view can only view
        if self.permission_level == "admin":
            return True
        if self.permission_level == "share" and action in ("view", "share"):
            return True
        if self.permission_level == "view" and action == "view":
            return True
        return False

    def __repr__(self):
        return f"<User {self.name} ({self.role}, {self.permission_level})>"