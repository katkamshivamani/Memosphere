import re
from database import get_db_connection


def tokenize_query(text: str) -> list:
    stop_words = {
        "where", "what", "when", "who", "did", "is", "are", "my", "the", "a",
        "an", "in", "on", "at", "to", "for", "of", "and", "or", "tell", "me",
        "about", "do", "i", "have", "any", "today", "can", "you", "show",
    }
    tokens = re.findall(r"[a-zA-Z0-9]+", (text or "").lower())
    return [t for t in tokens if t not in stop_words and len(t) > 1]


def score_record(tokens: list, text_blob: str) -> int:
    if not tokens:
        return 1
    low = (text_blob or "").lower()
    score = 0
    for tok in tokens:
        if tok in low:
            score += 3
    return score


def retrieve_relevant_context(query: str, max_per_table: int = 4) -> dict:
    """
    Retrieves only relevant personal records from local SQLite tables with source IDs.
    Minimizes personal data transmitted to external AI providers.
    """
    tokens = tokenize_query(query)
    conn = get_db_connection()
    cur = conn.cursor()

    sources = []
    matched = {
        "people": [],
        "places": [],
        "memories": [],
        "environmentGuides": [],
        "activities": [],
        "routines": [],
        "medications": [],
        "caregiverNotes": [],
    }

    # 1. People
    cur.execute("SELECT * FROM people ORDER BY lastInteraction DESC")
    for r in cur.fetchall():
        blob = f"{r['name']} {r['relationship']} {r['whereMet']} {r['keyFacts']} {r['importantDate'] or ''} {r['voicePrompt'] or ''}"
        sc = score_record(tokens, blob)
        if sc > 0:
            item = dict(r)
            item["_score"] = sc
            matched["people"].append(item)
    matched["people"] = sorted(matched["people"], key=lambda x: x["_score"], reverse=True)[:max_per_table]
    for p in matched["people"]:
        sources.append({"table": "people", "id": p["id"], "title": p["name"], "detail": f"{p['relationship']} — {p['keyFacts']} ({p['importantDate'] or ''})"})

    # 2. Places & Items
    cur.execute("SELECT * FROM places ORDER BY isPinned DESC, updatedAt DESC")
    for r in cur.fetchall():
        blob = f"{r['title']} {r['category']} {r['exactLocation']} {r['notes'] or ''}"
        sc = score_record(tokens, blob)
        if sc > 0:
            item = dict(r)
            item["_score"] = sc
            matched["places"].append(item)
    matched["places"] = sorted(matched["places"], key=lambda x: x["_score"], reverse=True)[:max_per_table]
    for pl in matched["places"]:
        sources.append({"table": "places", "id": pl["id"], "title": pl["title"], "detail": pl["exactLocation"]})

    # 3. Memories (Life Story & Album)
    cur.execute("SELECT * FROM memories ORDER BY createdAt DESC")
    for r in cur.fetchall():
        blob = f"{r['title']} {r['category']} {r['storyText']} {r['eraOrYear'] or ''} {r['favouriteMusic'] or ''} {r['involvedPeople'] or ''}"
        sc = score_record(tokens, blob)
        if sc > 0:
            item = dict(r)
            item["_score"] = sc
            matched["memories"].append(item)
    matched["memories"] = sorted(matched["memories"], key=lambda x: x["_score"], reverse=True)[:max_per_table]
    for m in matched["memories"]:
        sources.append({"table": "memories", "id": m["id"], "title": m["title"], "detail": m["storyText"]})

    # 4. Familiar Environment Guides
    cur.execute("SELECT * FROM environment_guides")
    for r in cur.fetchall():
        blob = f"{r['locationName']} {r['stepByStepInstruction']} {r['roomCategory']}"
        sc = score_record(tokens, blob)
        if sc > 0:
            item = dict(r)
            item["_score"] = sc
            matched["environmentGuides"].append(item)
    matched["environmentGuides"] = sorted(matched["environmentGuides"], key=lambda x: x["_score"], reverse=True)[:max_per_table]
    for eg in matched["environmentGuides"]:
        sources.append({"table": "environment_guides", "id": eg["id"], "title": eg["locationName"], "detail": eg["stepByStepInstruction"]})

    # 5. Activities
    cur.execute("SELECT * FROM activities ORDER BY loggedAt DESC")
    for r in cur.fetchall():
        blob = f"{r['actionTitle']} {r['category']} {r['notes'] or ''}"
        sc = score_record(tokens, blob)
        if sc > 0:
            item = dict(r)
            item["_score"] = sc
            matched["activities"].append(item)
    matched["activities"] = sorted(matched["activities"], key=lambda x: x["_score"], reverse=True)[:max_per_table]
    for a in matched["activities"]:
        sources.append({"table": "activities", "id": a["id"], "title": a["actionTitle"], "detail": f"Logged at {a['loggedAt']}"})

    # 6. Routines & Medications
    cur.execute("SELECT * FROM routines ORDER BY timeSlot ASC")
    for r in cur.fetchall():
        blob = f"{r['title']} {r['timeSlot']} {r['priority']}"
        sc = score_record(tokens, blob)
        if sc > 0:
            item = dict(r)
            item["_score"] = sc
            matched["routines"].append(item)
    matched["routines"] = sorted(matched["routines"], key=lambda x: x["_score"], reverse=True)[:max_per_table]

    cur.execute("SELECT * FROM medications ORDER BY scheduledTime ASC")
    for r in cur.fetchall():
        blob = f"{r['medicationName']} {r['scheduledTime']} {r['instructions']} {r['status']}"
        sc = score_record(tokens, blob)
        if sc > 0:
            item = dict(r)
            item["_score"] = sc
            matched["medications"].append(item)
    for med in matched["medications"]:
        sources.append({"table": "medications", "id": med["id"], "title": med["medicationName"], "detail": f"{med['scheduledTime']} — Status: {med['status']}"})

    # 7. Caregiver Notes / Visits
    cur.execute("SELECT * FROM caregiver_notes ORDER BY createdAt DESC")
    for r in cur.fetchall():
        blob = f"{r['title']} {r['noteType']} {r['content']} {r['scheduledFor'] or ''}"
        sc = score_record(tokens, blob)
        if sc > 0:
            item = dict(r)
            item["_score"] = sc
            matched["caregiverNotes"].append(item)

    conn.close()

    # Construct minimal context string for external AI provider
    lines = []
    for s in sources[:10]:
        lines.append(f"[{s['table']}#{s['id']}] {s['title']}: {s['detail']}")

    return {
        "query": query,
        "tokens": tokens,
        "matched": matched,
        "sources": sources,
        "minimalContextPrompt": "\n".join(lines) if lines else "NO_MATCHING_PERSONAL_RECORDS",
    }
