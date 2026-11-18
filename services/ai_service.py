import re
import requests
import json
from config import settings
from services.retrieval_service import retrieve_relevant_context

# Track repeated user questions per session to ensure calm, patient, non-irritated responses (C6)
QUESTION_HISTORY = {}


def answer_patient_question(question: str, language: str = "en-IN", session_id: str = "default") -> dict:
    q_clean = (question or "").strip()
    norm_q = re.sub(r"[^a-z0-9]+", " ", q_clean.lower()).strip()

    repeat_count = QUESTION_HISTORY.get(norm_q, 0) + 1
    QUESTION_HISTORY[norm_q] = repeat_count

    retrieval = retrieve_relevant_context(q_clean)
    sources = retrieval["sources"]
    minimal_context = retrieval["minimalContextPrompt"]

    # Try external LLM API if backend API key is configured for current provider
    if settings.has_active_api_key():
        system_prompt = (
            "You are Memosphere, a patient, warm, reassuring AI Memory and Dementia Care Companion. "
            "RULES:\n"
            "1. Answer ONLY using the saved personal records provided below. Never invent or fabricate personal facts.\n"
            "2. If the requested fact is not in the saved records, gently state that it is not saved yet and offer to help save it.\n"
            "3. Use short, simple, calming sentences (maximum 2-3 sentences). Never express frustration even if the user repeats a question.\n"
            f"4. Respond in language code: {language}.\n\n"
            f"SAVED PERSONAL RECORDS:\n{minimal_context}\n\n"
            f"Patient Question (Asked {repeat_count} time(s)): {q_clean}"
        )
        try:
            provider_config = settings.get_provider_config()
            provider_id = provider_config.get("provider_id", "gemini")
            
            # Route to appropriate provider handler
            if provider_id == "gemini":
                ans = _call_gemini(system_prompt, provider_config)
            elif provider_id in ("openai", "groq", "nvidia", "nvidia_nim", "together", "custom"):
                ans = _call_openai_compatible(system_prompt, provider_config)
            elif provider_id == "anthropic":
                ans = _call_anthropic(system_prompt, provider_config)
            else:
                ans = None
            
            if ans:
                return {
                    "success": True,
                    "answer": ans,
                    "repeatCount": repeat_count,
                    "sources": sources[:4],
                    "engine": f"External Cloud LLM ({provider_id}:{provider_config.get('model', 'unknown')})",
                    "aiOnline": True,
                }
        except Exception as exc:
            # Graceful fallback when API times out or fails
            pass

    # Graceful Local Record Synthesis (No fabricated facts; clearly distinguishes saved vs unsaved)
    answer = synthesize_grounded_patient_reply(q_clean, retrieval["matched"], repeat_count, language)
    return {
        "success": True,
        "answer": answer,
        "repeatCount": repeat_count,
        "sources": sources[:4],
        "engine": "Grounded SQLite Knowledge Base Recall (Configure Backend API Key in .env for Cloud LLM)",
        "aiOnline": False,
    }


def _call_gemini(prompt: str, config: dict) -> str | None:
    """Call Google Gemini API."""
    api_key = config.get("api_key")
    model = config.get("model", "gemini-2.5-flash")
    if not api_key:
        return None
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    resp = requests.post(
        url,
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": settings.ai_temperature,
                "maxOutputTokens": settings.ai_max_tokens,
            },
        },
        timeout=10,
    )
    if resp.ok:
        data = resp.json()
        ans = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
            .strip()
        )
        return ans if ans else None
    return None


def _call_openai_compatible(prompt: str, config: dict) -> str | None:
    """Call OpenAI-compatible API (OpenAI, Groq, NVIDIA NIM, Together, Custom)."""
    api_key = config.get("api_key")
    base_url = config.get("base_url", "https://api.openai.com/v1")
    model = config.get("model", "gpt-4o-mini")
    
    if not api_key:
        return None
    
    # Ensure base_url ends with /chat/completions
    if not base_url.endswith("/chat/completions"):
        base_url = base_url.rstrip("/") + "/chat/completions"
    
    resp = requests.post(
        base_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": settings.ai_temperature,
            "max_tokens": settings.ai_max_tokens,
        },
        timeout=15,
    )
    if resp.ok:
        data = resp.json()
        ans = data["choices"][0]["message"]["content"].strip()
        return ans if ans else None
    return None


def _call_anthropic(prompt: str, config: dict) -> str | None:
    """Call Anthropic Claude API."""
    api_key = config.get("api_key")
    model = config.get("model", "claude-3-5-sonnet-20241022")
    
    if not api_key:
        return None
    
    base_url = config.get("base_url", "https://api.anthropic.com/v1")
    if not base_url.endswith("/messages"):
        base_url = base_url.rstrip("/") + "/messages"
    
    resp = requests.post(
        base_url,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": settings.ai_max_tokens,
            "temperature": settings.ai_temperature,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=15,
    )
    if resp.ok:
        data = resp.json()
        # Anthropic returns content as array of blocks
        content = data.get("content", [])
        if content and isinstance(content, list):
            ans = "".join(block.get("text", "") for block in content if block.get("type") == "text").strip()
            return ans if ans else None
    return None


def synthesize_grounded_patient_reply(query: str, matched: dict, repeat_count: int, language: str) -> str:
    low = query.lower()

    # Check specific item lookups (e.g., glasses, passport, bike, keys)
    if matched["places"]:
        top_place = matched["places"][0]
        if repeat_count == 1:
            msg = f"You last saved that your {top_place['title']} is at: {top_place['exactLocation']}. Would you like me to read the notes for it?"
        else:
            msg = f"Your {top_place['title']} is at {top_place['exactLocation']}. Let's look there together."
        return localize_simple_reply(msg, top_place, language)

    # Check indoor environment guide (bathroom, bedroom, water, shoes)
    if matched["environmentGuides"]:
        eg = matched["environmentGuides"][0]
        return eg["spokenPrompt"]

    # Check people recognition ("Who is Ananya?", "Who likes filter coffee?")
    if matched["people"]:
        p = matched["people"][0]
        if p.get("voicePrompt"):
            return p["voicePrompt"]
        return f"{p['name']} is your {p['relationship']} (met at {p['whereMet']}). Key notes: {p['keyFacts']}."

    # Check memories / life stories
    if matched["memories"]:
        m = matched["memories"][0]
        return f"From your memory album ({m['title']}, {m['eraOrYear'] or ''}): {m['storyText']}"

    # Check medications
    if matched["medications"]:
        med = matched["medications"][0]
        return f"Your {med['medicationName']} ({med['dosageDisplay']}) is scheduled for {med['scheduledTime']}. Current status today: {med['status']}."

    # Check activities
    if matched["activities"]:
        act = matched["activities"][0]
        return f"Yes, you logged '{act['actionTitle']}' today ({act['notes'] or act['category']})."

    # When information is NOT found in SQLite — never invent or fabricate!
    if language == "kn-IN":
        return "ಕ್ಷಮಿಸಿ, ಈ ಮಾಹಿತಿ ನಿಮ್ಮ ಮೆಮೊಸ್ಫಿಯರ್ ದಾಖಲೆಗಳಲ್ಲಿ ಇನ್ನೂ ಉಳಿಸಲಾಗಿಲ್ಲ. ನಾನು ಇದನ್ನು ಈಗ ಉಳಿಸಬೇಕೇ?"
    if language == "hi-IN":
        return "यह जानकारी अभी आपके मेमोस्फियर रिकॉर्ड में सहेजी नहीं गई है। क्या आप इसे अभी सहेजना चाहेंगे?"
    return (
        "I checked your saved personal records, and that information has not been saved yet. "
        "Would you like to tell me so we can save it together?"
    )


def localize_simple_reply(english_msg: str, place_obj: dict, language: str) -> str:
    if language == "kn-IN":
        return f"ನಿಮ್ಮ {place_obj['title']} ಇಲ್ಲಿ ಇದೆ: {place_obj['exactLocation']}."
    if language == "hi-IN":
        return f"आपका {place_obj['title']} यहाँ रखा है: {place_obj['exactLocation']}।"
    return english_msg


def parse_voice_memory_proposal(utterance: str) -> dict:
    """
    C5: Parses a natural voice/text statement into a structured proposal requiring user confirmation
    before modifying or saving to the SQLite database.
    Examples:
      - "Remember that I kept my glasses on the bedside table."
      - "Ananya is my daughter."
      - "I completed my morning walk."
      - "Remind me to pay the electricity bill tomorrow."
    """
    raw = (utterance or "").strip()
    low = raw.lower()

    # 1. Place / Item storage pattern
    m_place = re.search(
        r"(?:remember that\s+)?(?:i\s+)?(?:kept|put|left|stored|parked)\s+(?:my\s+)?(.+?)\s+(?:on|in|at|inside|near)\s+(.+?)(?:\.|$)",
        raw,
        re.IGNORECASE,
    )
    if m_place or any(w in low for w in ("glasses", "keys", "passport", "parked", "bedside", "drawer", "pillar")):
        title = m_place.group(1).strip().title() if m_place else raw.split("—")[0].strip()[:35]
        location = m_place.group(2).strip() if m_place else raw
        return {
            "targetModule": "places",
            "categoryLabel": "Places & Item Finder",
            "requiresConfirmation": True,
            "proposedRecord": {
                "title": title,
                "category": "Parking Spot" if "park" in low or "pillar" in low else "Physical Item",
                "exactLocation": location,
                "notes": f"Voice memory capture: '{raw}'",
                "isPinned": True,
            },
            "confirmationPrompt": f"Save '{title}' at location '{location}' in your Places & Item Finder?",
            "spokenConfirmation": f"I have saved that your {title} is at {location}.",
        }

    # 2. Person / Relationship pattern ("Ananya is my daughter", "Met Rahul at...")
    m_person = re.search(
        r"^([A-Z][a-zA-Z\s]+?)\s+is\s+my\s+([a-zA-Z\s]+?)(?:[.,]|$)",
        raw,
    )
    if m_person or any(w in low for w in ("daughter", "son", "sister", "brother", "teammate", "friend", "mentor", "birthday", "coffee")):
        name = m_person.group(1).strip() if m_person else raw.split("—")[0].split("is")[0].strip()[:35]
        rel_raw = m_person.group(2).strip().title() if m_person else "Family"
        rel_mapped = "Family" if any(f in rel_raw.lower() for f in ("daughter", "son", "mother", "father", "sister", "brother")) else "Friend"
        return {
            "targetModule": "people",
            "categoryLabel": "People & Relationship Memory",
            "requiresConfirmation": True,
            "proposedRecord": {
                "name": name,
                "relationship": rel_mapped,
                "whereMet": "Family / Personal Circle",
                "keyFacts": raw,
                "importantDate": None,
            },
            "confirmationPrompt": f"Save '{name}' ({rel_mapped}) with note '{raw}' to My People?",
            "spokenConfirmation": f"I have saved {name} in your People Memory.",
        }

    # 3. Reminder / Schedule pattern ("Remind me to pay the electricity bill tomorrow")
    if low.startswith("remind me") or "tomorrow" in low or "at 8" in low or "schedule" in low:
        clean_title = re.sub(r"^remind me to\s+", "", raw, flags=re.IGNORECASE).strip().rstrip(".")
        return {
            "targetModule": "reminders",
            "categoryLabel": "Persistent Acknowledgement Reminders",
            "requiresConfirmation": True,
            "proposedRecord": {
                "title": clean_title.capitalize(),
                "category": "Bills/Errands" if "bill" in low else "Personal",
                "scheduledTime": "10:00 AM",
                "priority": "Important" if "bill" in low else "Normal",
                "repeatIntervalSec": 120,
                "snoozeDurationMins": 5,
            },
            "confirmationPrompt": f"Schedule an acknowledgement reminder for '{clean_title}' at 10:00 AM?",
            "spokenConfirmation": f"I have set a reminder to {clean_title} at 10:00 AM.",
        }

    # 4. Default: Completed Daily Activity ("I completed my morning walk")
    clean_act = re.sub(r"^(?:i\s+)?(?:just\s+)?(?:completed|finished|did)\s+(?:my\s+)?", "", raw, flags=re.IGNORECASE).strip().rstrip(".")
    return {
        "targetModule": "activities",
        "categoryLabel": "Daily Activities & Action Log",
        "requiresConfirmation": False,
        "proposedRecord": {
            "actionTitle": clean_act.capitalize() or raw,
            "category": "Health/Meds" if any(w in low for w in ("walk", "vitamin", "water", "medicine")) else "Personal",
            "notes": f"Voice capture: '{raw}'",
            "source": "voice",
        },
        "confirmationPrompt": f"Log completed activity '{clean_act or raw}' to Today's Timeline?",
        "spokenConfirmation": f"I have logged '{clean_act or raw}' in today's activities.",
    }