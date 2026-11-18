"""Rule-based intent classification.

Deliberately deterministic and local: intent guides which *categories* of
authorized context are retrieved, so it must not depend on the cloud model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class IntentName(str, Enum):
    GREETING = "greeting"
    HELP = "help"
    MEMORY_LOOKUP = "memory_lookup"
    OBJECT_LOCATION = "object_location"
    PEOPLE_LOOKUP = "people_lookup"
    PLACE_LOOKUP = "place_lookup"
    ACTIVITY_HISTORY = "activity_history"
    ROUTINE_LOOKUP = "routine_lookup"
    REMINDER_LOOKUP = "reminder_lookup"
    MEMORY_SAVE_REQUEST = "memory_save_request"
    MEMORY_UPDATE_REQUEST = "memory_update_request"
    REMINDER_REQUEST = "reminder_request"
    CONFIRMATION_QUESTION = "confirmation_question"
    GENERAL = "general"


@dataclass(frozen=True)
class Intent:
    name: IntentName
    categories: tuple[str, ...] = ()
    needs_personal_data: bool = False
    is_medical: bool = False
    is_question: bool = False
    keywords: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "name": self.name.value,
            "categories": list(self.categories),
            "needs_personal_data": self.needs_personal_data,
            "is_medical": self.is_medical,
        }


_WORD = re.compile(r"[a-z0-9']+")

_MEDICAL_TERMS = {
    "medicine", "medication", "medicines", "pill", "pills", "tablet", "tablets",
    "dose", "dosage", "prescription", "insulin", "inhaler", "pharmacy", "symptoms",
    "pain", "diagnosis", "doctor", "nurse", "clinic",
}
_CONFIRMATION_TEMPLATES = (
    "did i", "have i", "was i", "am i", "do i", "is it", "are my", "was my",
)
_SAVE_PHRASES = (
    "remember that", "remember this", "please remember", "save this", "save that",
    "note that", "make a note", "keep in mind", "store this",
)
_UPDATE_PHRASES = ("update my", "change my", "correct my", "edit my", "fix my memory")
_REMINDER_PHRASES = ("remind me", "set a reminder", "create a reminder", "add a reminder", "reminder for")
_ROUTINE_TERMS = {"routine", "routines", "habit", "habits", "every day", "daily", "schedule", "regularly"}
_REMINDER_TERMS = {"reminder", "reminders", "upcoming", "appointment", "appointments", "due", "calendar"}
_PEOPLE_TERMS = {
    "who", "person", "people", "daughter", "son", "wife", "husband", "friend",
    "carer", "caregiver", "doctor", "family", "neighbour", "neighbor", "relationship",
}
_PLACE_TERMS = {
    "where", "place", "room", "kitchen", "bedroom", "bathroom", "garden", "garage",
    "office", "study", "shop", "clinic", "pharmacy", "address", "location",
}
_ACTIVITY_TERMS = {
    "did", "done", "activity", "activities", "today", "yesterday", "morning",
    "evening", "walk", "ate", "eat", "took", "went", "visited", "exercise",
}
_OBJECT_TERMS = {
    "wallet", "keys", "key", "glasses", "spectacles", "passport", "phone", "purse",
    "bag", "documents", "papers", "remote", "hearing", "aid", "umbrella", "watch",
}
_PERSONAL_TERMS = {
    "i", "my", "me", "mine", "we", "our", "remember", "memory", "memories", "forgot",
}

_CATEGORY_ORDER = ("memory", "people", "places", "activities", "routines", "reminders")


class IntentClassifier:
    """Keyword/structure based classifier with no network dependency."""

    def classify(self, text: str) -> Intent:
        raw = (text or "").strip()
        lowered = raw.lower()
        tokens = set(_WORD.findall(lowered))
        is_question = "?" in raw or lowered.startswith(
            ("where", "what", "who", "when", "did", "do", "have", "is", "are", "can", "could")
        )
        is_medical = bool(tokens & _MEDICAL_TERMS)
        confirmation = any(lowered.startswith(template) or f" {template}" in f" {lowered}"
                           for template in _CONFIRMATION_TEMPLATES)

        if not raw:
            return Intent(IntentName.GENERAL)
        if lowered in {"hi", "hello", "hey", "good morning", "good evening"} or lowered.startswith("hello "):
            return Intent(IntentName.GREETING, is_question=False)
        if any(phrase in lowered for phrase in ("what can you do", "how do you work", "help me", "what are you")):
            return Intent(IntentName.HELP, is_question=True)

        if any(phrase in lowered for phrase in _UPDATE_PHRASES):
            return Intent(
                IntentName.MEMORY_UPDATE_REQUEST,
                categories=("memory",),
                needs_personal_data=True,
                is_medical=is_medical,
                is_question=is_question,
            )
        if any(phrase in lowered for phrase in _SAVE_PHRASES):
            return Intent(
                IntentName.MEMORY_SAVE_REQUEST,
                categories=("memory",),
                needs_personal_data=True,
                is_medical=is_medical,
                is_question=is_question,
            )
        if any(phrase in lowered for phrase in _REMINDER_PHRASES):
            return Intent(
                IntentName.REMINDER_REQUEST,
                categories=("reminders", "memory"),
                needs_personal_data=True,
                is_medical=is_medical,
                is_question=is_question,
            )

        categories: list[str] = []
        name = IntentName.GENERAL

        if tokens & _PLACE_TERMS or tokens & _OBJECT_TERMS:
            name = IntentName.OBJECT_LOCATION
            categories.extend(["memory", "places"])
        if tokens & _PEOPLE_TERMS:
            name = IntentName.PEOPLE_LOOKUP
            categories.append("people")
        if tokens & _REMINDER_TERMS:
            name = IntentName.REMINDER_LOOKUP
            categories.append("reminders")
        if tokens & _ROUTINE_TERMS:
            name = IntentName.ROUTINE_LOOKUP
            categories.append("routines")
        if tokens & _ACTIVITY_TERMS and name in (IntentName.GENERAL, IntentName.CONFIRMATION_QUESTION):
            name = IntentName.ACTIVITY_HISTORY
            categories.append("activities")
        if confirmation:
            name = IntentName.CONFIRMATION_QUESTION
            categories.extend(["activities", "routines"])
        if is_medical:
            categories.extend(["activities", "routines", "reminders"])
        if not categories and (tokens & _PERSONAL_TERMS or confirmation):
            name = IntentName.MEMORY_LOOKUP
            categories.append("memory")

        unique_categories = tuple(dict.fromkeys(c for c in _CATEGORY_ORDER if c in categories))
        needs_personal_data = bool(unique_categories) or bool(tokens & _PERSONAL_TERMS)

        if name is IntentName.GENERAL and needs_personal_data:
            name = IntentName.MEMORY_LOOKUP

        return Intent(
            name=name,
            categories=unique_categories,
            needs_personal_data=needs_personal_data,
            is_medical=is_medical,
            is_question=is_question,
            keywords=tuple(sorted(tokens & (_MEDICAL_TERMS | _OBJECT_TERMS | _PEOPLE_TERMS))),
        )
