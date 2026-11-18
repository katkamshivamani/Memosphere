"""Suggestion lifecycle: pending -> approved -> completed/failed, or rejected.

Only this service can execute a suggestion, and only when the *user* calls
:meth:`SuggestionService.approve`.  The agent can create pending suggestions but
has no reference to this service's execution path.
"""

from __future__ import annotations

import abc
import logging
import threading
from typing import Optional

from memory_agent.core.exceptions import (
    InvalidRequestError,
    PermissionDeniedError,
    RecordNotFoundError,
    SessionExpiredError,
)
from memory_agent.integrations.contracts import SuggestionExecutor, SuggestionExecutionResult
from memory_agent.models.message import utc_now
from memory_agent.models.suggestion import Suggestion, SuggestionStatus, SuggestionType
from memory_agent.security.permission_guard import PermissionGuard
from memory_agent.security.permissions import Permission

logger = logging.getLogger("memory_agent.suggestions")

#: Write permissions checked again at approval time (defence in depth).
WRITE_PERMISSION_BY_TYPE: dict[SuggestionType, str] = {
    SuggestionType.SAVE_MEMORY: "memory.create",
    SuggestionType.UPDATE_MEMORY: "memory.update",
    SuggestionType.CREATE_REMINDER: "reminders.create",
    SuggestionType.ADD_ACTIVITY: "activities.create",
    SuggestionType.CLARIFY_RECORD: "memory.update",
}


class SuggestionStore(abc.ABC):
    """Persistence contract implemented by the host application."""

    @abc.abstractmethod
    def add(self, suggestion: Suggestion) -> Suggestion: ...

    @abc.abstractmethod
    def get(self, user_id: str, suggestion_id: str) -> Optional[Suggestion]: ...

    @abc.abstractmethod
    def list(self, user_id: str, status: Optional[SuggestionStatus] = None) -> list[Suggestion]: ...

    @abc.abstractmethod
    def update(self, suggestion: Suggestion) -> Suggestion: ...


class InMemorySuggestionStore(SuggestionStore):
    """Test/development store. The desktop app uses the encrypted database."""

    def __init__(self) -> None:
        self._items: dict[str, Suggestion] = {}
        self._lock = threading.RLock()

    def add(self, suggestion: Suggestion) -> Suggestion:
        with self._lock:
            self._items[suggestion.id] = suggestion
        return suggestion

    def get(self, user_id: str, suggestion_id: str) -> Optional[Suggestion]:
        with self._lock:
            item = self._items.get(suggestion_id)
        if item and item.user_id == user_id:
            return item
        return None

    def list(self, user_id: str, status: Optional[SuggestionStatus] = None) -> list[Suggestion]:
        with self._lock:
            items = [s for s in self._items.values() if s.user_id == user_id]
        if status is not None:
            items = [s for s in items if s.status is status]
        return sorted(items, key=lambda s: s.created_at, reverse=True)

    def update(self, suggestion: Suggestion) -> Suggestion:
        with self._lock:
            self._items[suggestion.id] = suggestion
        return suggestion


class SuggestionService:
    """User-approved execution of agent suggestions."""

    def __init__(
        self,
        *,
        store: SuggestionStore,
        executor: SuggestionExecutor,
        guard: PermissionGuard,
    ) -> None:
        self._store = store
        self._executor = executor
        self._guard = guard

    # ------------------------------------------------------------------ #
    def create_from_agent(self, suggestion: Suggestion) -> Suggestion:
        """Persist a pending suggestion produced by a tool."""
        if not suggestion.user_id:
            raise InvalidRequestError("Suggestion is missing its user id.")
        if suggestion.status is not SuggestionStatus.PENDING_APPROVAL:
            raise InvalidRequestError("Agent-created suggestions must be pending approval.")
        persisted = self._store.add(suggestion)
        logger.info(
            "Suggestion created id=%s type=%s user=%s",
            persisted.id,
            persisted.type.value,
            persisted.user_id,
        )
        return persisted

    def list_pending(self, user_id: str) -> list[Suggestion]:
        self._guard.ensure_session(user_id)
        return self._store.list(user_id, SuggestionStatus.PENDING_APPROVAL)

    def list_all(self, user_id: str) -> list[Suggestion]:
        self._guard.ensure_session(user_id)
        return self._store.list(user_id)

    def get(self, user_id: str, suggestion_id: str) -> Suggestion:
        self._guard.ensure_session(user_id)
        suggestion = self._store.get(user_id, suggestion_id)
        if suggestion is None:
            raise RecordNotFoundError(
                "Suggestion not found for this user.",
                user_message="That suggestion no longer exists.",
            )
        return suggestion

    # ------------------------------------------------------------------ #
    def edit(
        self,
        user_id: str,
        suggestion_id: str,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        payload_updates: Optional[dict] = None,
    ) -> Suggestion:
        """Edit a pending suggestion; execution still requires approval."""
        suggestion = self.get(user_id, suggestion_id)
        if suggestion.status is not SuggestionStatus.PENDING_APPROVAL:
            raise InvalidRequestError(
                "Only pending suggestions can be edited.",
                user_message="This suggestion can no longer be edited.",
            )
        edited = suggestion.apply_edit(
            title=title, description=description, payload_updates=payload_updates
        )
        return self._store.update(edited)

    def reject(self, user_id: str, suggestion_id: str) -> Suggestion:
        suggestion = self.get(user_id, suggestion_id)
        if suggestion.status is not SuggestionStatus.PENDING_APPROVAL:
            raise InvalidRequestError(
                "Only pending suggestions can be rejected.",
                user_message="This suggestion has already been handled.",
            )
        updated = suggestion.model_copy(
            update={"status": SuggestionStatus.REJECTED, "updated_at": utc_now()}
        )
        logger.info("Suggestion rejected id=%s user=%s", suggestion_id, user_id)
        return self._store.update(updated)

    def approve(self, user_id: str, suggestion_id: str) -> Suggestion:
        """Execute an approved suggestion through the host application.

        Permission and status are re-checked here.  The AI model is not involved.
        """
        self._guard.ensure_session(user_id)
        suggestion = self.get(user_id, suggestion_id)
        if suggestion.status is not SuggestionStatus.PENDING_APPROVAL:
            raise InvalidRequestError(
                "Suggestion is not awaiting approval.",
                user_message="This suggestion has already been handled.",
            )

        write_permission = WRITE_PERMISSION_BY_TYPE.get(suggestion.type)
        if write_permission is None:
            raise InvalidRequestError("Unsupported suggestion type.")
        if not self._guard.has_permission(user_id, write_permission):
            raise PermissionDeniedError(
                f"Write permission {write_permission!r} not granted.",
                user_message="You do not have permission to apply this change.",
            )

        approved = suggestion.model_copy(
            update={"status": SuggestionStatus.APPROVED, "updated_at": utc_now()}
        )
        self._store.update(approved)

        try:
            outcome: SuggestionExecutionResult = self._executor.execute_suggestion(user_id, approved)
        except SessionExpiredError:
            raise
        except Exception as exc:  # never leak internals to the UI
            logger.error("Suggestion execution failed id=%s: %s", suggestion_id, type(exc).__name__)
            failed = approved.model_copy(
                update={
                    "status": SuggestionStatus.FAILED,
                    "updated_at": utc_now(),
                    "error": "The application could not apply this change.",
                }
            )
            return self._store.update(failed)

        if outcome.ok:
            completed = approved.model_copy(
                update={
                    "status": SuggestionStatus.COMPLETED,
                    "updated_at": utc_now(),
                    "error": None,
                    "payload": {**approved.payload, "result_record_id": outcome.record_id},
                }
            )
            logger.info("Suggestion completed id=%s record=%s", suggestion_id, outcome.record_id)
            return self._store.update(completed)

        failed = approved.model_copy(
            update={
                "status": SuggestionStatus.FAILED,
                "updated_at": utc_now(),
                "error": outcome.message or "The change could not be applied.",
            }
        )
        logger.warning("Suggestion failed id=%s", suggestion_id)
        return self._store.update(failed)

    def is_approved(self, user_id: str, suggestion_id: str) -> bool:
        suggestion = self._store.get(user_id, suggestion_id)
        return bool(suggestion and suggestion.status is SuggestionStatus.COMPLETED)
