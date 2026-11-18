"""Audit logging in the shared encrypted database.

Only actions and non-sensitive metadata are recorded.  Contents of memories and
credentials never enter the audit log.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from memory_agent.security.data_filter import redact_value


class AuditService:
    def __init__(self, db) -> None:
        self._db = db

    def log(
        self,
        *,
        action: str,
        user_id: Optional[str] = None,
        actor: str = "user",
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        safe_metadata = redact_value(metadata or {})
        with self._db.write() as conn:
            conn.execute(
                "INSERT INTO audit_log (user_id, actor, action, target_type, target_id, "
                "metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    actor,
                    action,
                    target_type,
                    target_id,
                    json.dumps(safe_metadata, ensure_ascii=False, default=str),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def recent(self, user_id: str, limit: int = 50) -> list[dict]:
        rows = self._db.connection().execute(
            "SELECT action, target_type, target_id, actor, created_at, metadata_json "
            "FROM audit_log WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [
            {
                "action": row[0],
                "target_type": row[1],
                "target_id": row[2],
                "actor": row[3],
                "created_at": row[4],
                "metadata": json.loads(row[5] or "{}"),
            }
            for row in rows
        ]
