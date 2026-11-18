"""
Activity and Daily Action Log Repository with consistency summaries.
"""
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from local_security.access_control.permission_manager import PermissionManager
from local_security.database.database_manager import DatabaseManager
from local_security.models.permissions import SecurityAction, SecurityModule
from local_security.models.records import ActivityRecord
from local_security.models.users import UserRole


class ActivityRepository:
    """Manages activity logs, action histories, and weekly consistency reports."""

    def __init__(self, db_manager: DatabaseManager, permission_manager: PermissionManager | None = None):
        self._db = db_manager
        self._perms = permission_manager or PermissionManager()

    def _row_to_activity(self, row) -> ActivityRecord:
        return ActivityRecord(
            id=row["id"],
            activity_name=row["activity_name"],
            category=row["category"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            notes=row["notes"],
            is_shared_with_caregiver=bool(row["is_shared_with_caregiver"]),
            metadata=json.loads(row["metadata_json"] or "{}"),
            created_at=row["created_at"],
        )

    def save_activity(self, activity: ActivityRecord, role: UserRole = UserRole.OWNER) -> str:
        self._perms.check_access(SecurityModule.ACTIVITIES, SecurityAction.CREATE, role=role)
        act_id = activity.id or str(uuid.uuid4())
        created_str = activity.created_at.isoformat() if hasattr(activity.created_at, "isoformat") else str(activity.created_at)
        started_str = activity.started_at.isoformat() if hasattr(activity.started_at, "isoformat") else str(activity.started_at)
        ended_str = activity.ended_at.isoformat() if activity.ended_at and hasattr(activity.ended_at, "isoformat") else (activity.ended_at or None)

        with self._db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO activities (
                    id, activity_name, category, started_at, ended_at,
                    notes, is_shared_with_caregiver, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    act_id,
                    activity.activity_name,
                    activity.category,
                    started_str,
                    ended_str,
                    activity.notes,
                    int(activity.is_shared_with_caregiver),
                    json.dumps(activity.metadata),
                    created_str,
                )
            )
        return act_id

    def get_activity_history(
        self,
        limit: int = 50,
        role: UserRole = UserRole.OWNER,
        category: str | None = None
    ) -> list[ActivityRecord]:
        self._perms.check_access(SecurityModule.ACTIVITIES, SecurityAction.READ, role=role)
        cur = self._db.cursor()

        if category:
            cur.execute(
                "SELECT * FROM activities WHERE category = ? ORDER BY started_at DESC LIMIT ?;",
                (category, limit)
            )
        else:
            cur.execute("SELECT * FROM activities ORDER BY started_at DESC LIMIT ?;", (limit,))

        rows = cur.fetchall()
        activities = []
        for row in rows:
            is_shared = bool(row["is_shared_with_caregiver"])
            if self._perms.check_access(
                SecurityModule.ACTIVITIES,
                SecurityAction.READ,
                role=role,
                is_shared_with_caregiver=is_shared,
                raise_exception=False,
            ):
                activities.append(self._row_to_activity(row))
        return activities

    def get_weekly_consistency_summary(self, role: UserRole = UserRole.OWNER) -> dict[str, Any]:
        """Calculates 7-day activity metrics for the user or caregiver dashboard."""
        self._perms.check_access(SecurityModule.ACTIVITIES, SecurityAction.READ, role=role)
        now = datetime.now(UTC)
        week_ago = (now - timedelta(days=7)).isoformat()

        cur = self._db.cursor()
        cur.execute(
            """
            SELECT date(started_at) as act_date, count(*) as count
            FROM activities
            WHERE started_at >= ?
            GROUP BY date(started_at)
            ORDER BY act_date ASC;
            """,
            (week_ago,)
        )
        daily_counts = {row["act_date"]: row["count"] for row in cur.fetchall()}

        cur.execute(
            """
            SELECT category, count(*) as count
            FROM activities
            WHERE started_at >= ?
            GROUP BY category;
            """,
            (week_ago,)
        )
        category_breakdown = {row["category"]: row["count"] for row in cur.fetchall()}

        total_activities = sum(daily_counts.values())
        days_active = len(daily_counts)
        consistency_percent = (days_active / 7.0) * 100.0

        return {
            "period_days": 7,
            "days_with_activity": days_active,
            "total_activities_logged": total_activities,
            "consistency_score_percentage": round(consistency_percent, 1),
            "daily_activity_counts": daily_counts,
            "category_distribution": category_breakdown,
        }
