# memosphere/models/routine.py
# Data model for a routine task.

from memosphere.config import (
    PRIORITY_HIGH,
    PRIORITY_MEDIUM,
    PRIORITY_LOW,
    VALID_PRIORITIES,
)


class Routine:
    """A routine task owned by a user."""

    def __init__(
        self,
        routine_id,
        owner_id,
        title,
        description=None,
        frequency="daily",
        priority="Medium",
        status="pending",
        last_completed=None,
        due_date=None,
    ):
        if priority not in VALID_PRIORITIES:
            raise ValueError(f"Invalid priority '{priority}'. Must be one of {VALID_PRIORITIES}")
        self.id = routine_id
        self.owner_id = owner_id
        self.title = title
        self.description = description
        self.frequency = frequency
        self.priority = priority
        self.status = status
        self.last_completed = last_completed
        self.due_date = due_date

    @property
    def is_overdue(self):
        """Return True if the routine is past due and not yet completed."""
        if self.status == "completed":
            return False
        if self.due_date is None:
            return False
        from datetime import date
        return date.today() > self.due_date

    @property
    def is_high_priority(self):
        return self.priority == PRIORITY_HIGH

    def __repr__(self):
        return f"<Routine {self.title} ({self.priority}, {self.status})>"