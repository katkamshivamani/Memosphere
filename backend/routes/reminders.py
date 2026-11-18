"""
MEMOSPHERE Reminders Routes
Endpoints:
- POST   /api/reminders
- GET    /api/reminders
- PUT    /api/reminders/<id>
- DELETE /api/reminders/<id>
"""
from flask import Blueprint, jsonify, request
from backend.models import db, Reminder
from backend.routes import get_current_user_id
from backend.services.reminder_service import ReminderService
from backend.services.ai.response_parser import ResponseParser

reminders_bp = Blueprint("reminders", __name__)

VALID_TONES = {"Friendly", "Calm", "Direct"}
VALID_RECURRENCES = {"none", "daily", "weekly", "weekdays"}


@reminders_bp.route("/api/reminders", methods=["POST"])
def create_reminder():
    user_id = get_current_user_id()
    data = request.get_json(silent=True) or {}

    title = ResponseParser.sanitize_text(str(data.get("title") or "")).strip()
    description = ResponseParser.sanitize_text(str(data.get("description") or "")).strip()
    reminder_datetime = ResponseParser.sanitize_text(str(data.get("reminder_datetime") or "")).strip()
    recurrence = str(data.get("recurrence") or "none").strip().lower()
    tone = str(data.get("tone") or "Friendly").strip().capitalize()

    if not title or not reminder_datetime:
        return jsonify({"error": "Reminder title and datetime/time are required."}), 400

    if recurrence not in VALID_RECURRENCES:
        recurrence = "none"
    if tone not in VALID_TONES:
        tone = "Friendly"

    reminder = Reminder(
        user_id=user_id,
        title=title,
        description=description,
        reminder_datetime=reminder_datetime,
        recurrence=recurrence,
        tone=tone,
        completed=bool(data.get("completed", False)),
    )
    db.session.add(reminder)
    db.session.commit()

    ReminderService.schedule_reminder_job(reminder)

    return jsonify({
        "message": "Reminder created and scheduled.",
        "reminder": reminder.to_dict(),
    }), 201


@reminders_bp.route("/api/reminders", methods=["GET"])
def list_reminders():
    user_id = get_current_user_id()
    summary = ReminderService.get_due_and_upcoming_reminders(user_id=user_id)
    return jsonify({
        "reminders": summary["all"],
        "pending": summary["pending"],
        "completed": summary["completed"],
        "pending_count": summary["pending_count"],
        "completed_count": summary["completed_count"],
        "scheduler_running": summary["scheduler_running"],
    }), 200


@reminders_bp.route("/api/reminders/<int:reminder_id>", methods=["PUT"])
def update_reminder(reminder_id: int):
    user_id = get_current_user_id()
    reminder = Reminder.query.filter_by(id=reminder_id, user_id=user_id).first()
    if not reminder:
        return jsonify({"error": "Reminder not found."}), 404

    data = request.get_json(silent=True) or {}
    if "title" in data and data["title"] is not None:
        reminder.title = ResponseParser.sanitize_text(str(data["title"])).strip() or reminder.title
    if "description" in data and data["description"] is not None:
        reminder.description = ResponseParser.sanitize_text(str(data["description"])).strip()
    if "reminder_datetime" in data and data["reminder_datetime"] is not None:
        reminder.reminder_datetime = ResponseParser.sanitize_text(str(data["reminder_datetime"])).strip()
    if "recurrence" in data and data["recurrence"] is not None:
        rec = str(data["recurrence"]).strip().lower()
        if rec in VALID_RECURRENCES:
            reminder.recurrence = rec
    if "tone" in data and data["tone"] is not None:
        t = str(data["tone"]).strip().capitalize()
        if t in VALID_TONES:
            reminder.tone = t
    if "completed" in data and data["completed"] is not None:
        reminder.completed = bool(data["completed"])

    db.session.commit()
    ReminderService.schedule_reminder_job(reminder)

    return jsonify({
        "message": "Reminder updated successfully.",
        "reminder": reminder.to_dict(),
    }), 200


@reminders_bp.route("/api/reminders/<int:reminder_id>", methods=["DELETE"])
def delete_reminder(reminder_id: int):
    user_id = get_current_user_id()
    reminder = Reminder.query.filter_by(id=reminder_id, user_id=user_id).first()
    if not reminder:
        return jsonify({"error": "Reminder not found."}), 404

    ReminderService.remove_reminder_job(reminder_id)
    db.session.delete(reminder)
    db.session.commit()

    return jsonify({"message": "Reminder deleted.", "id": reminder_id}), 200
