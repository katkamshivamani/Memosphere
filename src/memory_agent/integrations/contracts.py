"""Integration contracts between the agent and the host application.

These are *interfaces*, not implementations.  The host application's existing
services implement them (or are wrapped by the adapters in this package).

Design rules encoded here:

* Read methods return plain mappings; adapters normalize them into
  :class:`~memory_agent.models.memory.Record` without inventing data.
* The agent has **no write methods**.  Writes happen only through
  :class:`SuggestionExecutor`, called by the application after explicit user
  approval.
* Every method is user-scoped.  The agent always passes the authenticated user
  id from the session, never an id supplied by the model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional, Protocol, Sequence, runtime_checkable

from pydantic import BaseModel, ConfigDict

from memory_agent.models.suggestion import Suggestion


class SuggestionExecutionResult(BaseModel):
    """Outcome of executing an approved suggestion in the host application."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    record_id: Optional[str] = None
    message: str = ""


@runtime_checkable
class MemoryServiceProtocol(Protocol):
    def search_memories(
        self, user_id: str, query: str, filters: Optional[Mapping[str, Any]] = None
    ) -> Sequence[Mapping[str, Any]]: ...

    def get_memory(self, user_id: str, memory_id: str) -> Optional[Mapping[str, Any]]: ...


@runtime_checkable
class PeopleServiceProtocol(Protocol):
    def search_people(self, user_id: str, query: str) -> Sequence[Mapping[str, Any]]: ...

    def get_person(self, user_id: str, person_id: str) -> Optional[Mapping[str, Any]]: ...

    def get_relationships(
        self, user_id: str, person_id: str
    ) -> Sequence[Mapping[str, Any]]: ...


@runtime_checkable
class PlaceServiceProtocol(Protocol):
    def search_places(self, user_id: str, query: str) -> Sequence[Mapping[str, Any]]: ...

    def get_place_details(self, user_id: str, place_id: str) -> Optional[Mapping[str, Any]]: ...


@runtime_checkable
class ActivityServiceProtocol(Protocol):
    def get_activity_history(
        self,
        user_id: str,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Sequence[Mapping[str, Any]]: ...

    def search_activities(
        self,
        user_id: str,
        query: str,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Sequence[Mapping[str, Any]]: ...


@runtime_checkable
class RoutineServiceProtocol(Protocol):
    def get_routines(self, user_id: str) -> Sequence[Mapping[str, Any]]: ...

    def get_routine_history(
        self, user_id: str, routine_id: str
    ) -> Sequence[Mapping[str, Any]]: ...


@runtime_checkable
class ReminderServiceProtocol(Protocol):
    def get_upcoming_reminders(
        self, user_id: str, horizon_days: int = 7
    ) -> Sequence[Mapping[str, Any]]: ...


@runtime_checkable
class SuggestionExecutor(Protocol):
    """Executes an approved suggestion. Implemented by the host application.

    The executor MUST re-check authentication, approval status and write
    permissions.  It must never trust the model or the UI.
    """

    def execute_suggestion(self, user_id: str, suggestion: Suggestion) -> SuggestionExecutionResult: ...


class AgentIntegrations(BaseModel):
    """Dependency-injection container for host application services."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    memories: Any
    people: Any
    places: Any
    activities: Any
    routines: Any
    reminders: Any
    suggestions: Optional[Any] = None

    def validate(self) -> None:
        """Fail fast if a required service is missing a required read method."""
        required = {
            "memories": ("search_memories", "get_memory"),
            "people": ("search_people", "get_relationships"),
            "places": ("search_places", "get_place_details"),
            "activities": ("get_activity_history", "search_activities"),
            "routines": ("get_routines", "get_routine_history"),
            "reminders": ("get_upcoming_reminders",),
        }
        for attr, methods in required.items():
            service = getattr(self, attr)
            for method in methods:
                if not callable(getattr(service, method, None)):
                    raise TypeError(f"Integration service {attr!r} is missing method {method!r}()")
