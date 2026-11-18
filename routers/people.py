import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from database import get_db_connection

router = APIRouter(prefix="/api/people", tags=["Module A1: People & Familiar Faces"])


def format_person(r) -> dict:
    d = dict(r)
    d["sharedWithCaregiver"] = bool(d.get("sharedWithCaregiver", 1))
    return d


@router.get("")
def list_people(
    q: Optional[str] = Query(default=""),
    relationship: Optional[str] = Query(default=""),
    role: Optional[str] = Query(default="patient"),
):
    conn = get_db_connection()
    cur = conn.cursor()
    sql = "SELECT * FROM people WHERE 1=1"
    params = []

    if role == "caregiver":
        sql += " AND sharedWithCaregiver = 1"
    if relationship and relationship != "All":
        sql += " AND relationship = ?"
        params.append(relationship)
    if q and q.strip():
        lk = f"%{q.strip().lower()}%"
        sql += " AND (LOWER(name) LIKE ? OR LOWER(keyFacts) LIKE ? OR LOWER(whereMet) LIKE ? OR LOWER(COALESCE(importantDate,'')) LIKE ?)"
        params.extend([lk, lk, lk, lk])

    sql += " ORDER BY lastInteraction DESC"
    cur.execute(sql, params)
    rows = [format_person(r) for r in cur.fetchall()]
    conn.close()
    return {"success": True, "count": len(rows), "data": rows}


@router.get("/recognize")
def recognize_saved_person(q: str = Query(default="")):
    """
    A1: Familiar Faces & People Recognition Through Saved Profiles.
    Strictly matches saved family/friends profiles — never claims to identify unknown people automatically.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    lk = f"%{q.strip().lower()}%"
    cur.execute(
        "SELECT * FROM people WHERE LOWER(name) LIKE ? OR LOWER(relationship) LIKE ? OR LOWER(keyFacts) LIKE ?",
        (lk, lk, lk),
    )
    matches = [format_person(r) for r in cur.fetchall()]
    conn.close()
    return {
        "success": True,
        "query": q,
        "disclaimer": "Recognition is strictly matched against your saved family and friend profiles. Unknown individuals are never automatically identified.",
        "matches": matches,
    }


@router.post("", status_code=201)
def create_person(body: dict):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Person name is required")

    now_iso = datetime.now().isoformat()
    new_id = body.get("id") or f"per_{int(time.time() * 1000)}"
    kf = body.get("keyFacts") or ""
    if isinstance(kf, list):
        kf = ", ".join(kf)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO people (id, name, relationship, whereMet, keyFacts, importantDate, avatarUrl, photoCaption, voicePrompt, sharedWithCaregiver, lastInteraction, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id,
            name,
            body.get("relationship") or "Family",
            (body.get("whereMet") or "Home").strip(),
            str(kf).strip(),
            body.get("importantDate"),
            body.get("avatarUrl"),
            body.get("photoCaption") or f"{name} ({body.get('relationship', 'Family')})",
            body.get("voicePrompt") or f"This is {name}, your {body.get('relationship', 'Family')}. {kf}",
            1 if body.get("sharedWithCaregiver", True) else 0,
            body.get("lastInteraction") or now_iso,
            now_iso,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM people WHERE id = ?", (new_id,))
    created = format_person(cur.fetchone())
    conn.close()
    return {"success": True, "data": created}


@router.patch("/{person_id}")
def update_person(person_id: str, body: dict):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM people WHERE id = ?", (person_id,))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Person not found")

    cur.execute(
        """
        UPDATE people
        SET name = ?, relationship = ?, whereMet = ?, keyFacts = ?, importantDate = ?, avatarUrl = ?, photoCaption = ?, voicePrompt = ?, sharedWithCaregiver = ?, lastInteraction = ?
        WHERE id = ?
        """,
        (
            body.get("name", existing["name"]),
            body.get("relationship", existing["relationship"]),
            body.get("whereMet", existing["whereMet"]),
            body.get("keyFacts", existing["keyFacts"]),
            body.get("importantDate", existing["importantDate"]),
            body.get("avatarUrl", existing["avatarUrl"]),
            body.get("photoCaption", existing["photoCaption"]),
            body.get("voicePrompt", existing["voicePrompt"]),
            1 if body.get("sharedWithCaregiver", bool(existing["sharedWithCaregiver"])) else 0,
            body.get("lastInteraction", existing["lastInteraction"]),
            person_id,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM people WHERE id = ?", (person_id,))
    updated = format_person(cur.fetchone())
    conn.close()
    return {"success": True, "data": updated}


@router.delete("/{person_id}")
def delete_person(person_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM people WHERE id = ?", (person_id,))
    conn.commit()
    conn.close()
    return {"success": True, "deletedId": person_id}
