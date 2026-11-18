"""
MEMOSPHERE Response Parser & Sanitizer
Validates and sanitizes responses returned by external AI providers.
"""
import html
import json
import re
from datetime import date, timedelta


class ResponseParser:
    """Validates and sanitizes AI Q&A answers and structured JSON extractions."""

    VALID_CATEGORIES = {"People", "Places", "Items", "Activities", "Routines"}

    @classmethod
    def sanitize_text(cls, raw_text: str) -> str:
        """Sanitize text output to strip unsafe HTML tags and excess whitespace."""
        if not raw_text or not isinstance(raw_text, str):
            return ""
        # Remove script/style blocks if any
        cleaned = re.sub(r"<(script|style).*?>.*?</\1>", "", raw_text, flags=re.DOTALL | re.IGNORECASE)
        # Strip arbitrary HTML tags
        cleaned = re.sub(r"<[^>]+>", "", cleaned)
        cleaned = html.unescape(cleaned).strip()
        return cleaned

    @classmethod
    def smart_title(cls, raw_text: str) -> str:
        """Capitalize only the first character and preserve the original casing of the rest.

        Prevents over-capitalisation such as 'College Workshop' from
        'college workshop' while keeping proper nouns ('Dr. Meera Nair') intact.
        """
        if not raw_text or not isinstance(raw_text, str):
            return ""
        cleaned = raw_text.strip()
        return cleaned[:1].upper() + cleaned[1:] if cleaned else ""

    @classmethod
    def parse_extraction_json(cls, raw_output: str, original_text: str = "", reference_date: str | None = None) -> dict:
        """
        Parse, validate, and normalize structured JSON returned by an AI provider.
        Raises ValueError if the response cannot be parsed as a valid JSON object.
        """
        if not raw_output or not isinstance(raw_output, str):
            raise ValueError("Empty response from AI provider")

        text = raw_output.strip()
        # Strip markdown code fences if present
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if fence_match:
            text = fence_match.group(1)
        else:
            brace_match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
            if brace_match:
                text = brace_match.group(1)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON structure from AI provider: {exc.msg}") from exc

        if not isinstance(data, dict):
            raise ValueError("AI extraction response must be a JSON object")

        return cls.normalize_extracted_dict(data, original_text=original_text, reference_date=reference_date)

    @classmethod
    def normalize_extracted_dict(cls, data: dict, original_text: str = "", reference_date: str | None = None) -> dict:
        """Ensure all required fields exist, types are valid, and category is one of the 5 allowed."""
        today_str = reference_date or date.today().isoformat()

        raw_cat = str(data.get("category", "Items")).strip().capitalize()
        if raw_cat not in cls.VALID_CATEGORIES:
            # Map common synonyms
            cat_map = {
                "Person": "People",
                "Contact": "People",
                "Contacts": "People",
                "Location": "Places",
                "Place": "Places",
                "Object": "Items",
                "Item": "Items",
                "Belongings": "Items",
                "Activity": "Activities",
                "Event": "Activities",
                "Task": "Activities",
                "Routine": "Routines",
                "Habit": "Routines",
                "Medication": "Routines",
            }
            raw_cat = cat_map.get(raw_cat, "Items")

        title = cls.sanitize_text(str(data.get("title") or "")).strip()
        content = cls.sanitize_text(str(data.get("content") or original_text or "")).strip()
        if not title and content:
            words = content.split()
            title = " ".join(words[:5]).rstrip(".,;!?")

        entity_name = cls.sanitize_text(str(data.get("entity_name") or "")).strip()
        location = cls.sanitize_text(str(data.get("location") or "")).strip()
        event_date = cls.sanitize_text(str(data.get("event_date") or today_str)).strip()

        # Validate YYYY-MM-DD date format or default to reference_date
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", event_date):
            event_date = today_str

        needs_clarification = bool(data.get("needs_clarification", False))
        clarification_question = cls.sanitize_text(str(data.get("clarification_question") or "")).strip()

        return {
            "category": raw_cat,
            "title": title or "Saved Memory",
            "content": content or original_text,
            "entity_name": entity_name,
            "location": location,
            "event_date": event_date,
            "needs_clarification": needs_clarification,
            "clarification_question": clarification_question,
        }
