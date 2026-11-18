import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from database import get_db_connection
from services.reminder_service import time_str_to_minutes

router = APIRouter(prefix="/api/routines", tags=["Module D: Routines & Habit Builder"])


def format_routine(r) -> dict:
    d = dict(r)
    d["shareWithCircle"] = bool(d["shareWithCircle"])
    d["completedToday"] = bool(d["completedToday"])
    return d


@router.get("")
def list_routines(
    priority: Optional[str] = Query(default=""),
    shareWithCircle: Optional[str] = Query(default=""),
):
    conn = get_db_connection()
    cur = conn.cursor()
    sql = "SELECT * FROM routines WHERE 1=1"
    params = []
    if priority and priority != "All":
        sql += " AND priority = ?"
        params.append(priority)
    if shareWithCircle == "true":
        sql += " AND shareWithCircle = 1"
    sql += " ORDER BY priority ASC, timeSlot ASC"
    cur.execute(sql, params)
    rows = [format_routine(r) for r in cur.fetchall()]
    conn.close()
    return {"success": True, "count": len(rows), "data": rows}


@router.get("/status")
def get_circle_status():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM routines WHERE shareWithCircle = 1 ORDER BY timeSlot ASC")
    shared = [format_routine(r) for r in cur.fetchall()]
    conn.close()

    now = datetime.now()
    curr_m = now.hour * 60 + now.minute
    completed, pending, missed = [], [], []
    for r in shared:
        if r["completedToday"]:
            completed.append(r)
        elif curr_m > time_str_to_minutes(r["timeSlot"]) + 30:
            missed.append(r)
        else:
            pending.append(r)

    return {
        "generatedAt": now.isoformat(),
        "circleMonitoringEnabledCount": len(shared),
        "summary": {
            "completedCount": len(completed),
            "pendingCount": len(pending),
            "missedCount": len(missed),
            "criticalMissedAlert": any(m["priority"] == "CRITICAL" for m in missed),
        },
        "completed": completed,
        "pending": pending,
        "missed": missed,
    }


@router.post("", status_code=201)
def create_routine(body: dict):
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Routine title is required")

    new_id = f"rtn_{int(time.time() * 1000)}"
    now_iso = datetime.now().isoformat()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO routines (id, title, timeSlot, frequency, priority, shareWithCircle, completedToday, lastCompletedAt, streakCount, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, 0, NULL, 0, ?)
        """,
        (
            new_id,
            title,
            body.get("timeSlot") or "08:00 AM",
            body.get("frequency") or "Daily",
            "CRITICAL" if body.get("priority") == "CRITICAL" else "NORMAL",
            1 if body.get("shareWithCircle", True) else 0,
            now_iso,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM routines WHERE id = ?", (new_id,))
    created = format_routine(cur.fetchone())
    conn.close()
    return {"success": True, "data": created}


@router.patch("/{routine_id}")
def update_routine(routine_id: str, body: dict):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM routines WHERE id = ?", (routine_id,))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Routine not found")

    comp = bool(existing["completedToday"])
    streak = int(existing["streakCount"])
    last_at = existing["lastCompletedAt"]

    if "completedToday" in body:
        next_c = bool(body["completedToday"])
        if next_c and not comp:
            streak += 1
            last_at = datetime.now().isoformat()
        elif not next_c and comp:
            streak = max(0, streak - 1)
        comp = next_c

    cur.execute(
        """
        UPDATE routines
        SET title = ?, timeSlot = ?, frequency = ?, priority = ?, shareWithCircle = ?, completedToday = ?, lastCompletedAt = ?, streakCount = ?
        WHERE id = ?
        """,
        (
            body.get("title", existing["title"]),
            body.get("timeSlot", existing["timeSlot"]),
            body.get("frequency", existing["frequency"]),
            body.get("priority", existing["priority"]),
            1 if body.get("shareWithCircle", bool(existing["shareWithCircle"])) else 0,
            1 if comp else 0,
            last_at,
            streak,
            routine_id,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM routines WHERE id = ?", (routine_id,))
    updated = format_routine(cur.fetchone())
    conn.close()
    return {"success": True, "data": updated}


@router.delete("/{routine_id}")
def delete_routine(routine_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM routines WHERE id = ?", (routine_id,))
    conn.commit()
    conn.close()
    return {"success": True, "deletedId": routine_id}
