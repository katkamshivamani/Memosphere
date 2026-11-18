"""Memory records in the shared encrypted database."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from memory_agent.core.exceptions import RecordNotFoundError

from memory_companion.modules.audit import AuditService
from memory_companion.modules.common import like_clause, new_id, search_tokens, utc_now_iso


class MemoryService:
    """Implements the agent's MemoryServiceProtocol for the real database."""

    def __init__(self, db, audit: Optional[AuditService] = None) -> None:
        self._db = db
        self._audit = audit

    def _list(self, sql: str, params: Sequence[Any]) -> list[dict]:
        rows = self._db.connection().execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def search_memories(
        self, user_id: str, query: str, filters: Optional[Mapping[str, Any]] = None
    ) -> list[dict]:
        filters = filters or {}
        sql = (
            "SELECT id, user_id, title, content, category, created_at, updated_at "
            "FROM memories WHERE user_id = ?"
        )
        params: list[Any] = [user_id]
        if filters.get("category"):
            sql += " AND category = ?"
            params.append(str(filters["category"]))
        clause, clause_params = like_clause(("title", "content", "category"), search_tokens(query))
        if clause:
            sql += f" AND {clause}"
            params.extend(clause_params)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(int(filters.get("limit", 20)))
        return self._list(sql, params)

    def get_memory(self, user_id: str, memory_id: str) -> Optional[dict]:
        row = self._db.connection().execute(
            "SELECT id, user_id, title, content, category, created_at, updated_at "
            "FROM memories WHERE user_id = ? AND id = ?",
            (user_id, memory_id),
        ).fetchone()
        return dict(row) if row else None

    def create_memory(self, user_id: str, memory_data: Mapping[str, Any]) -> dict:
        title = str(memory_data.get("title") or "").strip()
        if not title:
            raise ValueError("A memory needs a title.")
        memory_id = str(memory_data.get("id") or new_id("mem"))
        now = utc_now_iso()
        with self._db.write() as conn:
            conn.execute(
                "INSERT INTO memories (id, user_id, title, content, category, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    memory_id,
                    user_id,
                    title,
                    str(memory_data.get("content") or ""),
                    str(memory_data.get("category") or "general"),
                    now,
                    now,
                ),
            )
        if self._audit:
            self._audit.log(
                action="memory.create",
                user_id=user_id,
                target_type="memory",
                target_id=memory_id,
            )
        return self.get_memory(user_id, memory_id) or {}

    def update_memory(self, user_id: str, memory_id: str, updates: Mapping[str, Any]) -> dict:
        existing = self.get_memory(user_id, memory_id)
        if existing is None:
            raise RecordNotFoundError("Memory not found for this user.")
        allowed = {key: updates[key] for key in ("title", "content", "category") if key in updates}
        if not allowed:
            return existing
        assignments = ", ".join(f"{column} = ?" for column in allowed)
        values = list(allowed.values()) + [utc_now_iso(), memory_id, user_id]
        with self._db.write() as conn:
            conn.execute(
                f"UPDATE memories SET {assignments}, updated_at = ? WHERE id = ? AND user_id = ?",
                values,
            )
        if self._audit:
            self._audit.log(
                action="memory.update",
                user_id=user_id,
                target_type="memory",
                target_id=memory_id,
                metadata={"fields": sorted(allowed)},
            )
        return self.get_memory(user_id, memory_id) or {}

    def list_recent(self, user_id: str, limit: int = 8) -> list[dict]:
        return self._list(
            "SELECT id, user_id, title, content, category, created_at, updated_at "
            "FROM memories WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
            (user_id, limit),
        )

    def count(self, user_id: str) -> int:
        row = self._db.connection().execute(
            "SELECT count(*) FROM memories WHERE user_id = ?", (user_id,)
        ).fetchone()
        return int(row[0]) if row else 0
