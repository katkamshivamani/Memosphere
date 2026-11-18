"""
MEMOSPHERE SQLAlchemy Database Models
Defines Users, Memories, Reminders, RoutineLogs, Conversations, and CaregiverPermissions.
"""
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="user")  # 'user' | 'caregiver' | 'admin'
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else str(self.created_at),
        }


class Memory(db.Model):
    __tablename__ = "memories"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category = db.Column(db.String(50), nullable=False, default="Items")  # People, Places, Items, Activities, Routines
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    entity_name = db.Column(db.String(150), nullable=True, default="")
    location = db.Column(db.String(150), nullable=True, default="")
    event_date = db.Column(db.String(40), nullable=True, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "category": self.category,
            "title": self.title,
            "content": self.content,
            "entity_name": self.entity_name or "",
            "location": self.location or "",
            "event_date": self.event_date or "",
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else str(self.created_at),
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else str(self.updated_at),
        }


class Reminder(db.Model):
    __tablename__ = "reminders"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True, default="")
    reminder_datetime = db.Column(db.String(64), nullable=False)  # ISO datetime or HH:MM
    recurrence = db.Column(db.String(50), nullable=False, default="none")  # none, daily, weekly, weekdays
    tone = db.Column(db.String(30), nullable=False, default="Friendly")  # Friendly, Calm, Direct
    completed = db.Column(db.Boolean, nullable=False, default=False)

    def format_notification_message(self) -> str:
        """Generate tone-adapted reminder notification message without calling external AI."""
        time_display = self.reminder_datetime
        if "T" in time_display:
            try:
                dt = datetime.fromisoformat(time_display)
                time_display = dt.strftime("%I:%M %p").lstrip("0")
            except ValueError:
                pass
        tone_key = (self.tone or "Friendly").capitalize()
        if tone_key == "Calm":
            return f"Gentle reminder ({time_display}): Whenever you're ready, it's time for {self.title.lower()}."
        if tone_key == "Direct":
            return f"Reminder ({time_display}): {self.title}."
        return f"Hey! It's {time_display}. Time for your {self.title.lower()}."

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description or "",
            "reminder_datetime": self.reminder_datetime,
            "recurrence": self.recurrence or "none",
            "tone": self.tone or "Friendly",
            "completed": bool(self.completed),
            "notification_message": self.format_notification_message(),
        }


class RoutineLog(db.Model):
    __tablename__ = "routine_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    routine_name = db.Column(db.String(200), nullable=False)
    completion_status = db.Column(db.String(40), nullable=False, default="pending")  # pending, completed, missed
    scheduled_time = db.Column(db.String(64), nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "routine_name": self.routine_name,
            "completion_status": self.completion_status,
            "scheduled_time": self.scheduled_time,
            "completed_at": (
                self.completed_at.isoformat()
                if isinstance(self.completed_at, datetime)
                else (str(self.completed_at) if self.completed_at else None)
            ),
        }


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "question": self.question,
            "answer": self.answer,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else str(self.created_at),
        }


class CaregiverPermission(db.Model):
    __tablename__ = "caregiver_permissions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    caregiver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    permission_type = db.Column(
        db.String(60), nullable=False, default="routines_and_reminders"
    )  # routines_and_reminders | activity_summary | full_ReadOnly (never raw private memories by default)
    consent_status = db.Column(
        db.String(40), nullable=False, default="granted"
    )  # pending | granted | revoked

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "caregiver_id": self.caregiver_id,
            "permission_type": self.permission_type,
            "consent_status": self.consent_status,
        }
