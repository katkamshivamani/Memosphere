import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from database import get_db_connection

router = APIRouter(tags=["Module B & A4: Places, Items & Familiar Environment Guide"])


def format_place(r) -> dict:
    d = dict(r)
    d["isPinned"] = bool(d["isPinned"])
    d["sharedWithCaregiver"] = bool(d.get("sharedWithCaregiver", 1))
    return d


@router.get("/api/places")
def list_places(
    q: Optional[str] = Query(default=""),
    category: Optional[str] = Query(default=""),
    pinned: Optional[str] = Query(default=""),
):
    conn = get_db_connection()
    cur = conn.cursor()
    sql = "SELECT * FROM places WHERE 1=1"
    params = []
    if category and category != "All":
        sql += " AND category = ?"
        params.append(category)
    if pinned == "true":
        sql += " AND isPinned = 1"
    if q and q.strip():
        lk = f"%{q.strip().lower()}%"
        sql += " AND (LOWER(title) LIKE ? OR LOWER(exactLocation) LIKE ? OR LOWER(COALESCE(notes,'')) LIKE ?)"
        params.extend([lk, lk, lk])
    sql += " ORDER BY isPinned DESC, updatedAt DESC"
    cur.execute(sql, params)
    rows = [format_place(r) for r in cur.fetchall()]
    conn.close()
    return {"success": True, "count": len(rows), "data": rows}


@router.post("/api/places", status_code=201)
def create_place(body: dict):
    title = (body.get("title") or "").strip()
    exact_loc = (body.get("exactLocation") or "").strip()
    if not title or not exact_loc:
        raise HTTPException(status_code=400, detail="Both title and exactLocation are required")

    now_iso = datetime.now().isoformat()
    new_id = body.get("id") or f"plc_{int(time.time() * 1000)}"
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO places (id, title, category, exactLocation, notes, isPinned, sharedWithCaregiver, updatedAt, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id,
            title,
            body.get("category") or "Physical Item",
            exact_loc,
            body.get("notes"),
            1 if body.get("isPinned", True) else 0,
            1 if body.get("sharedWithCaregiver", True) else 0,
            now_iso,
            now_iso,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM places WHERE id = ?", (new_id,))
    created = format_place(cur.fetchone())
    conn.close()
    return {"success": True, "data": created}


@router.patch("/api/places/{place_id}")
def update_place(place_id: str, body: dict):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM places WHERE id = ?", (place_id,))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Place not found")

    now_iso = datetime.now().isoformat()
    is_pinned = 1 if body.get("isPinned", bool(existing["isPinned"])) else 0
    cur.execute(
        """
        UPDATE places
        SET title = ?, category = ?, exactLocation = ?, notes = ?, isPinned = ?, updatedAt = ?
        WHERE id = ?
        """,
        (
            body.get("title", existing["title"]),
            body.get("category", existing["category"]),
            body.get("exactLocation", existing["exactLocation"]),
            body.get("notes", existing["notes"]),
            is_pinned,
            now_iso,
            place_id,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM places WHERE id = ?", (place_id,))
    updated = format_place(cur.fetchone())
    conn.close()
    return {"success": True, "data": updated}


@router.delete("/api/places/{place_id}")
def delete_place(place_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM places WHERE id = ?", (place_id,))
    conn.commit()
    conn.close()
    return {"success": True, "deletedId": place_id}


# Module A4: Familiar Environment Guide Endpoints
@router.get("/api/environment-guide")
def list_environment_guides():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM environment_guides ORDER BY isPinned DESC, locationName ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"success": True, "count": len(rows), "data": rows}


@router.post("/api/environment-guide", status_code=201)
def create_environment_guide(body: dict):
    loc = (body.get("locationName") or "").strip()
    instr = (body.get("stepByStepInstruction") or "").strip()
    if not loc or not instr:
        raise HTTPException(status_code=400, detail="locationName and stepByStepInstruction required")

    new_id = f"env_{int(time.time() * 1000)}"
    now_iso = datetime.now().isoformat()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO environment_guides (id, locationName, visualIcon, stepByStepInstruction, spokenPrompt, roomCategory, isPinned, updatedAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id,
            loc,
            body.get("visualIcon") or "🧭",
            instr,
            body.get("spokenPrompt") or instr,
            body.get("roomCategory") or "Home Indoor",
            1,
            now_iso,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM environment_guides WHERE id = ?", (new_id,))
    created = dict(cur.fetchone())
    conn.close()
    return {"success": True, "data": created}
