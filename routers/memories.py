import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from database import get_db_connection

router = APIRouter(tags=["Module A2 & A3: Daily Orientation & Life Story Memory Album"])


@router.get("/api/orientation")
def get_daily_orientation():
    """
    A2: Daily Orientation Assistant.
    Returns current date, day of week, time, period of day (Morning/Afternoon/Evening),
    today's scheduled activities/routines, upcoming appointments, expected family visits, and critical reminders.
    """
    now = datetime.now()
    hour = now.hour
    if 5 <= hour < 12:
        period = "Morning"
        greeting = "Good Morning"
    elif 12 <= hour < 17:
        period = "Afternoon"
        greeting = "Good Afternoon"
    elif 17 <= hour < 21:
        period = "Evening"
        greeting = "Good Evening"
    else:
        period = "Night"
        greeting = "Good Night"

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM routines ORDER BY timeSlot ASC")
    routines = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT * FROM medications ORDER BY scheduledTime ASC")
    medications = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT * FROM caregiver_notes ORDER BY createdAt DESC")
    cg_notes = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT * FROM reminders WHERE status != 'ACKNOWLEDGED' ORDER BY scheduledTime ASC")
    active_reminders = [dict(r) for r in cur.fetchall()]

    conn.close()

    appointments = [n for n in cg_notes if n["noteType"] == "Appointment"]
    expected_visits = [n for n in cg_notes if n["noteType"] == "Expected Visit"]

    return {
        "success": True,
        "currentDate": now.strftime("%d %B %Y"),
        "dayOfWeek": now.strftime("%A"),
        "currentTime": now.strftime("%I:%M %p"),
        "timeOfDay": period,
        "greeting": greeting,
        "scheduledRoutines": routines,
        "medicationsToday": medications,
        "upcomingAppointments": appointments,
        "expectedFamilyVisits": expected_visits,
        "importantReminders": active_reminders,
    }


@router.get("/api/memories")
def list_memories(
    q: Optional[str] = Query(default=""),
    category: Optional[str] = Query(default=""),
    role: Optional[str] = Query(default="patient"),
):
    conn = get_db_connection()
    cur = conn.cursor()
    sql = "SELECT * FROM memories WHERE 1=1"
    params = []
    if role == "caregiver":
        sql += " AND sharedWithCaregiver = 1"
    if category and category != "All":
        sql += " AND category = ?"
        params.append(category)
    if q and q.strip():
        lk = f"%{q.strip().lower()}%"
        sql += " AND (LOWER(title) LIKE ? OR LOWER(storyText) LIKE ? OR LOWER(COALESCE(involvedPeople,'')) LIKE ? OR LOWER(COALESCE(favouriteMusic,'')) LIKE ?)"
        params.extend([lk, lk, lk, lk])
    sql += " ORDER BY createdAt DESC"
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"success": True, "count": len(rows), "data": rows}


@router.post("/api/memories", status_code=201)
def create_memory(body: dict):
    title = (body.get("title") or "").strip()
    story = (body.get("storyText") or "").strip()
    if not title or not story:
        raise HTTPException(status_code=400, detail="title and storyText are required")

    new_id = f"mem_{int(time.time() * 1000)}"
    now_iso = datetime.now().isoformat()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO memories (id, title, category, storyText, eraOrYear, mediaUrl, favouriteMusic, involvedPeople, sharedWithCaregiver, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id,
            title,
            body.get("category") or "Family Memory",
            story,
            body.get("eraOrYear"),
            body.get("mediaUrl"),
            body.get("favouriteMusic"),
            body.get("involvedPeople"),
            1 if body.get("sharedWithCaregiver", True) else 0,
            now_iso,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM memories WHERE id = ?", (new_id,))
    created = dict(cur.fetchone())
    conn.close()
    return {"success": True, "data": created}


@router.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    conn.commit()
    conn.close()
    return {"success": True, "deletedId": memory_id}
