"""Suggestion model: the only pathway from AI output to a write action.

A suggestion is *data*.  It never executes anything by itself.  Only
:class:`memory_agent.services.suggestion_service.SuggestionService` may execute
an approved suggestion, after an explicit user action in the UI.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from memory_agent.models.message import utc_now


class SuggestionType(str, Enum):
    SAVE_MEMORY = "save_memory"
    UPDATE_MEMORY = "update_memory"
    CREATE_REMINDER = "create_reminder"
    ADD_ACTIVITY = "add_activity"
    CLARIFY_RECORD = "clarify_record"


class SuggestionStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"


class Suggestion(BaseModel):
    """A proposed change that requires explicit user approval."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: f"suggestion_{uuid.uuid4().hex[:12]}")
    user_id: str = ""
    conversation_id: Optional[str] = None
    type: SuggestionType
    title: str
    description: str = ""
    reason: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    status: SuggestionStatus = SuggestionStatus.PENDING_APPROVAL
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    error: Optional[str] = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Suggestion title must not be blank")
        return value.strip()

    def is_pending(self) -> bool:
        return self.status is SuggestionStatus.PENDING_APPROVAL

    def apply_edit(self, *, title: Optional[str] = None, description: Optional[str] = None,
                   payload_updates: Optional[dict[str, Any]] = None) -> "Suggestion":
        """Return a copy with user edits applied (still pending approval)."""
        data = self.model_dump()
        if title is not None:
            data["title"] = title
        if description is not None:
            data["description"] = description
        if payload_updates:
            merged = dict(data.get("payload") or {})
            merged.update(payload_updates)
            data["payload"] = merged
        data["updated_at"] = utc_now()
        return Suggestion.model_validate(data)
