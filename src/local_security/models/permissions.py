"""
Access Control and Permission Models.
"""
from enum import StrEnum

from pydantic import BaseModel, Field


class SecurityModule(StrEnum):
    PEOPLE = "people"
    PLACES = "places"
    MEMORIES = "memories"
    ACTIVITIES = "activities"
    ROUTINES = "routines"
    CONVERSATIONS = "conversations"
    CAREGIVER_DASHBOARD = "caregiver_dashboard"
    SYSTEM = "system"


class SecurityAction(StrEnum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXPORT = "export"
    SHARE = "share"


class AccessRequest(BaseModel):
    """Encapsulates a subject's request to access a module resource."""
    module: SecurityModule
    action: SecurityAction
    actor_id: str
    target_record_id: str | None = None
    context: dict = Field(default_factory=dict)


class PermissionRule(BaseModel):
    """Configured permission rule."""
    rule_id: str | None = None
    role: str
    module: SecurityModule
    allowed_actions: list[SecurityAction]
    shareable_only: bool = False
    description: str | None = None
