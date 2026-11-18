import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from database import get_db_connection

router = APIRouter(prefix="/api/activities", tags=["Module C: Daily Activities & Action Log"])


@router.get("")
def list_activities(
    q: Optional[str] = Query(default=""),
    category: Optional[str] = Query(default=""),
):
    conn = get_db_connection()
    cur = conn.cursor()
    sql = "SELECT * FROM activities WHERE 1=1"
    params = []
    if category and category != "All":
        sql += " AND category = ?"
        params.append(category)
    if q and q.strip():
        lk = f"%{q.strip().lower()}%"
        sql += " AND (LOWER(actionTitle) LIKE ? OR LOWER(COALESCE(notes,'')) LIKE ?)"
        params.extend([lk, lk])
    sql += " ORDER BY loggedAt DESC"
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"success": True, "count": len(rows), "data": rows}


@router.post("", status_code=201)
def create_activity(body: dict):
    title = (body.get("actionTitle") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="actionTitle is required")

    new_id = f"act_{int(time.time() * 1000)}"
    now_iso = datetime.now().isoformat()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO activities (id, actionTitle, category, notes, source, loggedAt)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            new_id,
            title,
            body.get("category") or "Personal",
            body.get("notes"),
            body.get("source") or "manual",
            body.get("loggedAt") or now_iso,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM activities WHERE id = ?", (new_id,))
    created = dict(cur.fetchone())
    conn.close()
    return {"success": True, "data": created}


@router.delete("/{activity_id}")
def delete_activity(activity_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM activities WHERE id = ?", (activity_id,))
    conn.commit()
    conn.close()
    return {"success": True, "deletedId": activity_id}
