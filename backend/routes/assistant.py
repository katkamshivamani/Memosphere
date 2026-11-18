"""
MEMOSPHERE AI Assistant Routes (Natural Language Q&A & Brain Dump Extraction)
Endpoints:
- POST /api/ai/ask
- POST /api/ai/extract
- GET  /api/ai/conversations
"""
from flask import Blueprint, jsonify, request
from backend.models import db, Conversation
from backend.routes import get_current_user_id
from backend.services.memory_service import MemoryService
from backend.services.ai.ai_client import AIClient

assistant_bp = Blueprint("assistant", __name__)


@assistant_bp.route("/api/ai/ask", methods=["POST"])
def ask_memory():
    """
    Workflow:
    User question -> Flask API -> Memory retrieval service -> Retrieve relevant SQLite records
    -> Construct AI prompt using retrieved records -> External AI API (or transparent local fallback)
    -> Validate response -> Save conversation turn -> Return answer + supporting memory references.
    """
    user_id = get_current_user_id()
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()

    if not question:
        return jsonify({"error": "Question cannot be empty."}), 400

    # 1. Detect repeated question for patient repetition handling
    is_repeated, repeat_count, recent_convs = MemoryService.detect_repeated_question(
        user_id=user_id, question=question
    )

    # 2. Retrieve only relevant SQLite memories (never send entire personal DB)
    relevant_memories = MemoryService.retrieve_relevant_memories(
        user_id=user_id, question=question, max_results=5
    )
    retrieved_dicts = [m.to_dict() for m in relevant_memories]
    recent_conv_dicts = [c.to_dict() for c in recent_convs]

    # 3. Call AI integration layer
    ai_client = AIClient()
    result = ai_client.answer_memory_question(
        question=question,
        retrieved_memories=retrieved_dicts,
        recent_conversations=recent_conv_dicts,
        is_repeated_question=is_repeated,
        repetition_count=repeat_count,
    )

    # 4. Save conversation history in SQLite
    conv = Conversation(
        user_id=user_id,
        question=question,
        answer=result["answer"],
    )
    db.session.add(conv)
    db.session.commit()

    return jsonify({
        "question": question,
        "answer": result["answer"],
        "supporting_memories": retrieved_dicts,
        "is_repeated_question": is_repeated,
        "repetition_count": repeat_count,
        "provider": result.get("provider"),
        "model": result.get("model"),
        "source_mode": result.get("source_mode"),
        "used_fallback": result.get("used_fallback", False),
        "conversation_id": conv.id,
    }), 200


@assistant_bp.route("/api/ai/extract", methods=["POST"])
def extract_brain_dump():
    """
    Extract structured JSON from natural language Brain Dump voice/text input.
    Optionally saves directly to SQLite if `auto_save: true` is passed and no clarification is needed.
    """
    user_id = get_current_user_id()
    data = request.get_json(silent=True) or {}
    raw_text = (data.get("text") or data.get("content") or "").strip()
    auto_save = bool(data.get("auto_save", False))
    reference_date = (data.get("reference_date") or "").strip() or None

    if not raw_text:
        return jsonify({"error": "Input text is required for Brain Dump extraction."}), 400

    ai_client = AIClient()
    result = ai_client.extract_memory(raw_text=raw_text, reference_date=reference_date)
    extracted = result["extracted"]

    saved_memory = None
    is_duplicate = False
    if auto_save and not extracted.get("needs_clarification", False):
        mem_obj, is_duplicate = MemoryService.create_or_update_memory(
            user_id=user_id,
            category=extracted["category"],
            title=extracted["title"],
            content=extracted["content"],
            entity_name=extracted["entity_name"],
            location=extracted["location"],
            event_date=extracted["event_date"],
            prevent_duplicates=True,
        )
        saved_memory = mem_obj.to_dict()

    return jsonify({
        "extracted": extracted,
        "saved_memory": saved_memory,
        "is_duplicate": is_duplicate,
        "provider": result.get("provider"),
        "model": result.get("model"),
        "source_mode": result.get("source_mode"),
        "used_fallback": result.get("used_fallback", False),
    }), 200


@assistant_bp.route("/api/ai/conversations", methods=["GET"])
def get_conversations():
    user_id = get_current_user_id()
    convs = (
        Conversation.query.filter_by(user_id=user_id)
        .order_by(Conversation.created_at.desc())
        .limit(25)
        .all()
    )
    return jsonify({"conversations": [c.to_dict() for c in convs]}), 200
