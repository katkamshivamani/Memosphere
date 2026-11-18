# memosphere/services/routine_permission_service.py
# Six functions for permission‑based routine sharing.
# All operations enforce ownership and contact status.
# Uses parameterised SQL; transactions where appropriate.

import sqlite3
from datetime import datetime

from memosphere.db import DB_PATH, init_db
from memosphere.models.contact import Contact
from memosphere.models.routine import Routine


def _get_conn():
    init_db()
    return sqlite3.connect(DB_PATH)


def _row_to_routine(row):
    """Convert a DB row (from routines table) into a Routine instance."""
    routine_id, owner_id, title, description, frequency, priority, status, last_completed, due_date = row
    return Routine(
        routine_id=routine_id,
        owner_id=owner_id,
        title=title,
        description=description,
        frequency=frequency,
        priority=priority,
        status=status,
        last_completed=last_completed,
        due_date=due_date,
    )


def share_routine(routine_id, contact_id, user_id):
    """Share a specific routine with a trusted contact.

    Parameters
    ----------
    routine_id : int
        ID of the routine to share.
    contact_id : int
        ID of the trusted contact.
    user_id : int
        ID of the current user (owner of the routine and the contact).

    Returns
    -------
    bool
        True if the permission was granted, False if the contact is inactive,
        the user does not own the routine, or a duplicate active permission exists.
    """
    conn = _get_conn()
    # verify user owns the routine
    cur = conn.execute(
        "SELECT owner_id FROM routines WHERE id = ?",
        (routine_id,),
    )
    row = cur.fetchone()
    if row is None or row[0] != user_id:
        conn.close()
        return False

    # verify contact belongs to the same user and is active
    cur = conn.execute(
        "SELECT active FROM trusted_contacts WHERE id = ? AND user_id = ?",
        (contact_id, user_id),
    )
    contact_row = cur.fetchone()
    if contact_row is None or contact_row[0] != 1:
        conn.close()
        return False

    # try to insert permission; the partial unique index will prevent duplicates
    try:
        conn.execute(
            """
            INSERT INTO permissions (routine_id, contact_id, owner_user_id, status, granted_at, updated_at)
            VALUES (?, ?, ?, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (routine_id, contact_id, user_id),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        # duplicate active permission (unique index violation)
        conn.close()
        return False


def get_shared_routines(contact_id):
    """Return a list of routine IDs that a contact has an active permission for.

    Parameters
    ----------
    contact_id : int

    Returns
    -------
    list[int]
    """
    conn = _get_conn()
    cur = conn.execute(
        "SELECT routine_id FROM permissions WHERE contact_id = ? AND status = 'active'",
        (contact_id,),
    )
    ids = [row[0] for row in cur.fetchall()]
    conn.close()
    return ids


def get_routine_contacts(routine_id):
    """Return a list of contact IDs that have an active permission on a routine.

    Parameters
    ----------
    routine_id : int

    Returns
    -------
    list[int]
    """
    conn = _get_conn()
    cur = conn.execute(
        "SELECT contact_id FROM permissions WHERE routine_id = ? AND status = 'active'",
        (routine_id,),
    )
    ids = [row[0] for row in cur.fetchall()]
    conn.close()
    return ids


def check_permission(contact_id, routine_id, user_id):
    """Check whether a contact has active permission to access a routine.

    Parameters
    ----------
    contact_id : int
    routine_id : int
    user_id : int – must own both the routine and the contact.

    Returns
    -------
    bool
    """
    conn = _get_conn()
    # verify ownership of routine
    cur = conn.execute(
        "SELECT owner_id FROM routines WHERE id = ? AND owner_id = ?",
        (routine_id, user_id),
    )
    if cur.fetchone() is None:
        conn.close()
        return False
    # verify ownership of contact
    cur = conn.execute(
        "SELECT active FROM trusted_contacts WHERE id = ? AND user_id = ?",
        (contact_id, user_id),
    )
    contact_row = cur.fetchone()
    if contact_row is None or contact_row[0] != 1:
        conn.close()
        return False
    # check active permission
    cur = conn.execute(
        "SELECT 1 FROM permissions WHERE routine_id = ? AND contact_id = ? AND status = 'active'",
        (routine_id, contact_id),
    )
    exists = cur.fetchone() is not None
    conn.close()
    return exists


def revoke_permission(routine_id, contact_id, user_id):
    """Revoke a contact's permission on a routine.

    Parameters
    ----------
    routine_id : int
    contact_id : int
    user_id : int – must own the routine and the contact.

    Returns
    -------
    bool
        True if a permission row was revoked, False if no active permission
        existed for this pair.
    """
    conn = _get_conn()
    # verify ownership
    cur = conn.execute(
        "SELECT owner_id FROM routines WHERE id = ? AND owner_id = ?",
        (routine_id, user_id),
    )
    if cur.fetchone() is None:
        conn.close()
        return False
    cur = conn.execute(
        "SELECT active FROM trusted_contacts WHERE id = ? AND user_id = ?",
        (contact_id, user_id),
    )
    if cur.fetchone() is None or cur.fetchone()[0] != 1:
        conn.close()
        return False

    # set status to revoked (soft delete)
    cur = conn.execute(
        "UPDATE permissions SET status = 'revoked', updated_at = CURRENT_TIMESTAMP "
        "WHERE routine_id = ? AND contact_id = ? AND status = 'active'",
        (routine_id, contact_id),
    )
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0


def restore_permission(routine_id, contact_id, user_id):
    """Re‑activate a previously revoked permission.

    Parameters
    ----------
    routine_id : int
    contact_id : int
    user_id : int – must own the routine and the contact.

    Returns
    -------
    bool
        True if the permission was restored (was previously revoked),
        False if it was already active or ownership check failed.
    """
    conn = _get_conn()
    # verify ownership
    cur = conn.execute(
        "SELECT owner_id FROM routines WHERE id = ? AND owner_id = ?",
        (routine_id, user_id),
    )
    if cur.fetchone() is None:
        conn.close()
        return False
    # verify contact active
    cur = conn.execute(
        "SELECT active FROM trusted_contacts WHERE id = ? AND user_id = ?",
        (contact_id, user_id),
    )
    contact_row = cur.fetchone()
    if contact_row is None or contact_row[0] != 1:
        conn.close()
        return False

    # try to set status back to active; the unique index will allow it
    # because there is now a revoked row; we just update it.
    cur = conn.execute(
        """
        UPDATE permissions
        SET status = 'active', updated_at = CURRENT_TIMESTAMP
        WHERE routine_id = ? AND contact_id = ? AND status = 'revoked'
        """,
        (routine_id, contact_id),
    )
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0