import time
from datetime import datetime
from fastapi import APIRouter, HTTPException
from database import get_db_connection
from services.ai_service import parse_voice_memory_proposal, answer_patient_question

router = APIRouter(prefix="/api/voice", tags=["Module C: Multilingual Voice Assistant"])


@router.post("/propose-capture")
def propose_voice_memory_capture(body: dict):
    """
    C5: Interprets spoken/typed memory statement, identifies target module, extracts structured fields,
    and returns a proposed entry for confirmation before writing to SQLite.
    """
    utterance = (body.get("utterance") or "").strip()
    if not utterance:
        raise HTTPException(status_code=400, detail="Utterance text is required")

    proposal = parse_voice_memory_proposal(utterance)
    return {"success": True, "utterance": utterance, "proposal": proposal}


@router.post("/confirm-capture", status_code=201)
def confirm_and_save_voice_capture(body: dict):
    """
    C5 Step 6 & 7: Saves the user-confirmed structured memory proposal to the appropriate SQLite table
    and returns text + spoken confirmation.
    """
    target = body.get("targetModule")
    rec = body.get("proposedRecord") or {}
    now_iso = datetime.now().isoformat()

    conn = get_db_connection()
    cur = conn.cursor()

    if target == "places":
        new_id = f"plc_{int(time.time() * 1000)}"
        cur.execute(
            """
            INSERT INTO places (id, title, category, exactLocation, notes, isPinned, sharedWithCaregiver, updatedAt, createdAt)
            VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?)
            """,
            (
                new_id,
                rec.get("title") or "Saved Item",
                rec.get("category") or "Physical Item",
                rec.get("exactLocation") or "Home",
                rec.get("notes") or "Saved via Voice Assistant",
                now_iso,
                now_iso,
            ),
        )
    elif target == "people":
        new_id = f"per_{int(time.time() * 1000)}"
        cur.execute(
            """
            INSERT INTO people (id, name, relationship, whereMet, keyFacts, importantDate, avatarUrl, photoCaption, voicePrompt, sharedWithCaregiver, lastInteraction, createdAt)
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, 1, ?, ?)
            """,
            (
                new_id,
                rec.get("name") or "Family Member",
                rec.get("relationship") or "Family",
                rec.get("whereMet") or "Home",
                rec.get("keyFacts") or "",
                rec.get("importantDate"),
                f"{rec.get('name')} ({rec.get('relationship')})",
                f"This is {rec.get('name')}, your {rec.get('relationship')}.",
                now_iso,
                now_iso,
            ),
        )
    elif target == "reminders":
        new_id = f"rem_{int(time.time() * 1000)}"
        cur.execute(
            """
            INSERT INTO reminders (id, title, category, scheduledTime, priority, repeatIntervalSec, snoozeDurationMins, escalationWindowMins, status, shareWithCaregiver, createdAt)
            VALUES (?, ?, ?, ?, ?, 120, 5, 30, 'ACTIVE', 1, ?)
            """,
            (
                new_id,
                rec.get("title") or "Voice Reminder",
                rec.get("category") or "Personal",
                rec.get("scheduledTime") or "10:00 AM",
                rec.get("priority") or "Important",
                now_iso,
            ),
        )
    else:
        new_id = f"act_{int(time.time() * 1000)}"
        cur.execute(
            """
            INSERT INTO activities (id, actionTitle, category, notes, source, loggedAt)
            VALUES (?, ?, ?, ?, 'voice', ?)
            """,
            (
                new_id,
                rec.get("actionTitle") or "Completed activity",
                rec.get("category") or "Personal",
                rec.get("notes") or "Confirmed via Voice Assistant",
                now_iso,
            ),
        )

    conn.commit()
    conn.close()
    return {
        "success": True,
        "savedId": new_id,
        "targetModule": target,
        "spokenConfirmation": body.get("spokenConfirmation") or "Your memory has been saved safely.",
    }
