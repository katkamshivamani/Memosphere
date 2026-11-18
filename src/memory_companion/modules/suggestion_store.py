"""SQL implementation of the agent's SuggestionStore contract."""

from __future__ import annotations

import json
from typing import Optional

from memory_agent.models.suggestion import Suggestion, SuggestionStatus, SuggestionType
from memory_agent.services.suggestion_service import SuggestionStore
from memory_companion.modules.common import utc_now_iso


class SqlSuggestionStore(SuggestionStore):
    def __init__(self, db) -> None:
        self._db = db

    def add(self, suggestion: Suggestion) -> Suggestion:
        with self._db.write() as conn:
            conn.execute(
                "INSERT INTO agent_suggestions (id, user_id, conversation_id, type, title, "
                "description, reason, payload_json, status, error, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    suggestion.id,
                    suggestion.user_id,
                    suggestion.conversation_id,
                    suggestion.type.value,
                    suggestion.title,
                    suggestion.description,
                    suggestion.reason,
                    json.dumps(suggestion.payload, ensure_ascii=False, default=str),
                    suggestion.status.value,
                    suggestion.error,
                    suggestion.created_at.isoformat(),
                    suggestion.updated_at.isoformat(),
                ),
            )
        return suggestion

    def update(self, suggestion: Suggestion) -> Suggestion:
        with self._db.write() as conn:
            conn.execute(
                "UPDATE agent_suggestions SET title = ?, description = ?, reason = ?, "
                "payload_json = ?, status = ?, error = ?, updated_at = ? "
                "WHERE id = ? AND user_id = ?",
                (
                    suggestion.title,
                    suggestion.description,
                    suggestion.reason,
                    json.dumps(suggestion.payload, ensure_ascii=False, default=str),
                    suggestion.status.value,
                    suggestion.error,
                    utc_now_iso(),
                    suggestion.id,
                    suggestion.user_id,
                ),
            )
        return suggestion

    def get(self, user_id: str, suggestion_id: str) -> Optional[Suggestion]:
        row = self._db.connection().execute(
            "SELECT id, user_id, conversation_id, type, title, description, reason, payload_json, "
            "status, error, created_at, updated_at FROM agent_suggestions "
            "WHERE id = ? AND user_id = ?",
            (suggestion_id, user_id),
        ).fetchone()
        return self._row_to_model(row) if row else None

    def list(self, user_id: str, status: Optional[SuggestionStatus] = None) -> list[Suggestion]:
        sql = (
            "SELECT id, user_id, conversation_id, type, title, description, reason, payload_json, "
            "status, error, created_at, updated_at FROM agent_suggestions WHERE user_id = ?"
        )
        params: list = [user_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status.value)
        sql += " ORDER BY created_at DESC"
        rows = self._db.connection().execute(sql, params).fetchall()
        return [self._row_to_model(row) for row in rows]

    @staticmethod
    def _row_to_model(row) -> Suggestion:
        return Suggestion(
            id=row["id"],
            user_id=row["user_id"],
            conversation_id=row["conversation_id"],
            type=SuggestionType(row["type"]),
            title=row["title"],
            description=row["description"],
            reason=row["reason"],
            payload=json.loads(row["payload_json"] or "{}"),
            status=SuggestionStatus(row["status"]),
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
