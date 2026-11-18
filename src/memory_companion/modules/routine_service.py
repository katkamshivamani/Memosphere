"""Routines and routine completion history."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from memory_companion.modules.audit import AuditService
from memory_companion.modules.common import new_id, utc_now_iso


class RoutineService:
    def __init__(self, db, audit: Optional[AuditService] = None) -> None:
        self._db = db
        self._audit = audit

    def get_routines(self, user_id: str) -> list[dict]:
        rows = self._db.connection().execute(
            "SELECT id, user_id, name, description, schedule_hint, created_at, updated_at "
            "FROM routines WHERE user_id = ? ORDER BY name COLLATE NOCASE",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_routine_history(self, user_id: str, routine_id: str) -> list[dict]:
        rows = self._db.connection().execute(
            "SELECT e.id, e.user_id, e.routine_id, e.status, e.notes, e.occurred_at, "
            "e.created_at, r.name AS routine_name "
            "FROM routine_events e JOIN routines r ON r.id = e.routine_id AND r.user_id = e.user_id "
            "WHERE e.user_id = ? AND e.routine_id = ? ORDER BY e.occurred_at DESC LIMIT 100",
            (user_id, routine_id),
        ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["title"] = f"{item.get('routine_name', 'Routine')} - {item.get('status', '')}"
            results.append(item)
        return results

    def create_routine(self, user_id: str, data: Mapping[str, Any]) -> dict:
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("A routine needs a name.")
        routine_id = new_id("rou")
        now = utc_now_iso()
        with self._db.write() as conn:
            conn.execute(
                "INSERT INTO routines (id, user_id, name, description, schedule_hint, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    routine_id,
                    user_id,
                    name,
                    str(data.get("description") or ""),
                    str(data.get("schedule_hint") or ""),
                    now,
                    now,
                ),
            )
        if self._audit:
            self._audit.log(
                action="routine.create", user_id=user_id, target_type="routine", target_id=routine_id
            )
        return self._get(user_id, routine_id) or {}

    def log_completion(
        self, user_id: str, routine_id: str, *, status: str = "completed", notes: str = ""
    ) -> dict:
        routine = self._get(user_id, routine_id)
        if routine is None:
            raise ValueError("Routine not found for this user.")
        event_id = new_id("rou_evt")
        now = utc_now_iso()
        with self._db.write() as conn:
            conn.execute(
                "INSERT INTO routine_events (id, user_id, routine_id, status, notes, occurred_at, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event_id, user_id, routine_id, status, notes, now, now),
            )
        if self._audit:
            self._audit.log(
                action="routine.log",
                user_id=user_id,
                target_type="routine_event",
                target_id=event_id,
                metadata={"routine_id": routine_id, "status": status},
            )
        return {
            "id": event_id,
            "user_id": user_id,
            "routine_id": routine_id,
            "routine_name": routine.get("name", ""),
            "status": status,
            "notes": notes,
            "occurred_at": now,
            "created_at": now,
        }

    def _get(self, user_id: str, routine_id: str) -> Optional[dict]:
        row = self._db.connection().execute(
            "SELECT id, user_id, name, description, schedule_hint, created_at, updated_at "
            "FROM routines WHERE user_id = ? AND id = ?",
            (user_id, routine_id),
        ).fetchone()
        return dict(row) if row else None

    def count(self, user_id: str) -> int:
        row = self._db.connection().execute(
            "SELECT count(*) FROM routines WHERE user_id = ?", (user_id,)
        ).fetchone()
        return int(row[0]) if row else 0
