"""Activity history in the shared encrypted database."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional

from memory_companion.modules.audit import AuditService
from memory_companion.modules.common import (
    like_clause,
    new_id,
    parse_datetime,
    search_tokens,
    to_iso,
    utc_now_iso,
)


class ActivityService:
    def __init__(self, db, audit: Optional[AuditService] = None) -> None:
        self._db = db
        self._audit = audit

    def get_activity_history(
        self,
        user_id: str,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list[dict]:
        sql = (
            "SELECT id, user_id, name, description, occurred_at, place_id, created_at, updated_at "
            "FROM activities WHERE user_id = ?"
        )
        params: list[Any] = [user_id]
        if date_from is not None:
            sql += " AND occurred_at >= ?"
            params.append(to_iso(date_from))
        if date_to is not None:
            sql += " AND occurred_at <= ?"
            params.append(to_iso(date_to))
        sql += " ORDER BY occurred_at DESC LIMIT 100"
        return [dict(row) for row in self._db.connection().execute(sql, params).fetchall()]

    def search_activities(
        self,
        user_id: str,
        query: str,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list[dict]:
        sql = (
            "SELECT id, user_id, name, description, occurred_at, place_id, created_at, updated_at "
            "FROM activities WHERE user_id = ?"
        )
        params: list[Any] = [user_id]
        if date_from is not None:
            sql += " AND occurred_at >= ?"
            params.append(to_iso(date_from))
        if date_to is not None:
            sql += " AND occurred_at <= ?"
            params.append(to_iso(date_to))
        clause, clause_params = like_clause(("name", "description"), search_tokens(query))
        if clause:
            sql += f" AND {clause}"
            params.extend(clause_params)
        sql += " ORDER BY occurred_at DESC LIMIT 50"
        return [dict(row) for row in self._db.connection().execute(sql, params).fetchall()]

    def create_activity(self, user_id: str, data: Mapping[str, Any]) -> dict:
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("An activity needs a name.")
        occurred = parse_datetime(data.get("occurred_at")) or datetime.now().astimezone()
        activity_id = new_id("act")
        now = utc_now_iso()
        with self._db.write() as conn:
            conn.execute(
                "INSERT INTO activities (id, user_id, name, description, occurred_at, place_id, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    activity_id,
                    user_id,
                    name,
                    str(data.get("description") or ""),
                    to_iso(occurred),
                    data.get("place_id"),
                    now,
                    now,
                ),
            )
        if self._audit:
            self._audit.log(
                action="activity.create",
                user_id=user_id,
                target_type="activity",
                target_id=activity_id,
            )
        return self._get(user_id, activity_id) or {}

    def _get(self, user_id: str, activity_id: str) -> Optional[dict]:
        row = self._db.connection().execute(
            "SELECT id, user_id, name, description, occurred_at, place_id, created_at, updated_at "
            "FROM activities WHERE user_id = ? AND id = ?",
            (user_id, activity_id),
        ).fetchone()
        return dict(row) if row else None

    def count(self, user_id: str) -> int:
        row = self._db.connection().execute(
            "SELECT count(*) FROM activities WHERE user_id = ?", (user_id,)
        ).fetchone()
        return int(row[0]) if row else 0
