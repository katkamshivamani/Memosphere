"""
Structured record models for Universal Personal Memory Companion.
"""
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class PersonRecord(BaseModel):
    id: str | None = None
    name: str
    nickname: str | None = None
    relationship_to_user: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None
    avatar_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RelationshipRecord(BaseModel):
    id: str | None = None
    person_a_id: str
    person_b_id: str
    relationship_type: str  # e.g., "spouse", "daughter", "caregiver", "doctor"
    description: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class PlaceRecord(BaseModel):
    id: str | None = None
    name: str
    address: str | None = None
    category: str | None = None  # e.g., "home", "hospital", "store", "park"
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ItemRecord(BaseModel):
    id: str | None = None
    name: str
    usual_location: str | None = None
    current_location: str | None = None
    category: str | None = None  # e.g., "keys", "glasses", "wallet", "medication"
    description: str | None = None
    image_path: str | None = None
    last_seen_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MemoryRecord(BaseModel):
    id: str | None = None
    title: str
    content: str
    category: str = "general"  # e.g., "childhood", "family", "medical", "preference"
    importance_level: int = 1  # 1 to 5
    tags: list[str] = Field(default_factory=list)
    people_mentioned: list[str] = Field(default_factory=list)
    places_mentioned: list[str] = Field(default_factory=list)
    is_shared_with_caregiver: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ActivityRecord(BaseModel):
    id: str | None = None
    activity_name: str
    category: str = "daily"  # e.g., "exercise", "reading", "walk", "social", "meal"
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime | None = None
    notes: str | None = None
    is_shared_with_caregiver: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class RoutineFrequency(StrEnum):
    DAILY = "daily"
    WEEKDAYS = "weekdays"
    WEEKENDS = "weekends"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class RoutineRecord(BaseModel):
    id: str | None = None
    title: str
    description: str | None = None
    frequency: RoutineFrequency = RoutineFrequency.DAILY
    time_of_day: str | None = None  # e.g., "08:00"
    is_shared_with_caregiver: bool = False
    is_active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RoutineLogStatus(StrEnum):
    COMPLETED = "completed"
    MISSED = "missed"
    SKIPPED = "skipped"
    PARTIAL = "partial"


class RoutineLogRecord(BaseModel):
    id: str | None = None
    routine_id: str
    scheduled_date: date
    status: RoutineLogStatus = RoutineLogStatus.COMPLETED
    notes: str | None = None
    logged_at: datetime = Field(default_factory=utc_now)
    is_shared_with_caregiver: bool = False


class ConversationMessage(BaseModel):
    id: str | None = None
    conversation_id: str
    sender: str  # "user" or "companion_ai"
    message_text: str
    confidence_score: float | None = None
    sentiment: str | None = None
    intent: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
