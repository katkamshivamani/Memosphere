# memosphere/services/analytics_service.py
# Weekly analytics for Memosphere – completion percentages, counts, streaks.
# All functions enforce ownership and sharing permissions where appropriate.
# Percentages are labelled ESTIMATES because the DB stores only the most recent
# last_completed date per routine – we cannot tell whether a routine was
# completed multiple times in a given week.

import sqlite3
from datetime import date, datetime, timedelta

from memosphere.db import DB_PATH, init_db
from memosphere.services.routine_status_service import get_routines_by_status


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _parse_date(val):
    """Convert a date value (Python date, ISO string, or None) to a date object."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    # ISO string like '2025-01-15'
    try:
        return datetime.strptime(str(val), "%Y-%m-%d").date()
    except Exception:
        return None


def _iso_week_dates(dt=None):
    """Return (monday, sunday) for the ISO week containing *dt*."""
    if dt is None:
        dt = date.today()
    # ISO calendar: Monday = 1, Sunday = 7
    iso = dt.isocalendar()
    monday = date.fromisocalendar(iso[1], 1, iso[2])
    sunday = date.fromisocalendar(iso[1], 7, iso[2])
    return monday, sunday


def _week_start_end(week_index=None):
    """Return (start, end) dates for the *week_index*‑th week from today.
    week_index = 0 → current week, -1 → last week, etc."""
    today = date.today()
    if week_index is None:
        week_index = 0
    # go back week_index weeks
    delta = timedelta(weeks=-week_index)
    target = today + delta
    return _iso_week_dates(target)


# ------------------------------------------------------------------
# 1️⃣  Weekly completion percentage (estimate)
# ------------------------------------------------------------------
def get_weekly_completion_pct(user_id, week_index=0):
    """Return the percentage of the user's routines that were completed
    during the specified ISO week.

    The calculation is an ESTIMATE because the database stores only the
    most recent last_completed date per routine – we cannot tell whether a
    routine was completed multiple times in the week.

    Parameters
    ----------
    user_id : int
    week_index : int, optional
        0 = current week, -1 = last week, etc.

    Returns
    -------
    float | None
        Percentage 0‑100, rounded to the nearest whole number, or None if
        no routines exist for the user.
    """
    monday, sunday = _iso_week_dates() if week_index == 0 else _week_start_end(week_index)
    routines = get_routines_by_status(user_id, "completed")  # all completed routines for this user

    if not routines:
        return 0.0

    # count how many have last_completed within the target week
    completed_in_week = sum(
        1 for r in routines
        if _parse_date(r["last_completed"]) and monday <= _parse_date(r["last_completed"]) <= sunday
    )
    pct = round(completed_in_week / len(routines) * 100)
    return pct


# ------------------------------------------------------------------
# 2️⃣  Weekly counts (completed / pending / missed)
# ------------------------------------------------------------------
def get_weekly_counts(user_id, week_index=0):
    """Return completed / pending / missed counts for the given ISO week.

    The 'completed' count is based on last_completed falling within the week.
    The 'pending' and 'missed' counts are based on the current state (no date filter).

    Parameters
    ----------
    user_id : int
    week_index : int, optional

    Returns
    -------
    dict
        {'completed': n, 'pending': n, 'missed': n}
    """
    monday, sunday = _iso_week_dates() if week_index == 0 else _week_start_end(week_index)

    routines = get_routines_by_status(user_id, "completed")
    completed = sum(
        1 for r in routines
        if _parse_date(r["last_completed"]) and monday <= _parse_date(r["last_completed"]) <= sunday
    )

    # pending: all routines currently pending (no date filter)
    pending_routines = get_routines_by_status(user_id, "pending")
    pending = len(pending_routines)

    # missed: all routines currently marked missed
    missed_routines = get_routines_by_status(user_id, "missed")
    missed = len(missed_routines)

    return {"completed": completed, "pending": pending, "missed": missed}


# ------------------------------------------------------------------
# 3️⃣  Weekly streak (consecutive weeks with at least one completed routine)
# ------------------------------------------------------------------
def get_weekly_streak(user_id):
    """Return the number of consecutive ISO weeks ending with the most
    recent week in which the user completed at least one routine.

    If the user has never completed a routine, the streak is 0.
    """
    # collect weeks (as integers) where at least one routine was completed
    completed_routines = get_routines_by_status(user_id, "completed")
    weeks_with_completion = set()
    for r in completed_routines:
        if r["last_completed"]:
            d = _parse_date(r["last_completed"])
            if d:
                iso_week = d.isocalendar()[1]  # ISO week number
                weeks_with_completion.add(iso_week)

    if not weeks_with_completion:
        return 0

    # sort weeks and find the longest consecutive suffix
    sorted_weeks = sorted(weeks_with_completion)
    # the most recent week (highest number) is the baseline
    recent = max(sorted_weeks)
    streak = 0
    # walk backwards from the most recent week
    for w in reversed(sorted_weeks):
        if w == recent - streak:
            streak += 1
        else:
            break
    return streak


# ------------------------------------------------------------------
# 4️⃣  Weekly trend (percentage for the last N weeks)
# ------------------------------------------------------------------
def get_weekly_trend(user_id, weeks=4):
    """Return a list of completion percentages for the last *weeks* ISO weeks,
    starting with the oldest and ending with the most recent week.

    Each value is an ESTIMATE (see get_weekly_completion_pct).
    """
    trend = []
    for i in range(weeks, 0, -1):  # oldest first
        pct = get_weekly_completion_pct(user_id, week_index=i - 1)  # i-1 because our indexing: 0=current
        trend.append(pct)
    return trend