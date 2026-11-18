import time
from datetime import datetime
from fastapi import APIRouter, HTTPException
from database import get_db_connection
from services.security_service import log_audit_event, get_caregiver_permissions

router = APIRouter(tags=["Module D3 & D4: Mood Check-ins, Caregiver Notes & Audit Logs"])


@router.get("/api/moods")
def list_mood_checkins():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM mood_checkins ORDER BY loggedAt DESC LIMIT 20")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"success": True, "count": len(rows), "data": rows}


@router.post("/api/moods", status_code=201)
def log_mood_checkin(body: dict):
    mood = body.get("mood") or "Normal"
    if mood not in ("Happy", "Normal", "Sad", "Anxious"):
        raise HTTPException(status_code=400, detail="Mood must be Happy, Normal, Sad, or Anxious")

    new_id = f"mood_{int(time.time() * 1000)}"
    now_iso = datetime.now().isoformat()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO mood_checkins (id, mood, notes, sharedWithCaregiver, loggedAt)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            new_id,
            mood,
            body.get("notes") or f"Patient checked in as {mood}",
            1 if body.get("sharedWithCaregiver", True) else 0,
            now_iso,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM mood_checkins WHERE id = ?", (new_id,))
    created = dict(cur.fetchone())
    conn.close()
    return {"success": True, "data": created}


@router.get("/api/caregivers/notes")
def list_caregiver_notes():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM caregiver_notes ORDER BY createdAt DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"success": True, "count": len(rows), "data": rows}


@router.post("/api/caregivers/notes", status_code=201)
def create_caregiver_note(body: dict):
    title = (body.get("title") or "").strip()
    content = (body.get("content") or "").strip()
    if not title or not content:
        raise HTTPException(status_code=400, detail="title and content are required")

    new_id = f"cgn_{int(time.time() * 1000)}"
    now_iso = datetime.now().isoformat()
    author = body.get("authorName") or "Authorized Caregiver"
    note_type = body.get("noteType") or "Observation"

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO caregiver_notes (id, authorName, noteType, title, content, scheduledFor, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (new_id, author, note_type, title, content, body.get("scheduledFor") or "Today", now_iso),
    )
    conn.commit()
    cur.execute("SELECT * FROM caregiver_notes WHERE id = ?", (new_id,))
    created = dict(cur.fetchone())
    conn.close()
    log_audit_event("caregiver", author, f"ADD_{note_type.upper().replace(' ', '_')}", "/api/caregivers/notes", title)
    return {"success": True, "data": created}


@router.get("/api/caregivers/audit-logs")
def list_audit_logs():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 30")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"success": True, "permissions": get_caregiver_permissions(), "data": rows}
