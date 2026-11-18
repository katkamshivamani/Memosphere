"""Normalized conversation message models used across the agent."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Timezone-aware UTC timestamp (the only clock used by the agent core)."""
    return datetime.now(timezone.utc)


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Message(BaseModel):
    """A single conversation turn stored in the shared encrypted database."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:16]}")
    conversation_id: str
    role: Role
    content: str
    created_at: datetime = Field(default_factory=utc_now)
    evidence: Optional[dict] = None
    tool_trace: Optional[list[dict]] = None
    error_code: Optional[str] = None

    def to_provider_text(self) -> str:
        return self.content


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: f"conv_{uuid.uuid4().hex[:16]}")
    user_id: str
    title: str = "New conversation"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    context_mode: str = "minimal"

    def preview(self, limit: int = 60) -> str:
        text = self.title.strip() or "Conversation"
        return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
