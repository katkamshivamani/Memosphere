# memosphere/utils/helpers.py
# Small utility helpers used across the Circle of Trust module.

from datetime import date, timedelta


def format_status(status: str) -> str:
    """Return a human‑readable status string."""
    mapping = {"completed": "Completed", "pending": "Pending", "missed": "Missed"}
    return mapping.get(status, status)


def days_until_due(due_date: str) -> int | None:
    """Given a due_date string (YYYY‑MM‑DD), return days remaining (negative if overdue)."""
    if due_date is None:
        return None
    d = date.fromisoformat(due_date)
    delta = d - date.today()
    return delta.days


def is_within_grace_period(due_date: str, grace_minutes: int = 30) -> bool:
    """Check if the current time is within the grace period after the due date.

    For simplicity we only compare dates; a full implementation would include time.
    """
    if due_date is None:
        return False
    d = date.fromisoformat(due_date)
    # Grace period is expressed in minutes; we treat any day after due as outside grace.
    return (date.today() - d).days * 24 * 60 <= grace_minutes