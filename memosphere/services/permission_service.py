# memosphere/services/permission_service.py
# Core permission enforcement for the Circle of Trust module.

from memosphere.db.schema import get_connection  # we'll create this helper later
from memosphere.models.user import User
from memosphere.models.routine import Routine


def check_permission(user, routine, action="view"):
    """
    Determine whether a user has the required permission for a routine.

    Parameters
    ----------
    user : User or None
        The trusting user (may be None for anonymous view).
    routine : Routine
        The routine to check against.
    action : str
        One of "view", "share", "admin".

    Returns
    -------
    bool
        True if permission is granted, False otherwise.
    """
    if user is None:
        # Allow public view of completed routines only? For now deny.
        return False

    # Check direct permission in the permissions table
    conn = get_connection()
    cur = conn.execute(
        "SELECT permission_level FROM permissions "
        "WHERE routine_id = ? AND contact_id = ?",
        (routine.id, user.id),
    )
    row = cur.fetchone()
    conn.close()

    if row is None:
        # No explicit permission; fall back to user's default role level
        return user.permission_level == "admin" or action == "view" and user.permission_level in ("view", "share")

    permitted_level = row[0]
    # Simple hierarchy: admin > share > view
    hierarchy = {"admin": 3, "share": 2, "view": 1}
    needed = hierarchy.get(action, 1)
    return hierarchy.get(permitted_level, 0) >= needed


def revoke_permission(routine_id, contact_id):
    """Revoke all permission rows for a given routine‑contact pair."""
    from memosphere.db.schema import get_connection
    conn = get_connection()
    conn.execute(
        "DELETE FROM permissions WHERE routine_id = ? AND contact_id = ?",
        (routine_id, contact_id),
    )
    conn.commit()
    conn.close()


def list_permitted_routines(user, routine_ids=None):
    """
    Return a list of routine IDs that the given user has at least 'view' permission on.

    Parameters
    ----------
    user : User
    routine_ids : list of int, optional
        If provided, only check those routine IDs.

    Returns
    -------
    list[int]
    """
    from memosphere.db.schema import get_connection
    conn = get_connection()
    if routine_ids:
        placeholders = ",".join("?" for _ in routine_ids)
        cur = conn.execute(
            f"SELECT routine_id FROM permissions "
            f"WHERE contact_id IN (SELECT id FROM trusted_contacts WHERE user_id = ?) "
            f"AND routine_id IN ({placeholders})",
            [user.id] + routine_ids,
        )
    else:
        cur = conn.execute(
            "SELECT routine_id FROM permissions "
            "WHERE contact_id IN (SELECT id FROM trusted_contacts WHERE user_id = ?)",
            (user.id,),
        )
    ids = [row[0] for row in cur.fetchall()]
    conn.close()
    return ids