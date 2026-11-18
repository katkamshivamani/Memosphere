"""
MEMOSPHERE Caregiver Dashboard & Consent Routes
Endpoints:
- GET  /api/caregiver/dashboard
- POST /api/caregiver/consent
Privacy & Role-Based Authorization:
- Requires explicit consent (`consent_status == 'granted'`) in CaregiverPermissions.
- Caregivers NEVER receive raw personal memories (People/Items/Places notes or Q&A transcripts).
- Provides only routine completion status, missed routines, pending reminders, activity category counts, and frequently missed routines.
"""
from collections import Counter
from flask import Blueprint, jsonify, request
from backend.models import db, User, Memory, Reminder, RoutineLog, CaregiverPermission
from backend.routes import get_current_user

caregiver_bp = Blueprint("caregiver", __name__)


@caregiver_bp.route("/api/caregiver/dashboard", methods=["GET"])
def caregiver_dashboard():
    current_user = get_current_user()
    patient_id_param = request.args.get("user_id")
    primary_user = (
        User.query.get(int(patient_id_param))
        if patient_id_param and str(patient_id_param).isdigit()
        else User.query.filter_by(role="user").first()
    )

    if not primary_user:
        return jsonify({"error": "Primary user profile not found."}), 404

    caregiver_user = (
        current_user
        if current_user and current_user.role in ("caregiver", "admin")
        else User.query.filter_by(role="caregiver").first()
    )

    perm = None
    if caregiver_user:
        perm = CaregiverPermission.query.filter_by(
            user_id=primary_user.id, caregiver_id=caregiver_user.id
        ).first()

    if not perm or perm.consent_status != "granted":
        return jsonify({
            "authorized": False,
            "consent_status": perm.consent_status if perm else "none",
            "patient_name": primary_user.name,
            "message": (
                "Explicit patient consent is required before viewing caregiver wellness & routine summaries. "
                "Private personal memories are always protected."
            ),
        }), 403

    routines = RoutineLog.query.filter_by(user_id=primary_user.id).all()
    reminders = Reminder.query.filter_by(user_id=primary_user.id).all()
    memories = Memory.query.filter_by(user_id=primary_user.id).all()

    daily_routine_status = [r.to_dict() for r in routines]
    missed_routines = [r.to_dict() for r in routines if r.completion_status == "missed"]
    completed_routines = [r.to_dict() for r in routines if r.completion_status == "completed"]
    pending_reminders = [rem.to_dict() for rem in reminders if not rem.completed]

    # Calculate frequently missed activities
    missed_counter = Counter(r.routine_name for r in routines if r.completion_status == "missed")
    frequently_missed = [
        {"routine_name": name, "missed_count": count}
        for name, count in missed_counter.most_common(5)
    ]

    # High-level activity summaries (aggregate counts ONLY — never expose private memory content)
    activity_category_counts = Counter(m.category for m in memories)

    return jsonify({
        "authorized": True,
        "consent_status": perm.consent_status,
        "permission_type": perm.permission_type,
        "privacy_notice": "Private memories and personal conversations are hidden by privacy lock.",
        "patient": {
            "id": primary_user.id,
            "name": primary_user.name,
            "email": primary_user.email,
        },
        "caregiver": caregiver_user.to_dict() if caregiver_user else None,
        "daily_routine_status": daily_routine_status,
        "missed_routines": missed_routines,
        "pending_reminders": pending_reminders,
        "frequently_missed_activities": frequently_missed,
        "activity_summary": {
            "total_routines": len(routines),
            "completed_routines_count": len(completed_routines),
            "missed_routines_count": len(missed_routines),
            "pending_reminders_count": len(pending_reminders),
            "CompletionRatePercent": round((len(completed_routines) / len(routines)) * 100) if routines else 0,
            "logged_activities_count": activity_category_counts.get("Activities", 0),
            "logged_routines_count": activity_category_counts.get("Routines", 0),
            "private_memories_redacted": True,
        },
    }), 200


@caregiver_bp.route("/api/caregiver/consent", methods=["POST", "PUT"])
def update_caregiver_consent():
    data = request.get_json(silent=True) or {}
    consent_status = str(data.get("consent_status") or "granted").strip().lower()
    permission_type = str(data.get("permission_type") or "routines_and_reminders").strip()

    if consent_status not in ("granted", "revoked", "pending"):
        return jsonify({"error": "Invalid consent_status. Choose granted, revoked, or pending."}), 400

    primary_user = User.query.filter_by(role="user").first()
    caregiver_user = User.query.filter_by(role="caregiver").first()
    if not primary_user or not caregiver_user:
        return jsonify({"error": "User or caregiver account not found."}), 404

    perm = CaregiverPermission.query.filter_by(
        user_id=primary_user.id, caregiver_id=caregiver_user.id
    ).first()
    if not perm:
        perm = CaregiverPermission(
            user_id=primary_user.id,
            caregiver_id=caregiver_user.id,
            permission_type=permission_type,
            consent_status=consent_status,
        )
        db.session.add(perm)
    else:
        perm.consent_status = consent_status
        perm.permission_type = permission_type

    db.session.commit()
    return jsonify({
        "message": f"Caregiver consent status updated to '{consent_status}'.",
        "permission": perm.to_dict(),
    }), 200
