# memosphere/services/routine_status_service.py
# Routine status management – owner can mark completed, auto‑missed routines,
# and query routines by status.  All functions use parameterised SQL and
# enforce ownership / sharing rules.

import sqlite3
from datetime import date, timedelta
from datetime import datetime as dt_datetime

from memosphere.db import DB_PATH, init_db
from memosphere.models.routine import Routine


def _get_conn():
    """Return a new sqlite3 connection with the database already initialised."""
    init_db()
    return sqlite3.connect(DB_PATH)


def _row_to_routine(row):
    """Convert a DB row (tuple) into a Routine dict.

    The row may contain extra columns; only the required ones are extracted.
    """
    # expected order: id, owner_id, title, description, frequency, priority, status, last_completed, due_date
    # allow extra columns to be ignored
    routine_id = row[0] if len(row) > 0 else None
    owner_id = row[1] if len(row) > 1 else None
    title = row[2] if len(row) > 2 else None
    description = row[3] if len(row) > 3 else None
    frequency = row[4] if len(row) > 4 else None
    priority = row[5] if len(row) > 5 else None
    status = row[6] if len(row) > 6 else None
    last_completed = row[7] if len(row) > 7 else None
    due_date = row[8] if len(row) > 8 else None
    return {
        "id": routine_id,
        "owner_id": owner_id,
        "title": title,
        "description": description,
        "frequency": frequency,
        "priority": priority,
        "status": status,
        "last_completed": last_completed,
        "due_date": due_date,
    }


# ----------------------------------------------------------------------
# 1️⃣  Mark a routine as completed (owner only)
# ----------------------------------------------------------------------
def mark_routine_completed(routine_id: int, user_id: int) -> bool:
    """Mark a routine as completed.

    Parameters
    ----------
    routine_id : int
        ID of the routine to mark.
    user_id : int
        ID of the current user (must own the routine).

    Returns
    -------
    bool
        True if the status was changed, False if the routine is already
        completed or the user does not own it.
    """
    conn = _get_conn()
    try:
        # verify ownership
        cur = conn.execute(
            "SELECT owner_id, status FROM routines WHERE id = ?",
            (routine_id,),
        )
        row = cur.fetchone()
        if row is None:
            conn.close()
            return False
        owner_id, status = row
        if owner_id != user_id:
            conn.close()
            return False
        if status == "completed":
            # already completed – nothing to do
            conn.close()
            return False

        conn.execute(
            "UPDATE routines SET status = 'completed', last_completed = CURRENT_DATE WHERE id = ?",
            (routine_id,),
        )
        conn.commit()
        return True
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 2️⃣  Auto‑mark routines as missed (owner only)
# ----------------------------------------------------------------------
def update_missing_routines(user_id: int) -> int:
    """Mark routines as 'missed' when their due date has passed.

    Only routines that are NOT already 'completed' are considered.
    Returns the number of rows whose status was changed.

    Parameters
    ----------
    user_id : int
        ID of the owner whose routines are examined.
    """
    conn = _get_conn()
    try:
        today = date.today()
        # fetch routines owned by this user that are not completed
        cur = conn.execute(
            "SELECT id, due_date, status FROM routines "
            "WHERE owner_id = ? AND status != 'completed'",
            (user_id,),
        )
        rows = cur.fetchall()
        changed = 0
        for routine_id, due_date, status in rows:
            # due_date may be a Python date object or an ISO string from SQLite
            due = dt_datetime.strptime(due_date, "%Y-%m-%d").date() if isinstance(due_date, str) else due_date
            if due is not None and due < today:
                conn.execute(
                    "UPDATE routines SET status = 'missed' WHERE id = ?",
                    (routine_id,),
                )
                changed += 1
        conn.commit()
        return changed
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 3️⃣  Get routines filtered by status (owner only)
# ----------------------------------------------------------------------
def get_routines_by_status(user_id: int, status: str) -> list:
    """Return all routines owned by *user_id* that have the given *status*.

    Parameters
    ----------
    user_id : int
        Owner of the routines.
    status : str
        One of 'completed', 'pending', 'missed'.

    Returns
    -------
    list[dict]
        List of routine dicts (as returned by ``_row_to_routine``).
    """
    conn = _get_conn()
    try:
        cur = conn.execute(
            "SELECT id, owner_id, title, description, frequency, priority, status, last_completed, due_date "
            "FROM routines "
            "WHERE owner_id = ? AND status = ?",
            (user_id, status),
        )
        routines = [_row_to_routine(r) for r in cur.fetchall()]
        return routines
    finally:
        conn.close()