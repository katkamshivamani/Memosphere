# memosphere/services/contact_service.py
# Back‑end service for trusted‑contact management.
# All queries are parameterised and enforce ownership of the contacting user.

import sqlite3
from datetime import datetime

from memosphere.db import DB_PATH, init_db
from memosphere.models.contact import Contact


def _get_conn():
    """Return a new sqlite3 connection with the database already initialised."""
    init_db()  # ensures schema + migration are up‑to‑date
    return sqlite3.connect(DB_PATH)


def _row_to_contact(row):
    """Convert a DB row (tuple) into a Contact model instance."""
    # row order: id, user_id, contact_name, email, phone, role, active, created_at, updated_at
    contact_id, user_id, name, email, phone, role, active, created_at, updated_at = row
    return Contact(
        contact_id=contact_id,
        owner_user_id=user_id,
        contact_name=name,
        email=email,
        phone=phone,
        role=role,
        active=bool(active),
        created_at=created_at,
        updated_at=updated_at,
    )


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def add_contact(user_id, name, role, email=None, phone=None):
    """Add a new trusted contact for the given owner.

    Parameters
    ----------
    user_id : int
        The ID of the user who owns this contact (enforces ownership).
    name : str
        Contact name (must be non‑empty).
    role : str
        One of the valid roles defined in config.py (Family, Caregiver,
        Study Buddy, Roommate).
    email : str | None
        Optional email address.
    phone : str | None
        Optional phone number.

    Returns
    -------
    Contact
        The newly created Contact instance, or None if the name is invalid.
    """
    if not name or not name.strip():
        return None
    if role not in ("Family", "Caregiver", "Study Buddy", "Roommate"):
        raise ValueError(f"Invalid role '{role}'. Must be one of Family, Caregiver, Study Buddy, Roommate.")

    conn = _get_conn()
    cur = conn.execute(
        """
        INSERT INTO trusted_contacts (user_id, contact_name, role, email, phone, active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (user_id, name.strip(), role, email.strip() if email else None, phone.strip() if phone else None),
    )
    conn.commit()

    # Fetch the row we just inserted
    cur2 = conn.execute(
        "SELECT id, user_id, contact_name, role, email, phone, active, created_at, updated_at "
        "FROM trusted_contacts WHERE id = ?",
        (cur.lastrowid,),
    )
    row = cur2.fetchone()
    conn.close()
    return _row_to_contact(row)


def get_contacts(user_id):
    """Return all contacts owned by *user_id*, ordered by name.

    Parameters
    ----------
    user_id : int
        The ID of the user whose contacts we want.

    Returns
    -------
    list[Contact]
        A list of Contact objects.  Empty list if the user has no contacts.
    """
    conn = _get_conn()
    cur = conn.execute(
        """
        SELECT id, user_id, contact_name, role, email, phone, active, created_at, updated_at
        FROM trusted_contacts
        WHERE user_id = ?
        ORDER BY contact_name COLLATE NOCASE
        """,
        (user_id,),
    )
    contacts = [_row_to_contact(r) for r in cur.fetchall()]
    conn.close()
    return contacts


def edit_contact(contact_id, user_id, name=None, role=None, email=None, phone=None):
    """Edit an existing contact’s details.

    Only the fields supplied are updated; other fields keep their current values.
    Ownership is enforced – *contact_id* must belong to *user_id*.

    Parameters
    ----------
    contact_id : int
        ID of the contact to edit.
    user_id : int
        ID of the owner (used only for the ownership check).
    name : str | None
        New contact name; must be non‑empty if provided.
    role : str | None
        New role; must be one of the valid roles.
    email : str | None
        New email address.
    phone : str | None
        New phone number.

    Returns
    -------
    Contact | None
        The updated Contact instance, or None if the contact does not exist
        or the user does not own it.
    """
    if role and role not in ("Family", "Caregiver", "Study Buddy", "Roommate"):
        raise ValueError(f"Invalid role '{role}'.")

    # Build the SET clause dynamically – only non‑None values.
    set_parts = []
    params = []

    if name is not None:
        if not name.strip():
            return None
        set_parts.append("contact_name = ?")
        params.append(name.strip())
    if role is not None:
        set_parts.append("role = ?")
        params.append(role)
    if email is not None:
        set_parts.append("email = ?")
        params.append(email.strip() if email else None)
    if phone is not None:
        set_parts.append("phone = ?")
        params.append(phone.strip() if phone else None)

    if not set_parts:
        # Nothing to update; just return the existing contact.
        return get_contacts(user_id=user_id) and next(
            (c for c in get_contacts(user_id=user_id) if c.id == contact_id), None
        )

    set_sql = ", ".join(set_parts)
    params.append(datetime.now())  # for updated_at
    params.append(contact_id)

    # Ownership check in the same statement is not possible in SQLite, so we
    # verify via a SELECT before updating.
    conn = _get_conn()
    # Verify ownership
    cur_check = conn.execute(
        "SELECT id FROM trusted_contacts WHERE id = ? AND user_id = ?",
        (contact_id, user_id),
    )
    if cur_check.fetchone() is None:
        conn.close()
        return None

    cur = conn.execute(
        f"""
        UPDATE trusted_contacts
        SET {set_sql},
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        params,
    )
    conn.commit()

    # Return the refreshed contact
    cur2 = conn.execute(
        "SELECT id, user_id, contact_name, role, email, phone, active, created_at, updated_at "
        "FROM trusted_contacts WHERE id = ?",
        (contact_id,),
    )
    row = cur2.fetchone()
    conn.close()
    return _row_to_contact(row)


def set_active(contact_id, user_id, active=True):
    """Activate or deactivate a contact.

    Ownership is enforced.

    Parameters
    ----------
    contact_id : int
        ID of the contact to toggle.
    user_id : int
        ID of the owner (used for ownership check).
    active : bool
        True to activate, False to deactivate.

    Returns
    -------
    Contact | None
        The updated Contact instance, or None if the contact does not exist
        or the user does not own it.
    """
    conn = _get_conn()
    # Ownership check
    cur_check = conn.execute(
        "SELECT id FROM trusted_contacts WHERE id = ? AND user_id = ?",
        (contact_id, user_id),
    )
    if cur_check.fetchone() is None:
        conn.close()
        return None

    cur = conn.execute(
        "UPDATE trusted_contacts SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (1 if active else 0, contact_id),
    )
    conn.commit()

    cur2 = conn.execute(
        "SELECT id, user_id, contact_name, role, email, phone, active, created_at, updated_at "
        "FROM trusted_contacts WHERE id = ?",
        (contact_id,),
    )
    row = cur2.fetchone()
    conn.close()
    return _row_to_contact(row)