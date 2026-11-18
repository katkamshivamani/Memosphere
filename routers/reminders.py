import time
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from database import get_db_connection
from services.reminder_service import evaluate_reminders_and_escalations

router = APIRouter(prefix="/api/reminders", tags=["Module B: Persistent Vibration & Reminder Acknowledgement"])


@router.get("")
def list_and_evaluate_reminders():
    return {"success": True, **evaluate_reminders_and_escalations()}


@router.post("", status_code=201)
def create_reminder(body: dict):
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Reminder title is required")

    priority = body.get("priority") or "Important"
    if priority not in ("Normal", "Important", "Critical"):
        priority = "Important"

    new_id = f"rem_{int(time.time() * 1000)}"
    now_iso = datetime.now().isoformat()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO reminders (
            id, title, category, scheduledTime, priority,
            repeatIntervalSec, snoozeDurationMins, escalationWindowMins,
            status, acknowledgedAt, snoozedUntil, retryCount, shareWithCaregiver, createdAt
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', NULL, NULL, 0, ?, ?)
        """,
        (
            new_id,
            title,
            body.get("category") or "Medication",
            body.get("scheduledTime") or "08:00 AM",
            priority,
            int(body.get("repeatIntervalSec", 120)),
            int(body.get("snoozeDurationMins", 5)),
            int(body.get("escalationWindowMins", 30)),
            1 if body.get("shareWithCaregiver", True) else 0,
            now_iso,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM reminders WHERE id = ?", (new_id,))
    created = dict(cur.fetchone())
    conn.close()
    return {"success": True, "data": created}


@router.post("/{reminder_id}/acknowledge")
def acknowledge_reminder(reminder_id: str, body: dict = None):
    body = body or {}
    now_iso = datetime.now().isoformat()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
    rem = cur.fetchone()
    if not rem:
        conn.close()
        raise HTTPException(status_code=404, detail="Reminder not found")

    cur.execute(
        """
        UPDATE reminders
        SET status = 'ACKNOWLEDGED', acknowledgedAt = ?, snoozedUntil = NULL
        WHERE id = ?
        """,
        (now_iso, reminder_id),
    )
    conn.commit()
    cur.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
    updated = dict(cur.fetchone())
    conn.close()
    return {
        "success": True,
        "message": "Reminder explicitly acknowledged; vibration loop stopped.",
        "acknowledgedAt": now_iso,
        "data": updated,
    }


@router.post("/{reminder_id}/snooze")
def snooze_reminder(reminder_id: str, body: dict = None):
    body = body or {}
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
    rem = cur.fetchone()
    if not rem:
        conn.close()
        raise HTTPException(status_code=404, detail="Reminder not found")

    snooze_mins = int(body.get("snoozeDurationMins") or rem["snoozeDurationMins"] or 5)
    snoozed_until = (datetime.now() + timedelta(minutes=snooze_mins)).isoformat()
    next_retry = int(rem["retryCount"]) + 1

    cur.execute(
        """
        UPDATE reminders
        SET status = 'SNOOZED', snoozedUntil = ?, retryCount = ?
        WHERE id = ?
        """,
        (snoozed_until, next_retry, reminder_id),
    )
    conn.commit()
    cur.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
    updated = dict(cur.fetchone())
    conn.close()
    return {
        "success": True,
        "message": f"Reminder snoozed for {snooze_mins} minutes.",
        "snoozedUntil": snoozed_until,
        "data": updated,
    }
