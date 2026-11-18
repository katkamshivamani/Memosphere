"""
MEMOSPHERE Reminder & Routine Scheduling Service
Uses Python and APScheduler (BackgroundScheduler) for deterministic reminder scheduling,
recurring reminders, completion tracking, and tone-based notifications.
Does NOT use an AI API for scheduling logic.
"""
from datetime import datetime
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from backend.models import db, Reminder, RoutineLog, utc_now

logger = logging.getLogger("memosphere.reminders")


class ReminderService:
    """Manages APScheduler background jobs and deterministic reminder notifications."""

    _scheduler: BackgroundScheduler | None = None
    _recent_notifications: list[dict] = []

    @classmethod
    def init_scheduler(cls, app=None) -> BackgroundScheduler:
        if cls._scheduler is None:
            cls._scheduler = BackgroundScheduler(daemon=True)
            cls._scheduler.add_job(
                func=cls._check_due_reminders_tick,
                trigger="interval",
                seconds=60,
                id="memosphere_due_reminder_checker",
                replace_existing=True,
            )
            cls._scheduler.start()
        return cls._scheduler

    @classmethod
    def get_scheduler(cls) -> BackgroundScheduler:
        return cls.init_scheduler()

    @classmethod
    def schedule_reminder_job(cls, reminder: Reminder) -> str:
        """Register or update an APScheduler job for a specific reminder."""
        scheduler = cls.get_scheduler()
        job_id = f"reminder_{reminder.id}"
        scheduler.add_job(
            func=cls.trigger_reminder_notification,
            trigger="interval",
            minutes=60 if reminder.recurrence == "none" else 1440,
            id=job_id,
            replace_existing=True,
            kwargs={
                "reminder_id": reminder.id,
                "title": reminder.title,
                "tone": reminder.tone,
                "reminder_datetime": reminder.reminder_datetime,
            },
        )
        return job_id

    @classmethod
    def remove_reminder_job(cls, reminder_id: int) -> None:
        scheduler = cls.get_scheduler()
        job_id = f"reminder_{reminder_id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

    @classmethod
    def trigger_reminder_notification(
        cls,
        reminder_id: int,
        title: str,
        tone: str = "Friendly",
        reminder_datetime: str = "",
    ) -> dict:
        """Build and record a friendly, calm, or direct notification without using AI."""
        temp = Reminder(
            id=reminder_id,
            user_id=0,
            title=title,
            reminder_datetime=reminder_datetime or datetime.now().strftime("%I:%M %p"),
            tone=tone or "Friendly",
        )
        msg = temp.format_notification_message()
        event = {
            "reminder_id": reminder_id,
            "title": title,
            "tone": tone,
            "message": msg,
            "triggered_at": utc_now().isoformat(),
        }
        cls._recent_notifications.append(event)
        if len(cls._recent_notifications) > 50:
            cls._recent_notifications = cls._recent_notifications[-50:]
        return event

    @classmethod
    def _check_due_reminders_tick(cls) -> None:
        """Background tick executed by APScheduler."""
        pass

    @classmethod
    def get_due_and_upcoming_reminders(cls, user_id: int) -> dict:
        reminders = (
            Reminder.query.filter_by(user_id=user_id)
            .order_by(Reminder.completed.asc(), Reminder.reminder_datetime.asc())
            .all()
        )
        pending = [r.to_dict() for r in reminders if not r.completed]
        completed = [r.to_dict() for r in reminders if r.completed]
        return {
            "all": [r.to_dict() for r in reminders],
            "pending": pending,
            "completed": completed,
            "pending_count": len(pending),
            "completed_count": len(completed),
            "scheduler_running": bool(cls._scheduler and cls._scheduler.running),
        }
