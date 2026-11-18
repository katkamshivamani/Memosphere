"""
User and Security Audit data models.
"""
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class UserRole(StrEnum):
    OWNER = "owner"
    CAREGIVER = "caregiver"
    ACCOUNTABILITY_PARTNER = "accountability_partner"
    GUEST = "guest"


class UserProfile(BaseModel):
    """User account representation."""
    user_id: str
    username: str
    display_name: str
    role: UserRole = UserRole.OWNER
    pin_hash: str | None = None
    biometrics_enabled: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_authenticated_at: datetime | None = None


class AuthAttemptState(BaseModel):
    """Tracks failed authentication attempts for rate limiting."""
    user_id: str
    failed_attempts: int = 0
    locked_until: datetime | None = None
    last_attempt_at: datetime | None = None


class AuditEventType(StrEnum):
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    BIOMETRIC_SUCCESS = "biometric_success"
    BIOMETRIC_FAILURE = "biometric_failure"
    PIN_CHANGED = "pin_changed"
    APP_LOCKED = "app_locked"
    APP_UNLOCKED = "app_unlocked"
    KEY_ROTATED = "key_rotated"
    RECORD_CREATED = "record_created"
    RECORD_ACCESSED = "record_accessed"
    RECORD_UPDATED = "record_updated"
    RECORD_DELETED = "record_deleted"
    PERMISSION_DENIED = "permission_denied"
    DATABASE_BACKUP = "database_backup"


class AuditEvent(BaseModel):
    """Immutable security audit event."""
    event_id: str | None = None
    event_type: AuditEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actor_id: str | None = None
    module: str | None = None
    action: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    ip_or_host: str = "localhost"
