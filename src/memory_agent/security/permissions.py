"""Permission identifiers used by tools and the application permission system."""

from __future__ import annotations

from enum import Enum


class Permission(str, Enum):
    MEMORY_READ = "memory.read"
    MEMORY_SUGGEST_CREATE = "memory.suggest_create"
    MEMORY_SUGGEST_UPDATE = "memory.suggest_update"
    PEOPLE_READ = "people.read"
    PLACES_READ = "places.read"
    ACTIVITIES_READ = "activities.read"
    ROUTINES_READ = "routines.read"
    REMINDERS_READ = "reminders.read"
    REMINDERS_SUGGEST_CREATE = "reminders.suggest_create"

    @property
    def is_read(self) -> bool:
        return self.value.endswith(".read")

    @property
    def is_suggestion(self) -> bool:
        return ".suggest_" in self.value


READ_PERMISSIONS: tuple[Permission, ...] = (
    Permission.MEMORY_READ,
    Permission.PEOPLE_READ,
    Permission.PLACES_READ,
    Permission.ACTIVITIES_READ,
    Permission.ROUTINES_READ,
    Permission.REMINDERS_READ,
)

SUGGESTION_PERMISSIONS: tuple[Permission, ...] = (
    Permission.MEMORY_SUGGEST_CREATE,
    Permission.MEMORY_SUGGEST_UPDATE,
    Permission.REMINDERS_SUGGEST_CREATE,
)

ALL_PERMISSIONS: tuple[Permission, ...] = READ_PERMISSIONS + SUGGESTION_PERMISSIONS

#: Permissions that authorize *writes* executed by the application after user
#: approval.  The agent itself never holds these; the approval service checks
#: them again at execution time.
WRITE_PERMISSIONS = frozenset(
    {
        "memory.create",
        "memory.update",
        "reminders.create",
        "activities.create",
    }
)
