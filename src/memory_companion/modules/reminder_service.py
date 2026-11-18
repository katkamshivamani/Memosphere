"""Reminders in the shared encrypted database.

The agent never calls the write methods here directly.  They are used by the
UI and by :class:`SuggestionExecutor` after user approval.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from memory_companion.modules.audit import AuditService
from memory_companion.modules.common import new_id, parse_datetime, to_iso, utc_now_iso


class ReminderService:
    def __init__(self, db, audit: Optional[AuditService] = None) -> None:
        self._db = db
        self._audit = audit

    def get_upcoming_reminders(self, user_id: str, horizon_days: int = 7) -> list[dict]:
        horizon = datetime.now(timezone.utc) + timedelta(days=max(1, int(horizon_days)))
        rows = self._db.connection().execute(
            "SELECT id, user_id, title, description, due_at, status, related_type, related_id, "
            "created_at, updated_at FROM reminders "
            "WHERE user_id = ? AND status IN ('scheduled', 'pending') AND due_at <= ? "
            "ORDER BY due_at ASC",
            (user_id, to_iso(horizon)),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_all(self, user_id: str, limit: int = 50) -> list[dict]:
        rows = self._db.connection().execute(
            "SELECT id, user_id, title, description, due_at, status, related_type, related_id, "
            "created_at, updated_at FROM reminders WHERE user_id = ? "
            "ORDER BY due_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def create_reminder(self, user_id: str, reminder_data: Mapping[str, Any]) -> dict:
        title = str(reminder_data.get("title") or "").strip()
        if not title:
            raise ValueError("A reminder needs a title.")
        due = parse_datetime(reminder_data.get("due_at"))
        if due is None:
            raise ValueError("A reminder needs a valid due date/time.")
        reminder_id = str(reminder_data.get("id") or new_id("rem"))
        now = utc_now_iso()
        with self._db.write() as conn:
            conn.execute(
                "INSERT INTO reminders (id, user_id, title, description, due_at, status, "
                "related_type, related_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    reminder_id,
                    user_id,
                    title,
                    str(reminder_data.get("description") or ""),
                    to_iso(due),
                    str(reminder_data.get("status") or "scheduled"),
                    reminder_data.get("related_type"),
                    reminder_data.get("related_id"),
                    now,
                    now,
                ),
            )
        if self._audit:
            self._audit.log(
                action="reminder.create",
                user_id=user_id,
                target_type="reminder",
                target_id=reminder_id,
                metadata={"source": reminder_data.get("source", "manual")},
            )
        return self._get(user_id, reminder_id) or {}

    def mark_done(self, user_id: str, reminder_id: str) -> dict:
        with self._db.write() as conn:
            conn.execute(
                "UPDATE reminders SET status = 'completed', updated_at = ? "
                "WHERE id = ? AND user_id = ?",
                (utc_now_iso(), reminder_id, user_id),
            )
        if self._audit:
            self._audit.log(
                action="reminder.complete",
                user_id=user_id,
                target_type="reminder",
                target_id=reminder_id,
            )
        return self._get(user_id, reminder_id) or {}

    def _get(self, user_id: str, reminder_id: str) -> Optional[dict]:
        row = self._db.connection().execute(
            "SELECT id, user_id, title, description, due_at, status, related_type, related_id, "
            "created_at, updated_at FROM reminders WHERE user_id = ? AND id = ?",
            (user_id, reminder_id),
        ).fetchone()
        return dict(row) if row else None

    def count_upcoming(self, user_id: str, horizon_days: int = 7) -> int:
        return len(self.get_upcoming_reminders(user_id, horizon_days))
