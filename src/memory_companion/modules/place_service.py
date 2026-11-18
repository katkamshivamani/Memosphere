"""Places in the shared encrypted database."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from memory_companion.modules.audit import AuditService
from memory_companion.modules.common import like_clause, new_id, search_tokens, utc_now_iso


class PlaceService:
    def __init__(self, db, audit: Optional[AuditService] = None) -> None:
        self._db = db
        self._audit = audit

    def search_places(self, user_id: str, query: str) -> list[dict]:
        sql = (
            "SELECT id, user_id, name, category, description, created_at, updated_at "
            "FROM places WHERE user_id = ?"
        )
        params: list[Any] = [user_id]
        clause, clause_params = like_clause(("name", "category", "description"), search_tokens(query))
        if clause:
            sql += f" AND {clause}"
            params.extend(clause_params)
        sql += " ORDER BY name COLLATE NOCASE LIMIT 25"
        return [dict(row) for row in self._db.connection().execute(sql, params).fetchall()]

    def get_place_details(self, user_id: str, place_id: str) -> Optional[dict]:
        row = self._db.connection().execute(
            "SELECT id, user_id, name, category, description, created_at, updated_at "
            "FROM places WHERE user_id = ? AND id = ?",
            (user_id, place_id),
        ).fetchone()
        return dict(row) if row else None

    def create_place(self, user_id: str, data: Mapping[str, Any]) -> dict:
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("A place needs a name.")
        place_id = new_id("place")
        now = utc_now_iso()
        with self._db.write() as conn:
            conn.execute(
                "INSERT INTO places (id, user_id, name, category, description, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    place_id,
                    user_id,
                    name,
                    str(data.get("category") or "place"),
                    str(data.get("description") or ""),
                    now,
                    now,
                ),
            )
        if self._audit:
            self._audit.log(
                action="place.create", user_id=user_id, target_type="place", target_id=place_id
            )
        return self.get_place_details(user_id, place_id) or {}

    def count(self, user_id: str) -> int:
        row = self._db.connection().execute(
            "SELECT count(*) FROM places WHERE user_id = ?", (user_id,)
        ).fetchone()
        return int(row[0]) if row else 0
