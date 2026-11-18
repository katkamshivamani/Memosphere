"""Consent tracking for context sharing and cloud audio transcription.

Consent state is configuration metadata (scope, timestamp, categories) - it
contains no personal memories, so a JSON file is acceptable.  Every change is
mirrored to an audit hook provided by the application so it lands in the shared
encrypted audit log.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict, Field


class ConsentScope(str, Enum):
    FULL_CONTEXT = "full_authorized_context"
    CLOUD_TRANSCRIPTION = "cloud_transcription"


class ConsentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: ConsentScope
    granted_at: datetime
    withdrawn_at: Optional[datetime] = None
    categories: list[str] = Field(default_factory=list)
    version: str = "1"

    def is_active(self) -> bool:
        return self.withdrawn_at is None


AuditHook = Callable[[str, dict], None]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ConsentManager:
    """Persisted consent flags with grant/withdraw history."""

    def __init__(self, path: str | Path, audit_hook: Optional[AuditHook] = None) -> None:
        self.path = Path(path)
        self._audit = audit_hook
        self._lock = threading.RLock()
        self._records = self._load()

    # -- persistence ----------------------------------------------------- #
    def _load(self) -> dict[str, ConsentRecord]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            records: dict[str, ConsentRecord] = {}
            for item in raw.get("records", []):
                record = ConsentRecord.model_validate(item)
                records[record.scope.value] = record
            return records
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "records": [record.model_dump(mode="json") for record in self._records.values()],
        }
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def _emit(self, action: str, record: ConsentRecord) -> None:
        if self._audit is None:
            return
        try:
            self._audit(
                action,
                {
                    "scope": record.scope.value,
                    "categories": record.categories,
                    "granted_at": record.granted_at.isoformat(),
                    "withdrawn_at": record.withdrawn_at.isoformat() if record.withdrawn_at else None,
                },
            )
        except Exception:  # audit failure must not break consent handling
            pass

    # -- API ------------------------------------------------------------- #
    def grant(self, scope: ConsentScope, categories: Optional[list[str]] = None) -> ConsentRecord:
        with self._lock:
            existing = self._records.get(scope.value)
            record = ConsentRecord(
                scope=scope,
                granted_at=existing.granted_at if existing and existing.is_active() else _now(),
                categories=sorted(set(categories or (existing.categories if existing else []))),
            )
            self._records[scope.value] = record
            self._save()
            self._emit("consent_granted", record)
            return record

    def revoke(self, scope: ConsentScope) -> Optional[ConsentRecord]:
        with self._lock:
            existing = self._records.get(scope.value)
            if existing is None or not existing.is_active():
                return existing
            updated = existing.model_copy(update={"withdrawn_at": _now()})
            self._records[scope.value] = updated
            self._save()
            self._emit("consent_withdrawn", updated)
            return updated

    def is_granted(self, scope: ConsentScope) -> bool:
        record = self._records.get(scope.value)
        return bool(record and record.is_active())

    def get(self, scope: ConsentScope) -> Optional[ConsentRecord]:
        return self._records.get(scope.value)

    def summary(self) -> dict[str, dict]:
        return {
            scope.value: {
                "granted": self.is_granted(scope),
                "record": self._records[scope.value].model_dump(mode="json")
                if scope.value in self._records
                else None,
            }
            for scope in ConsentScope
        }
