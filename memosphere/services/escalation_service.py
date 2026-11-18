# memosphere/services/escalation_service.py
# Smart escalation for overdue high‑priority routines.
# – Detects routines overdue past a configurable grace period.
# – Sends notifications only to active contacts with active sharing permission.
# – Prevents duplicate alerts via a DB‑backed unique index.
# – Never automatically marks routines as completed.

import sqlite3
from datetime import date, datetime, timedelta

from memosphere.db import DB_PATH, init_db
from memosphere.services.contact_service import get_contacts, set_active
from memosphere.services.routine_permission_service import (
    get_shared_routines,
    check_permission,
)


def _get_conn():
    """Return a new sqlite3 connection with the DB already initialised."""
    init_db()
    return sqlite3.connect(DB_PATH)


# ------------------------------------------------------------------
# Grace‑period configuration (default 30 minutes, as required)
# ------------------------------------------------------------------
GRACE_PERIOD_MINUTES = 30


# ------------------------------------------------------------------
# 1️⃣  Detect routines that are overdue past the grace period.
# ------------------------------------------------------------------
def detect_overdue_routines(user_id, grace_minutes=GRACE_PERIOD_MINUTES):
    """Return a list of routines that are overdue for the given user.

    A routine is considered overdue when
      • its status is NOT 'completed', and
      • its due_date has passed, and
      • the elapsed time since due_date exceeds the grace period.

    Parameters
    ----------
    user_id : int
        Owner of the routines to check.
    grace_minutes : int, optional
        Grace period in minutes (default 30).

    Returns
    -------
    list[dict]
        Each entry contains: routine_id, title, due_date, elapsed_minutes.
    """
    conn = _get_conn()
    try:
        today = date.today()
        # routines owned by this user that are not completed
        cur = conn.execute(
            "SELECT id, title, due_date, status FROM routines "
            "WHERE owner_id = ? AND status != 'completed'",
            (user_id,),
        )
        rows = cur.fetchall()
        overdue = []
        for routine_id, title, due_date, status in rows:
            if due_date is None:
                continue
            # compute elapsed minutes since due_date
            if isinstance(due_date, str):
                d = datetime.strptime(due_date, "%Y-%m-%d").date()
            else:
                d = due_date
            elapsed = (today - d).days * 24 * 60 + (today - d).seconds // 60
            # simple approximation: we only care about whole‑day difference
            # for the grace‑period check; if the date is today or earlier,
            # elapsed >= 0.
            if elapsed < 0:
                # due_date is in the future – not overdue yet
                continue
            if elapsed > grace_minutes:
                overdue.append(
                    {
                        "routine_id": routine_id,
                        "title": title,
                        "due_date": due_date,
                        "elapsed_minutes": elapsed,
                    }
                )
        return overdue
    finally:
        conn.close()


# ------------------------------------------------------------------
# 2️⃣  Send escalation notifications to eligible contacts.
# ------------------------------------------------------------------
def send_escalation_notifications(user_id, overdue_list):
    """Send notifications for the given overdue routines.

    For each routine, find contacts that
      • have an active permission on that routine, and
      • are themselves active (not deactivated).
    Insert a row into escalation_logs for each new (routine_id, contact_id)
    pair – the unique index prevents duplicates.

    Returns the number of *new* notifications inserted.
    """
    conn = _get_conn()
    new_count = 0
    try:
        for routine_info in overdue_list:
            routine_id = routine_info["routine_id"]
            # 1️⃣  Find contacts with active permission on this routine
            shared_ids = get_shared_routines(routine_id)  # returns list of contact_ids
            # 2️⃣  Filter to contacts that are active and belong to the same user
            # (get_shared_routines already filters by permission, but we also
            #  need to verify the contact’s own active flag.)
            # Fetch all contacts for this user and keep only active ones
            all_contacts = get_contacts(user_id=user_id)
            active_contacts = [c for c in all_contacts if c.is_active]

            for contact in active_contacts:
                contact_id = contact.id
                if contact_id not in shared_ids:
                    continue  # no permission for this routine

                # 3️⃣  Try to insert into escalation_logs – the unique index
                #    (routine_id, contact_id, DATE(alerted_at)) prevents
                #    duplicate alerts for the same day.
                try:
                    conn.execute(
                        "INSERT INTO escalation_logs (routine_id, contact_id, alerted_at, resolved_at, notes)"
                        " VALUES (?, ?, CURRENT_TIMESTAMP, NULL, NULL)",
                        (routine_id, contact_id),
                    )
                    conn.commit()
                    new_count += 1
                except sqlite3.IntegrityError:
                    # duplicate (same routine+contact+day) – skip
                    pass
        return new_count
    finally:
        conn.close()


# ------------------------------------------------------------------
# 3️⃣  Retrieve escalation logs for a user (optionally filtered).
# ------------------------------------------------------------------
def get_escalation_logs(user_id, resolved=None):
    """Return escalation‑log rows for routines owned by *user_id*.

    Parameters
    ----------
    user_id : int
    resolved : bool | None
        • True  – only show resolved logs,
        • False – only show unresolved logs,
        • None  – show all logs.

    Returns
    -------
    list[dict]
    """
    conn = _get_conn()
    try:
        if resolved is None:
            cur = conn.execute(
                "SELECT id, routine_id, contact_id, alerted_at, resolved_at, notes "
                "FROM escalation_logs WHERE routine_id IN "
                "(SELECT id FROM routines WHERE owner_id = ?)",
                (user_id,),
            )
        elif resolved:
            cur = conn.execute(
                "SELECT id, routine_id, contact_id, alerted_at, resolved_at, notes "
                "FROM escalation_logs "
                "WHERE routine_id IN "
                "(SELECT id FROM routines WHERE owner_id = ?) AND resolved_at IS NOT NULL",
                (user_id,),
            )
        else:
            cur = conn.execute(
                "SELECT id, routine_id, contact_id, alerted_at, resolved_at, notes "
                "FROM escalation_logs "
                "WHERE routine_id IN "
                "(SELECT id FROM routines WHERE owner_id = ?) AND resolved_at IS NULL",
                (user_id,),
            )
        rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "routine_id": r[1],
                "contact_id": r[2],
                "alerted_at": r[3],
                "resolved_at": r[4],
                "notes": r[5] or "",
            }
            for r in rows
        ]
    finally:
        conn.close()


# ------------------------------------------------------------------
# 4️⃣  Mark a specific escalation log as resolved.
# ------------------------------------------------------------------
def resolve_escalation(log_id, user_id):
    """Mark the escalation log *log_id* as resolved.

    Only the owner of the routine may resolve it.
    Returns True if a row was updated, False otherwise.
    """
    conn = _get_conn()
    try:
        # verify ownership first
        cur = conn.execute(
            "SELECT owner_id FROM routines WHERE id IN "
            "(SELECT routine_id FROM escalation_logs WHERE id = ?)",
            (log_id,),
        )
        row = cur.fetchone()
        if row is None or row[0] != user_id:
            conn.close()
            return False

        cur = conn.execute(
            "UPDATE escalation_logs SET resolved_at = CURRENT_TIMESTAMP WHERE id = ?",
            (log_id,),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()