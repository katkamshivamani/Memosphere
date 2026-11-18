"""
Routine and Habit Tracking Repository with status logging, missed routine detection, and caregiver filtering.
"""
import json
import uuid
from datetime import date

from local_security.access_control.permission_manager import PermissionManager
from local_security.core.exceptions import RecordNotFoundError
from local_security.database.database_manager import DatabaseManager
from local_security.models.permissions import SecurityAction, SecurityModule
from local_security.models.records import (
    RoutineFrequency,
    RoutineLogRecord,
    RoutineLogStatus,
    RoutineRecord,
    utc_now,
)
from local_security.models.users import UserRole


class RoutineRepository:
    """Manages routines, habits, adherence logs, and escalation monitoring."""

    def __init__(self, db_manager: DatabaseManager, permission_manager: PermissionManager | None = None):
        self._db = db_manager
        self._perms = permission_manager or PermissionManager()

    def _row_to_routine(self, row) -> RoutineRecord:
        return RoutineRecord(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            frequency=RoutineFrequency(row["frequency"]),
            time_of_day=row["time_of_day"],
            is_shared_with_caregiver=bool(row["is_shared_with_caregiver"]),
            is_active=bool(row["is_active"]),
            metadata=json.loads(row["metadata_json"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_log(self, row) -> RoutineLogRecord:
        return RoutineLogRecord(
            id=row["id"],
            routine_id=row["routine_id"],
            scheduled_date=date.fromisoformat(row["scheduled_date"]),
            status=RoutineLogStatus(row["status"]),
            notes=row["notes"],
            logged_at=row["logged_at"],
            is_shared_with_caregiver=bool(row["is_shared_with_caregiver"]),
        )

    def save_routine(self, routine: RoutineRecord, role: UserRole = UserRole.OWNER) -> str:
        self._perms.check_access(SecurityModule.ROUTINES, SecurityAction.CREATE, role=role)
        r_id = routine.id or str(uuid.uuid4())
        now_str = utc_now().isoformat()
        created_str = routine.created_at.isoformat() if hasattr(routine.created_at, "isoformat") else str(routine.created_at)

        with self._db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO routines (
                    id, title, description, frequency, time_of_day,
                    is_shared_with_caregiver, is_active, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    r_id,
                    routine.title,
                    routine.description,
                    routine.frequency.value,
                    routine.time_of_day,
                    int(routine.is_shared_with_caregiver),
                    int(routine.is_active),
                    json.dumps(routine.metadata),
                    created_str,
                    now_str,
                )
            )
        return r_id

    def get_routine(self, routine_id: str, role: UserRole = UserRole.OWNER) -> RoutineRecord | None:
        cur = self._db.cursor()
        cur.execute("SELECT * FROM routines WHERE id = ?;", (routine_id,))
        row = cur.fetchone()
        if not row:
            return None

        is_shared = bool(row["is_shared_with_caregiver"])
        self._perms.check_access(
            SecurityModule.ROUTINES,
            SecurityAction.READ,
            role=role,
            is_shared_with_caregiver=is_shared
        )
        return self._row_to_routine(row)

    def update_routine(self, routine_id: str, updates: dict, role: UserRole = UserRole.OWNER) -> RoutineRecord:
        existing = self.get_routine(routine_id, role=role)
        if not existing:
            raise RecordNotFoundError(f"Routine '{routine_id}' not found.")

        self._perms.check_access(
            SecurityModule.ROUTINES,
            SecurityAction.UPDATE,
            role=role,
            is_shared_with_caregiver=existing.is_shared_with_caregiver
        )

        title = updates.get("title", existing.title)
        description = updates.get("description", existing.description)
        freq = updates.get("frequency", existing.frequency)
        freq_val = freq.value if isinstance(freq, RoutineFrequency) else str(freq)
        time_of_day = updates.get("time_of_day", existing.time_of_day)
        is_shared = updates.get("is_shared_with_caregiver", existing.is_shared_with_caregiver)
        is_active = updates.get("is_active", existing.is_active)
        meta = updates.get("metadata", existing.metadata)
        now_str = utc_now().isoformat()

        with self._db.transaction() as cur:
            cur.execute(
                """
                UPDATE routines SET
                    title = ?, description = ?, frequency = ?, time_of_day = ?,
                    is_shared_with_caregiver = ?, is_active = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?;
                """,
                (title, description, freq_val, time_of_day, int(is_shared), int(is_active), json.dumps(meta), now_str, routine_id)
            )
        return self.get_routine(routine_id, role=role)  # type: ignore

    def delete_routine(self, routine_id: str, role: UserRole = UserRole.OWNER) -> bool:
        self._perms.check_access(SecurityModule.ROUTINES, SecurityAction.DELETE, role=role)
        with self._db.transaction() as cur:
            cur.execute("DELETE FROM routines WHERE id = ?;", (routine_id,))
            return cur.rowcount > 0

    def log_routine_status(self, log: RoutineLogRecord, role: UserRole = UserRole.OWNER) -> str:
        """Records status of routine execution (completed, missed, skipped)."""
        self._perms.check_access(SecurityModule.ROUTINES, SecurityAction.UPDATE, role=role)
        log_id = log.id or str(uuid.uuid4())
        logged_str = log.logged_at.isoformat() if hasattr(log.logged_at, "isoformat") else str(log.logged_at)
        sched_date_str = log.scheduled_date.isoformat() if hasattr(log.scheduled_date, "isoformat") else str(log.scheduled_date)

        # Look up parent routine's caregiver sharing setting
        cur = self._db.cursor()
        cur.execute("SELECT is_shared_with_caregiver FROM routines WHERE id = ?;", (log.routine_id,))
        row = cur.fetchone()
        is_shared = bool(row[0]) if row else log.is_shared_with_caregiver

        with self._db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO routine_logs (id, routine_id, scheduled_date, status, notes, logged_at, is_shared_with_caregiver)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (log_id, log.routine_id, sched_date_str, log.status.value, log.notes, logged_str, int(is_shared))
            )
        return log_id

    def get_routine_logs(self, routine_id: str, role: UserRole = UserRole.OWNER, limit: int = 30) -> list[RoutineLogRecord]:
        self._perms.check_access(SecurityModule.ROUTINES, SecurityAction.READ, role=role)
        cur = self._db.cursor()
        cur.execute(
            "SELECT * FROM routine_logs WHERE routine_id = ? ORDER BY scheduled_date DESC LIMIT ?;",
            (routine_id, limit)
        )
        return [self._row_to_log(row) for row in cur.fetchall()]

    def get_missed_routines(self, for_date: date, role: UserRole = UserRole.OWNER) -> list[RoutineRecord]:
        """Finds all active daily routines that do NOT have a 'completed' log for for_date."""
        self._perms.check_access(SecurityModule.ROUTINES, SecurityAction.READ, role=role)
        date_str = for_date.isoformat()
        cur = self._db.cursor()
        cur.execute(
            """
            SELECT r.* FROM routines r
            WHERE r.is_active = 1
            AND r.id NOT IN (
                SELECT rl.routine_id FROM routine_logs rl
                WHERE rl.scheduled_date = ? AND rl.status = 'completed'
            );
            """,
            (date_str,)
        )
        return [self._row_to_routine(row) for row in cur.fetchall()]

    def get_routines_for_caregiver(self) -> list[RoutineRecord]:
        """Returns only routines authorized for caregiver sharing."""
        cur = self._db.cursor()
        cur.execute("SELECT * FROM routines WHERE is_shared_with_caregiver = 1 AND is_active = 1;")
        return [self._row_to_routine(row) for row in cur.fetchall()]
