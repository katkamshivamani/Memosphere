"""
MEMOSPHERE Authentication Routes
Endpoints:
- POST /api/register
- POST /api/login
- POST /api/logout
- GET  /api/me
"""
from flask import Blueprint, jsonify, request, session
from backend.models import db, User, CaregiverPermission
from backend.routes import get_current_user

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = (data.get("role") or "user").strip().lower()

    if not name or not email or not password:
        return jsonify({"error": "Name, email, and password are required."}), 400

    if role not in ("user", "caregiver", "admin"):
        role = "user"

    existing = User.query.filter_by(email=email).first()
    if existing:
        return jsonify({"error": "An account with this email already exists."}), 409

    user = User(name=name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    # If registering as a caregiver and a primary user exists, create a pending/granted permission record if requested
    if role == "caregiver":
        primary_user = User.query.filter_by(role="user").first()
        if primary_user:
            perm = CaregiverPermission(
                user_id=primary_user.id,
                caregiver_id=user.id,
                permission_type="routines_and_reminders",
                consent_status="granted" if data.get("consent_granted", True) else "pending",
            )
            db.session.add(perm)
            db.session.commit()

    session["user_id"] = user.id
    session["role"] = user.role

    return jsonify({
        "message": "Registration successful.",
        "user": user.to_dict(),
    }), 201


@auth_bp.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password."}), 401

    session["user_id"] = user.id
    session["role"] = user.role

    return jsonify({
        "message": "Login successful.",
        "user": user.to_dict(),
    }), 200


@auth_bp.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully."}), 200


@auth_bp.route("/api/me", methods=["GET"])
def me():
    user = get_current_user()
    if not user:
        return jsonify({"authenticated": False, "user": None}), 401
    return jsonify({"authenticated": True, "user": user.to_dict()}), 200
