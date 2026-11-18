"""
MEMOSPHERE Routines Routes
Endpoints:
- POST /api/routines
- GET  /api/routines
- PUT  /api/routines/<id>
"""
from flask import Blueprint, jsonify, request
from backend.models import db, RoutineLog, utc_now
from backend.routes import get_current_user_id
from backend.services.ai.response_parser import ResponseParser

routines_bp = Blueprint("routines", __name__)

VALID_STATUSES = {"pending", "completed", "missed"}


@routines_bp.route("/api/routines", methods=["POST"])
def create_routine():
    user_id = get_current_user_id()
    data = request.get_json(silent=True) or {}

    routine_name = ResponseParser.sanitize_text(str(data.get("routine_name") or "")).strip()
    scheduled_time = ResponseParser.sanitize_text(str(data.get("scheduled_time") or "08:00 AM")).strip()
    completion_status = str(data.get("completion_status") or "pending").strip().lower()

    if not routine_name:
        return jsonify({"error": "Routine name is required."}), 400

    if completion_status not in VALID_STATUSES:
        completion_status = "pending"

    completed_at = utc_now() if completion_status == "completed" else None

    routine = RoutineLog(
        user_id=user_id,
        routine_name=routine_name,
        completion_status=completion_status,
        scheduled_time=scheduled_time,
        completed_at=completed_at,
    )
    db.session.add(routine)
    db.session.commit()

    return jsonify({
        "message": "Routine created successfully.",
        "routine": routine.to_dict(),
    }), 201


@routines_bp.route("/api/routines", methods=["GET"])
def list_routines():
    user_id = get_current_user_id()
    routines = RoutineLog.query.filter_by(user_id=user_id).all()
    total = len(routines)
    completed = sum(1 for r in routines if r.completion_status == "completed")
    missed = sum(1 for r in routines if r.completion_status == "missed")
    pending = sum(1 for r in routines if r.completion_status == "pending")

    return jsonify({
        "routines": [r.to_dict() for r in routines],
        "summary": {
            "total": total,
            "completed": completed,
            "missed": missed,
            "pending": pending,
            "completion_rate": round((completed / total) * 100) if total else 0,
        },
    }), 200


@routines_bp.route("/api/routines/<int:routine_id>", methods=["PUT"])
def update_routine(routine_id: int):
    user_id = get_current_user_id()
    routine = RoutineLog.query.filter_by(id=routine_id, user_id=user_id).first()
    if not routine:
        return jsonify({"error": "Routine not found."}), 404

    data = request.get_json(silent=True) or {}
    if "routine_name" in data and data["routine_name"] is not None:
        routine.routine_name = ResponseParser.sanitize_text(str(data["routine_name"])).strip() or routine.routine_name
    if "scheduled_time" in data and data["scheduled_time"] is not None:
        routine.scheduled_time = ResponseParser.sanitize_text(str(data["scheduled_time"])).strip() or routine.scheduled_time
    if "completion_status" in data and data["completion_status"] is not None:
        status = str(data["completion_status"]).strip().lower()
        if status in VALID_STATUSES:
            routine.completion_status = status
            routine.completed_at = utc_now() if status == "completed" else None

    db.session.commit()
    return jsonify({
        "message": "Routine updated successfully.",
        "routine": routine.to_dict(),
    }), 200
