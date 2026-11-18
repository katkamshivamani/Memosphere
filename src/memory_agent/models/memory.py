"""Normalized record representation shared by every integration adapter.

The agent never invents identifiers or timestamps: every value in a
:class:`Record` is copied from the source service response.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field


class RecordType(str, Enum):
    MEMORY = "memory"
    PERSON = "person"
    RELATIONSHIP = "relationship"
    PLACE = "place"
    ACTIVITY = "activity"
    ROUTINE = "routine"
    ROUTINE_EVENT = "routine_event"
    REMINDER = "reminder"


class SourceRef(BaseModel):
    """Provenance pointer for a piece of evidence shown to the user."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    record_type: RecordType
    source_module: str
    title: str
    timestamp: Optional[str] = None

    def describe(self) -> str:
        when = f" ({self.timestamp})" if self.timestamp else ""
        return f"{self.title}{when}"


class Record(BaseModel):
    """Provider-independent view of one application record."""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    type: RecordType
    title: str
    content: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    source_module: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    flagged_untrusted: bool = False

    def source_ref(self) -> SourceRef:
        stamp = self.updated_at or self.created_at
        return SourceRef(
            record_id=self.id,
            record_type=self.type,
            source_module=self.source_module,
            title=self.title,
            timestamp=stamp.isoformat() if stamp else None,
        )


def coerce_datetime(value: Any) -> Optional[datetime]:
    """Best-effort datetime coercion that never fabricates a value."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def record_from_mapping(
    raw: Mapping[str, Any],
    *,
    record_type: RecordType,
    source_module: str,
    user_id: str,
) -> Record:
    """Translate a service-layer mapping into a :class:`Record` without invention.

    ``raw`` must contain an ``id``.  Missing optional fields stay missing.
    """
    record_id = raw.get("id")
    if not record_id:
        raise ValueError(f"{source_module} returned a record without an id")

    created = coerce_datetime(raw.get("created_at"))
    updated = coerce_datetime(raw.get("updated_at"))

    metadata = dict(raw.get("metadata") or {})
    for key in ("category", "status", "due_at", "occurred_at", "relationship", "role"):
        if key in raw and raw[key] is not None and key not in metadata:
            metadata[key] = raw[key]

    title = raw.get("title") or raw.get("name") or raw.get("label") or ""
    content = (
        raw.get("content")
        or raw.get("description")
        or raw.get("notes")
        or ""
    )
    return Record(
        id=str(record_id),
        user_id=str(raw.get("user_id") or user_id),
        type=record_type,
        title=str(title),
        content=str(content),
        created_at=created,
        updated_at=updated,
        source_module=source_module,
        metadata=metadata,
    )
