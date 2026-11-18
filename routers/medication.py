import time
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from database import get_db_connection

router = APIRouter(prefix="/api/medications", tags=["Module A6: Medication Reminder & Confirmation"])


def format_med(r) -> dict:
    d = dict(r)
    d["isCritical"] = bool(d["isCritical"])
    d["shareWithCaregiver"] = bool(d["shareWithCaregiver"])
    return d


@router.get("")
def list_medications():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM medications ORDER BY scheduledTime ASC")
    meds = [format_med(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM medication_logs ORDER BY timestamp DESC LIMIT 25")
    logs = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {
        "success": True,
        "safetyPolicy": "Medications are NEVER automatically marked as taken when a notification is dismissed. Dosage recommendations are strictly prohibited.",
        "data": meds,
        "confirmationLogs": logs,
    }


@router.post("", status_code=201)
def create_medication(body: dict):
    name = (body.get("medicationName") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="medicationName is required")

    new_id = f"med_{int(time.time() * 1000)}"
    now_iso = datetime.now().isoformat()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO medications (id, medicationName, dosageDisplay, scheduledTime, instructions, isCritical, shareWithCaregiver, status, lastConfirmedAt, snoozedUntil, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', NULL, NULL, ?)
        """,
        (
            new_id,
            name,
            body.get("dosageDisplay") or "As prescribed by physician",
            body.get("scheduledTime") or "08:00 AM",
            body.get("instructions") or "Take with water as prescribed",
            1 if body.get("isCritical", True) else 0,
            1 if body.get("shareWithCaregiver", True) else 0,
            now_iso,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM medications WHERE id = ?", (new_id,))
    created = format_med(cur.fetchone())
    conn.close()
    return {"success": True, "data": created}


@router.post("/{med_id}/confirm")
def confirm_medication_action(med_id: str, body: dict):
    """
    A6: Explicit confirmation endpoint supporting ONLY:
      - TAKEN
      - NOT_TAKEN
      - REMIND_LATER
    Dismissing a popup NEVER marks a medication as TAKEN.
    """
    action = (body.get("action") or "").upper()
    if action not in ("TAKEN", "NOT_TAKEN", "REMIND_LATER"):
        raise HTTPException(
            status_code=400,
            detail="Invalid action. Must be one of: TAKEN, NOT_TAKEN, REMIND_LATER",
        )

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM medications WHERE id = ?", (med_id,))
    med = cur.fetchone()
    if not med:
        conn.close()
        raise HTTPException(status_code=404, detail="Medication not found")

    now = datetime.now()
    now_iso = now.isoformat()
    snooze_mins = int(body.get("snoozeMins", 10))

    if action == "TAKEN":
        new_status = "TAKEN"
        last_conf = now_iso
        snooze_until = None
    elif action == "NOT_TAKEN":
        new_status = "NOT_TAKEN"
        last_conf = now_iso
        snooze_until = None
    else:
        new_status = "SNOOZED"
        last_conf = med["lastConfirmedAt"]
        snooze_until = (now + timedelta(minutes=snooze_mins)).isoformat()

    cur.execute(
        """
        UPDATE medications
        SET status = ?, lastConfirmedAt = ?, snoozedUntil = ?
        WHERE id = ?
        """,
        (new_status, last_conf, snooze_until, med_id),
    )

    log_id = f"mlog_{int(time.time() * 1000)}"
    cur.execute(
        """
        INSERT INTO medication_logs (id, medicationId, medicationName, action, confirmedBy, timestamp, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            log_id,
            med_id,
            med["medicationName"],
            action,
            body.get("confirmedBy") or "Patient Explicit Button",
            now_iso,
            body.get("notes") or f"Explicitly marked {action}",
        ),
    )

    # Also log in daily activities if TAKEN
    if action == "TAKEN":
        cur.execute(
            """
            INSERT INTO activities (id, actionTitle, category, notes, source, loggedAt)
            VALUES (?, ?, 'Health/Meds', ?, 'manual', ?)
            """,
            (
                f"act_{int(time.time() * 1000)}",
                f"Took {med['medicationName']}",
                f"Confirmed TAKEN at {now.strftime('%I:%M %p')}",
                now_iso,
            ),
        )

    conn.commit()
    cur.execute("SELECT * FROM medications WHERE id = ?", (med_id,))
    updated = format_med(cur.fetchone())
    conn.close()

    caregiver_alert = bool(med["isCritical"] and action == "NOT_TAKEN")
    return {
        "success": True,
        "data": updated,
        "recordedTimestamp": now_iso,
        "caregiverEscalationTriggered": caregiver_alert,
    }
