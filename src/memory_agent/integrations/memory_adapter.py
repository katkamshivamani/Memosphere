"""Adapters that translate host application services into normalized records.

Adapters are intentionally read-only.  They never expose create/update/delete to
the tool layer; approved writes go through the host's ``SuggestionExecutor``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

from memory_agent.core.exceptions import StorageUnavailableError
from memory_agent.models.memory import Record, RecordType, record_from_mapping

_MAX_RECORDS = 50


def _safe_call(source: str, method_name: str, func, *args, **kwargs) -> Sequence[Mapping[str, Any]]:
    try:
        result = func(*args, **kwargs)
    except Exception as exc:  # host errors must not leak internals
        raise StorageUnavailableError(
            f"{source}.{method_name} failed: {exc}",
        ) from exc
    return list(result or [])


def _single(mapping: Optional[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    if mapping is None:
        return None
    return dict(mapping)


class _BaseAdapter:
    source_module: str
    record_type: RecordType
    service: Any

    def _records(self, rows: Sequence[Mapping[str, Any]], user_id: str) -> list[Record]:
        records: list[Record] = []
        for row in rows[:_MAX_RECORDS]:
            try:
                record = record_from_mapping(
                    dict(row),
                    record_type=self.record_type,
                    source_module=self.source_module,
                    user_id=user_id,
                )
            except (ValueError, TypeError):
                # A malformed row is skipped rather than fabricated.
                continue
            if record.user_id != user_id:
                # Cross-user leakage guard: never surface another user's record.
                continue
            records.append(record)
        return records


class MemoryAdapter(_BaseAdapter):
    source_module = "memories"
    record_type = RecordType.MEMORY

    def __init__(self, service: Any) -> None:
        self.service = service

    def search(self, user_id: str, query: str, filters: Optional[Mapping[str, Any]] = None) -> list[Record]:
        rows = _safe_call(self.source_module, "search_memories", self.service.search_memories, user_id, query, filters)
        return self._records(rows, user_id)

    def get(self, user_id: str, memory_id: str) -> Optional[Record]:
        row = _single(_safe_call_single(self.service.get_memory, user_id, memory_id))
        if row is None:
            return None
        records = self._records([row], user_id)
        return records[0] if records else None


class PeopleAdapter(_BaseAdapter):
    source_module = "people"
    record_type = RecordType.PERSON

    def __init__(self, service: Any) -> None:
        self.service = service

    def search(self, user_id: str, query: str) -> list[Record]:
        rows = _safe_call(self.source_module, "search_people", self.service.search_people, user_id, query)
        return self._records(rows, user_id)

    def get(self, user_id: str, person_id: str) -> Optional[Record]:
        getter = getattr(self.service, "get_person", None)
        if callable(getter):
            row = _single(_safe_call_single(getter, user_id, person_id))
        else:  # graceful degradation for services without get_person
            matches = self.search(user_id, person_id)
            row = next((m.model_dump() for m in matches if m.id == person_id), None)
        if row is None:
            return None
        records = self._records([row], user_id)
        return records[0] if records else None

    def relationships(self, user_id: str, person_id: str) -> tuple[list[Record], Optional[Record]]:
        rows = _safe_call(
            self.source_module, "get_relationships", self.service.get_relationships, user_id, person_id
        )
        person = self.get(user_id, person_id)
        relationship_records: list[Record] = []
        for row in rows:
            data = dict(row)
            data.setdefault("id", f"rel_{person_id}_{len(relationship_records)}")
            try:
                record = record_from_mapping(
                    data,
                    record_type=RecordType.RELATIONSHIP,
                    source_module=self.source_module,
                    user_id=user_id,
                )
            except (ValueError, TypeError):
                continue
            if record.user_id != user_id:
                continue
            relationship_records.append(record)
        return relationship_records, person


class PlaceAdapter(_BaseAdapter):
    source_module = "places"
    record_type = RecordType.PLACE

    def __init__(self, service: Any) -> None:
        self.service = service

    def search(self, user_id: str, query: str) -> list[Record]:
        rows = _safe_call(self.source_module, "search_places", self.service.search_places, user_id, query)
        return self._records(rows, user_id)

    def get(self, user_id: str, place_id: str) -> Optional[Record]:
        row = _single(_safe_call_single(self.service.get_place_details, user_id, place_id))
        if row is None:
            return None
        records = self._records([row], user_id)
        return records[0] if records else None


class ActivityAdapter(_BaseAdapter):
    source_module = "activities"
    record_type = RecordType.ACTIVITY

    def __init__(self, service: Any) -> None:
        self.service = service

    def history(
        self,
        user_id: str,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list[Record]:
        rows = _safe_call(
            self.source_module,
            "get_activity_history",
            self.service.get_activity_history,
            user_id,
            date_from,
            date_to,
        )
        records = self._records(rows, user_id)
        return sorted(records, key=_sort_stamp, reverse=True)

    def search(
        self,
        user_id: str,
        query: str,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list[Record]:
        rows = _safe_call(
            self.source_module,
            "search_activities",
            self.service.search_activities,
            user_id,
            query,
            date_from,
            date_to,
        )
        return self._records(rows, user_id)


class RoutineAdapter(_BaseAdapter):
    source_module = "routines"
    record_type = RecordType.ROUTINE

    def __init__(self, service: Any) -> None:
        self.service = service

    def routines(self, user_id: str) -> list[Record]:
        rows = _safe_call(self.source_module, "get_routines", self.service.get_routines, user_id)
        return self._records(rows, user_id)

    def history(self, user_id: str, routine_id: str) -> list[Record]:
        rows = _safe_call(
            self.source_module, "get_routine_history", self.service.get_routine_history, user_id, routine_id
        )
        records: list[Record] = []
        for row in rows[:_MAX_RECORDS]:
            data = dict(row)
            data.setdefault("id", f"routine_event_{routine_id}_{len(records)}")
            data.setdefault("title", data.get("routine_name") or f"Routine event for {routine_id}")
            try:
                record = record_from_mapping(
                    data,
                    record_type=RecordType.ROUTINE_EVENT,
                    source_module=self.source_module,
                    user_id=user_id,
                )
            except (ValueError, TypeError):
                continue
            if record.user_id == user_id:
                records.append(record)
        return sorted(records, key=_sort_stamp, reverse=True)


class ReminderAdapter(_BaseAdapter):
    source_module = "reminders"
    record_type = RecordType.REMINDER

    def __init__(self, service: Any) -> None:
        self.service = service

    def upcoming(self, user_id: str, horizon_days: int = 7) -> list[Record]:
        rows = _safe_call(
            self.source_module,
            "get_upcoming_reminders",
            self.service.get_upcoming_reminders,
            user_id,
            horizon_days,
        )
        records = self._records(rows, user_id)
        return sorted(records, key=_sort_stamp)


def _safe_call_single(func, *args) -> Optional[Mapping[str, Any]]:
    try:
        return func(*args)
    except Exception as exc:
        raise StorageUnavailableError(f"Service lookup failed: {exc}") from exc


def _sort_stamp(record: Record) -> str:
    stamp = record.metadata.get("occurred_at") or record.metadata.get("due_at")
    if not stamp:
        stamp = record.updated_at.isoformat() if record.updated_at else record.created_at.isoformat() if record.created_at else ""
    return str(stamp)
