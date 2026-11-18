"""
MEMOSPHERE Routes Package
Provides authentication helpers and blueprints for all REST API endpoints.
"""
from flask import request, session
from backend.models import db, User


def get_current_user_id() -> int:
    """
    Resolve active user ID from session, X-User-Id header, or default demo user (id=1).
    Ensures smooth operation across authenticated sessions and live hackathon demos.
    """
    if "user_id" in session and session["user_id"]:
        return int(session["user_id"])
    header_uid = request.headers.get("X-User-Id")
    if header_uid and str(header_uid).isdigit():
        return int(header_uid)
    user = User.query.filter_by(role="user").first() or User.query.first()
    return user.id if user else 1


def get_current_user() -> User | None:
    uid = get_current_user_id()
    return db.session.get(User, uid)
