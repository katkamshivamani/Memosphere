"""Proactive assistance and reminder evaluation.

Triggered by the application (a scheduled reminder approaching, a routine due, a
user-defined event).  There is no background monitoring loop inside the agent.

Careful wording rules:

* absence of an activity record is never treated as proof that the activity did
  not happen;
* duplicate reminders are detected before a suggestion is created;
* quiet hours and the user's proactive preference are respected;
* suggestions are created locally without sending personal data to a cloud model.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict, Field

from memory_agent.config import SettingsStore
from memory_agent.integrations.memory_adapter import ReminderAdapter, RoutineAdapter
from memory_agent.models.suggestion import Suggestion, SuggestionType
from memory_agent.services.suggestion_service import SuggestionService

logger = logging.getLogger("memory_agent.proactive")


class ProactiveTrigger(str, Enum):
    UPCOMING_REMINDER = "upcoming_reminder"
    ROUTINE_DUE = "routine_due"
    EXPECTED_ACTIVITY_MISSING = "expected_activity_missing"
    USER_EVENT = "user_event"


class ProactiveEvent(BaseModel):
    """An application event the agent may evaluate."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    trigger: ProactiveTrigger
    title: str
    description: str = ""
    due_at: Optional[datetime] = None
    reference_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class ProactiveOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handled: bool
    suppressed: bool = False
    reason: str = ""
    suggestion: Optional[Suggestion] = None


_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN.findall((text or "").lower()) if len(token) > 2}


def _similar(a: str, b: str, threshold: float = 0.6) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold


class ProactiveEngine:
    def __init__(
        self,
        *,
        reminders: ReminderAdapter,
        routines: RoutineAdapter,
        suggestions: SuggestionService,
        settings_store: SettingsStore,
        guard,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._reminders = reminders
        self._routines = routines
        self._suggestions = suggestions
        self._settings_store = settings_store
        self._guard = guard
        self._clock = clock

    def evaluate(self, event: ProactiveEvent) -> ProactiveOutcome:
        self._guard.ensure_session(event.user_id)
        settings = self._settings_store.load()

        if not settings.enabled:
            return ProactiveOutcome(handled=False, suppressed=True, reason="Assistant is turned off.")
        if not settings.proactive_enabled:
            return ProactiveOutcome(
                handled=False, suppressed=True, reason="Proactive suggestions are turned off."
            )
        now = self._clock()
        local_now = now.astimezone() if now.tzinfo else now
        if settings.quiet_hours.contains_hour(local_now.hour):
            return ProactiveOutcome(
                handled=False, suppressed=True, reason="Within quiet hours."
            )

        if self._is_duplicate(event):
            return ProactiveOutcome(
                handled=True,
                suppressed=True,
                reason="A similar reminder or suggestion already exists.",
            )

        due_at = event.due_at
        if event.trigger is ProactiveTrigger.UPCOMING_REMINDER:
            suggestion = self._for_upcoming_reminder(event, due_at)
        elif event.trigger is ProactiveTrigger.ROUTINE_DUE:
            suggestion = self._for_routine_due(event)
        elif event.trigger is ProactiveTrigger.EXPECTED_ACTIVITY_MISSING:
            suggestion = self._for_missing_activity(event)
        else:
            suggestion = self._for_user_event(event, due_at)

        if suggestion is None:
            return ProactiveOutcome(handled=False, suppressed=True, reason="Nothing worth suggesting.")

        persisted = self._suggestions.create_from_agent(suggestion)
        logger.info(
            "Proactive suggestion created type=%s trigger=%s user=%s",
            persisted.type.value,
            event.trigger.value,
            event.user_id,
        )
        return ProactiveOutcome(handled=True, suggestion=persisted)

    # ------------------------------------------------------------------ #
    def _is_duplicate(self, event: ProactiveEvent) -> bool:
        try:
            upcoming = self._reminders.upcoming(event.user_id, horizon_days=30)
        except Exception:
            upcoming = []
        for record in upcoming:
            if _similar(record.title, event.title) or (
                event.reference_id and event.reference_id in (record.metadata or {}).values()
            ):
                return True
        for pending in self._suggestions.list_pending(event.user_id):
            if _similar(pending.title, event.title):
                return True
        return False

    def _for_upcoming_reminder(self, event: ProactiveEvent, due_at: Optional[datetime]) -> Suggestion:
        when = due_at.isoformat() if due_at else "the scheduled time"
        return Suggestion(
            user_id=event.user_id,
            type=SuggestionType.CREATE_REMINDER,
            title=f"Prepare for: {event.title}",
            description=(
                f"Your reminder '{event.title}' is due at {when}. "
                "This suggestion would create an earlier preparation reminder."
            ),
            reason="Based on your recorded schedule.",
            payload={
                "title": f"Prepare for {event.title}",
                "description": event.description or f"Preparation reminder for {event.title}.",
                "due_at": due_at.isoformat() if due_at else None,
                "source": event.trigger.value,
                "reference_id": event.reference_id,
            },
        )

    def _for_routine_due(self, event: ProactiveEvent) -> Suggestion:
        return Suggestion(
            user_id=event.user_id,
            type=SuggestionType.CLARIFY_RECORD,
            title=f"Record today's routine: {event.title}",
            description=(
                f"Your routine '{event.title}' is due. When you have done it, you can add a "
                "record so it is easy to remember later."
            ),
            reason="A routine in your saved schedule is due.",
            payload={
                "routine_id": event.reference_id,
                "routine_name": event.title,
                "action": "log_routine_completion",
                "source": event.trigger.value,
            },
        )

    def _for_missing_activity(self, event: ProactiveEvent) -> Suggestion:
        # Never assert that the activity was missed; only note that it is unrecorded.
        return Suggestion(
            user_id=event.user_id,
            type=SuggestionType.CLARIFY_RECORD,
            title=f"No record yet for: {event.title}",
            description=(
                f"There is no record for '{event.title}' today. This does not mean it did "
                "not happen. You can add a record if it did, or set a reminder for next time."
            ),
            reason="An expected activity has no record; records may simply be missing.",
            payload={
                "expected_activity": event.title,
                "reference_id": event.reference_id,
                "action": "confirm_or_log_activity",
                "source": event.trigger.value,
            },
        )

    def _for_user_event(self, event: ProactiveEvent, due_at: Optional[datetime]) -> Suggestion:
        return Suggestion(
            user_id=event.user_id,
            type=SuggestionType.CREATE_REMINDER,
            title=f"Reminder: {event.title}",
            description=event.description or f"Reminder for {event.title}.",
            reason="You asked to be reminded about this event.",
            payload={
                "title": event.title,
                "description": event.description,
                "due_at": due_at.isoformat() if due_at else None,
                "source": event.trigger.value,
            },
        )

    # ------------------------------------------------------------------ #
    # Convenience trigger builders used by the host scheduler
    # ------------------------------------------------------------------ #
    def upcoming_reminder_events(self, user_id: str, horizon_days: int = 2) -> list[ProactiveEvent]:
        self._guard.ensure_session(user_id)
        events = []
        for record in self._reminders.upcoming(user_id, horizon_days=horizon_days):
            due_raw = (record.metadata or {}).get("due_at")
            due = None
            if due_raw:
                try:
                    due = datetime.fromisoformat(str(due_raw).replace("Z", "+00:00"))
                except ValueError:
                    due = None
            events.append(
                ProactiveEvent(
                    user_id=user_id,
                    trigger=ProactiveTrigger.UPCOMING_REMINDER,
                    title=record.title,
                    description=record.content,
                    due_at=due,
                    reference_id=record.id,
                )
            )
        return events
