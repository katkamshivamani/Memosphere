import json
import time
import hmac
import hashlib
from datetime import datetime
from database import get_db_connection, hash_password
from config import settings

ACTIVE_SESSIONS = {}


def create_session_token(user_id: str, username: str, role: str) -> str:
    payload = f"{user_id}:{username}:{role}:{int(time.time())}"
    sig = hmac.new(
        settings.secret_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:24]
    token = f"{payload}:{sig}"
    ACTIVE_SESSIONS[token] = {
        "userId": user_id,
        "username": username,
        "role": role,
        "createdAt": datetime.now().isoformat(),
    }
    return token


def authenticate_user(username: str, password: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username.strip(),))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    if row["passwordHash"] != hash_password(password):
        return None
    token = create_session_token(row["id"], row["username"], row["role"])
    return {
        "token": token,
        "user": {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "fullName": row["fullName"],
            "permissions": json.loads(row["permissionsJson"] or "{}"),
        },
    }


def log_audit_event(actor_role: str, actor_name: str, action: str, resource: str, details: str = ""):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO audit_logs (id, actorRole, actorName, action, resource, timestamp, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"aud_{int(time.time() * 1000)}",
            actor_role,
            actor_name,
            action,
            resource,
            datetime.now().isoformat(),
            details,
        ),
    )
    conn.commit()
    conn.close()


def get_caregiver_permissions() -> dict:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT permissionsJson FROM users WHERE role = 'caregiver' LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        return {
            "canViewPeople": True,
            "canViewMemories": True,
            "canViewMedications": True,
            "canViewLocation": True,
            "canManageRoutines": True,
        }
    return json.loads(row["permissionsJson"] or "{}")


def update_caregiver_permissions(new_perms: dict) -> dict:
    current = get_caregiver_permissions()
    current.update({k: bool(v) for k, v in new_perms.items()})
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET permissionsJson = ? WHERE role = 'caregiver'",
        (json.dumps(current),),
    )
    conn.commit()
    conn.close()
    log_audit_event("patient", "Patient Owner", "UPDATE_PERMISSIONS", "/api/caregivers/permissions", json.dumps(current))
    return current
