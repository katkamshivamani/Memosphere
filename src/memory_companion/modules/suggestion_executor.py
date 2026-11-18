"""Executes approved suggestions inside the application.

Defence in depth: the status must be ``APPROVED``, the session must be valid and
the write permission is checked here again.  The AI model is never consulted.
"""

from __future__ import annotations

import logging
from typing import Optional

from memory_agent.integrations.contracts import SuggestionExecutionResult
from memory_agent.models.suggestion import Suggestion, SuggestionStatus, SuggestionType
from memory_agent.services.suggestion_service import WRITE_PERMISSION_BY_TYPE

from memory_companion.modules.activity_service import ActivityService
from memory_companion.modules.audit import AuditService
from memory_companion.modules.memory_service import MemoryService
from memory_companion.modules.reminder_service import ReminderService
from memory_companion.modules.routine_service import RoutineService

logger = logging.getLogger("memory_companion.suggestions")


class SuggestionExecutorImpl:
    """Applies a user-approved suggestion to the shared database."""

    def __init__(
        self,
        *,
        auth,
        memories: MemoryService,
        reminders: ReminderService,
        activities: ActivityService,
        routines: RoutineService,
        audit: Optional[AuditService] = None,
    ) -> None:
        self._auth = auth
        self._memories = memories
        self._reminders = reminders
        self._activities = activities
        self._routines = routines
        self._audit = audit

    def execute_suggestion(self, user_id: str, suggestion: Suggestion) -> SuggestionExecutionResult:
        if suggestion.status is not SuggestionStatus.APPROVED:
            return SuggestionExecutionResult(
                ok=False, message="Only approved suggestions can be applied."
            )
        if not self._auth.validate_session(user_id):
            return SuggestionExecutionResult(ok=False, message="Your session has expired.")
        permission = WRITE_PERMISSION_BY_TYPE.get(suggestion.type)
        if not permission or not self._auth.has_permission(user_id, permission):
            return SuggestionExecutionResult(
                ok=False, message="You do not have permission to apply this change."
            )

        try:
            if suggestion.type is SuggestionType.SAVE_MEMORY:
                record = self._memories.create_memory(
                    user_id,
                    {
                        "title": suggestion.payload.get("title") or suggestion.title,
                        "content": suggestion.payload.get("content") or suggestion.description,
                        "category": suggestion.payload.get("category") or "general",
                    },
                )
                return self._success(user_id, suggestion, record.get("id"), "Memory saved.")

            if suggestion.type is SuggestionType.UPDATE_MEMORY:
                memory_id = str(suggestion.payload.get("memory_id") or "")
                updates = {
                    key: suggestion.payload[key]
                    for key in ("title", "content", "category")
                    if suggestion.payload.get(key)
                }
                if not memory_id or not updates:
                    return SuggestionExecutionResult(
                        ok=False, message="The update is missing the memory id or new values."
                    )
                record = self._memories.update_memory(user_id, memory_id, updates)
                return self._success(user_id, suggestion, record.get("id"), "Memory updated.")

            if suggestion.type is SuggestionType.CREATE_REMINDER:
                record = self._reminders.create_reminder(
                    user_id,
                    {
                        "title": suggestion.payload.get("title") or suggestion.title,
                        "description": suggestion.payload.get("description")
                        or suggestion.description,
                        "due_at": suggestion.payload.get("due_at"),
                        "source": suggestion.payload.get("source", "agent_suggestion"),
                    },
                )
                return self._success(user_id, suggestion, record.get("id"), "Reminder created.")

            if suggestion.type is SuggestionType.ADD_ACTIVITY:
                record = self._activities.create_activity(
                    user_id,
                    {
                        "name": suggestion.payload.get("name") or suggestion.title,
                        "description": suggestion.payload.get("description")
                        or suggestion.description,
                        "occurred_at": suggestion.payload.get("occurred_at"),
                    },
                )
                return self._success(user_id, suggestion, record.get("id"), "Activity added.")

            if suggestion.type is SuggestionType.CLARIFY_RECORD:
                routine_id = suggestion.payload.get("routine_id")
                if routine_id:
                    event = self._routines.log_completion(
                        user_id, str(routine_id), notes="Logged after user approved a suggestion."
                    )
                    return self._success(
                        user_id, suggestion, event.get("id"), "Routine record added."
                    )
                return SuggestionExecutionResult(
                    ok=False,
                    message=(
                        "Open the record to add the missing details, then approve again. "
                        "Nothing was changed."
                    ),
                )

            return SuggestionExecutionResult(ok=False, message="Unsupported suggestion type.")
        except Exception as exc:
            logger.error(
                "Suggestion execution error type=%s id=%s: %s",
                suggestion.type.value,
                suggestion.id,
                type(exc).__name__,
            )
            return SuggestionExecutionResult(
                ok=False, message="The change could not be applied. Please try again."
            )

    def _success(
        self, user_id: str, suggestion: Suggestion, record_id: Optional[str], message: str
    ) -> SuggestionExecutionResult:
        if self._audit:
            self._audit.log(
                action="suggestion.execute",
                user_id=user_id,
                actor="user_approved_suggestion",
                target_type=suggestion.type.value,
                target_id=record_id,
                metadata={"suggestion_id": suggestion.id},
            )
        return SuggestionExecutionResult(ok=True, record_id=record_id, message=message)
