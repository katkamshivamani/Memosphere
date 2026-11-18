"""
MEMOSPHERE Memories & Dashboard Stats Routes
Endpoints:
- POST   /api/memories
- GET    /api/memories
- GET    /api/memories/<id>
- PUT    /api/memories/<id>
- DELETE /api/memories/<id>
- GET    /api/dashboard/stats
"""
from flask import Blueprint, jsonify, request
from backend.models import db, Memory, Reminder, RoutineLog, Conversation, utc_now
from backend.routes import get_current_user_id
from backend.services.memory_service import MemoryService
from backend.services.ai.response_parser import ResponseParser

memories_bp = Blueprint("memories", __name__)


@memories_bp.route("/api/memories", methods=["POST"])
def create_memory():
    user_id = get_current_user_id()
    data = request.get_json(silent=True) or {}

    title = ResponseParser.sanitize_text(str(data.get("title") or "")).strip()
    content = ResponseParser.sanitize_text(str(data.get("content") or "")).strip()
    category = ResponseParser.sanitize_text(str(data.get("category") or "Items")).strip().capitalize()

    if not content and not title:
        return jsonify({"error": "Memory content or title is required."}), 400

    if not title:
        title = " ".join(content.split()[:5]).rstrip(".,;!?")
    if not content:
        content = title

    if category not in ResponseParser.VALID_CATEGORIES:
        category = "Items"

    entity_name = ResponseParser.sanitize_text(str(data.get("entity_name") or "")).strip()
    location = ResponseParser.sanitize_text(str(data.get("location") or "")).strip()
    event_date = ResponseParser.sanitize_text(str(data.get("event_date") or "")).strip()
    prevent_duplicates = bool(data.get("prevent_duplicates", True))

    memory, is_duplicate = MemoryService.create_or_update_memory(
        user_id=user_id,
        category=category,
        title=title,
        content=content,
        entity_name=entity_name,
        location=location,
        event_date=event_date,
        prevent_duplicates=prevent_duplicates,
    )

    status_code = 200 if is_duplicate else 201
    return jsonify({
        "message": "Existing memory updated (duplicate prevented)." if is_duplicate else "Memory saved successfully.",
        "is_duplicate": is_duplicate,
        "memory": memory.to_dict(),
    }), status_code


@memories_bp.route("/api/memories", methods=["GET"])
def list_memories():
    user_id = get_current_user_id()
    category = (request.args.get("category") or "").strip()
    search_q = (request.args.get("q") or request.args.get("search") or "").strip()

    query = Memory.query.filter_by(user_id=user_id)
    if category and category.lower() != "all":
        query = query.filter_by(category=category.capitalize())

    memories = query.order_by(Memory.updated_at.desc()).all()

    if search_q:
        q_lower = search_q.lower()
        memories = [
            m for m in memories
            if q_lower in (m.title or "").lower()
            or q_lower in (m.content or "").lower()
            or q_lower in (m.entity_name or "").lower()
            or q_lower in (m.location or "").lower()
            or q_lower in (m.category or "").lower()
        ]

    return jsonify({
        "memories": [m.to_dict() for m in memories],
        "count": len(memories),
    }), 200


@memories_bp.route("/api/memories/<int:memory_id>", methods=["GET"])
def get_memory(memory_id: int):
    user_id = get_current_user_id()
    memory = Memory.query.filter_by(id=memory_id, user_id=user_id).first()
    if not memory:
        return jsonify({"error": "Memory not found."}), 404
    return jsonify({"memory": memory.to_dict()}), 200


@memories_bp.route("/api/memories/<int:memory_id>", methods=["PUT"])
def update_memory(memory_id: int):
    user_id = get_current_user_id()
    memory = Memory.query.filter_by(id=memory_id, user_id=user_id).first()
    if not memory:
        return jsonify({"error": "Memory not found."}), 404

    data = request.get_json(silent=True) or {}
    if "title" in data and data["title"] is not None:
        memory.title = ResponseParser.sanitize_text(str(data["title"])).strip() or memory.title
    if "content" in data and data["content"] is not None:
        memory.content = ResponseParser.sanitize_text(str(data["content"])).strip() or memory.content
    if "category" in data and data["category"] is not None:
        cat = str(data["category"]).strip().capitalize()
        if cat in ResponseParser.VALID_CATEGORIES:
            memory.category = cat
    if "entity_name" in data:
        memory.entity_name = ResponseParser.sanitize_text(str(data["entity_name"] or "")).strip()
    if "location" in data:
        memory.location = ResponseParser.sanitize_text(str(data["location"] or "")).strip()
    if "event_date" in data:
        memory.event_date = ResponseParser.sanitize_text(str(data["event_date"] or "")).strip()

    memory.updated_at = utc_now()
    db.session.commit()

    return jsonify({
        "message": "Memory updated successfully.",
        "memory": memory.to_dict(),
    }), 200


@memories_bp.route("/api/memories/<int:memory_id>", methods=["DELETE"])
def delete_memory(memory_id: int):
    user_id = get_current_user_id()
    memory = Memory.query.filter_by(id=memory_id, user_id=user_id).first()
    if not memory:
        return jsonify({"error": "Memory not found."}), 404

    db.session.delete(memory)
    db.session.commit()
    return jsonify({"message": "Memory deleted successfully.", "id": memory_id}), 200


@memories_bp.route("/api/dashboard/stats", methods=["GET"])
def dashboard_stats():
    user_id = get_current_user_id()
    memories = Memory.query.filter_by(user_id=user_id).order_by(Memory.updated_at.desc()).all()
    reminders = Reminder.query.filter_by(user_id=user_id).all()
    routines = RoutineLog.query.filter_by(user_id=user_id).all()
    conversations = Conversation.query.filter_by(user_id=user_id).order_by(Conversation.created_at.desc()).limit(5).all()

    categories = {cat: 0 for cat in ["People", "Places", "Items", "Activities", "Routines"]}
    for m in memories:
        categories[m.category] = categories.get(m.category, 0) + 1

    upcoming_reminders = [r.to_dict() for r in reminders if not r.completed]
    completed_routines = sum(1 for r in routines if r.completion_status == "completed")
    total_routines = len(routines)
    routine_progress_pct = round((completed_routines / total_routines) * 100) if total_routines > 0 else 0

    return jsonify({
        "total_memories": len(memories),
        "category_counts": categories,
        "upcoming_reminders_count": len(upcoming_reminders),
        "completed_reminders_count": sum(1 for r in reminders if r.completed),
        "total_routines": total_routines,
        "completed_routines": completed_routines,
        "missed_routines": sum(1 for r in routines if r.completion_status == "missed"),
        "routine_progress_percent": routine_progress_pct,
        "recent_memories": [m.to_dict() for m in memories[:6]],
        "upcoming_reminders": upcoming_reminders[:5],
        "routines": [r.to_dict() for r in routines],
        "recent_conversations": [c.to_dict() for c in conversations],
    }), 200
