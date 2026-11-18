# memosphere/components/routine_dashboard.py
# Streamlit page – Routine Status Dashboard (Stage 5)
# Shows summary cards, a filterable table, and owner vs contact views.
# All backend queries go through routine_status_service; sharing permissions
# are checked for the contact mode.

import streamlit as st
from datetime import date, timedelta

from memosphere.services.routine_status_service import (
    mark_routine_completed,
    update_missing_routines,
    get_routines_by_status,
)
from memosphere.services.contact_service import get_contacts, set_active
from memosphere.services.routine_permission_service import (
    get_shared_routines,
    check_permission,
)
from memosphere.models.contact import Contact


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _current_user_id():
    """Return the mock user ID from session state, or None."""
    if "current_user" in st.session_state and st.session_state.current_user:
        return st.session_state.current_user.id
    return None


def _routines_owner(user_id, date_from=None, date_to=None):
    """Fetch routines owned by *user_id* optionally filtered by date range."""
    from memosphere.services.routine_status_service import _get_conn
    conn = _get_conn()
    cur = conn.execute(
        "SELECT id, owner_id, title, frequency, priority, status, last_completed, due_date "
        "FROM routines WHERE owner_id = ?",
        (user_id,),
    )
    routines = [_row_to_routine(r) for r in cur.fetchall()]
    conn.close()

    # apply date filter
    if date_from or date_to:
        filtered = []
        for r in routines:
            d = r["due_date"]
            if d:
                if date_from and d < date_from:
                    continue
                if date_to and d > date_to:
                    continue
                filtered.append(r)
            else:
                filtered.append(r)
        return filtered
    return routines


def _routine_to_table_row(r, can_edit):
    """Convert a routine dict to a table‑row dict."""
    return {
        "#": r["id"],
        "Routine": r["title"],
        "Frequency": r["frequency"],
        "Priority": r["priority"],
        "Due date": r["due_date"] if r["due_date"] else "—",
        "Status": r["status"].capitalize(),
        "Last completed": r["last_completed"] if r["last_completed"] else "—",
        "Edit/Complete": can_edit and "Mark complete" or "",
    }


def _contact_has_permission(contact_id, routine_id, owner_user_id):
    """Quick check: does the contact have an active permission on this routine?"""
    # Re‑use the permission service; it already checks active status and ownership.
    return check_permission(contact_id, routine_id, owner_user_id)


# ----------------------------------------------------------------------
# UI page
# ----------------------------------------------------------------------
def show_routine_dashboard():
    """Render the Routine Status Dashboard page."""
    user_id = _current_user_id()
    if user_id is None:
        st.error("User not logged in. Please start the app from the main dashboard.")
        return

    st.title("📅 Routine Status Dashboard")

    # -----------------------------------------------------------------
    # 1️⃣  Sidebar: view mode + date filter
    # -----------------------------------------------------------------
    st.sidebar.header("View options")
    view_mode = st.sidebar.radio(
        "Select view",
        ["Owner", "Authorized contact"],
        index=0,
        help="Owner can mark routines completed; contact has read‑only access.",
    )

    # date filter
    default_from = date.today() - timedelta(days=28)
    default_to = date.today()
    date_from = st.sidebar.date_input("From", value=default_from)
    date_to = st.sidebar.date_input("To", value=default_to)

    # -----------------------------------------------------------------
    # 2️⃣  Load routines based on mode
    # -----------------------------------------------------------------
    if view_mode == "Owner":
        routines = _routines_owner(user_id, date_from, date_to)
        can_edit = True
        # compute summary counts from all routines (ignoring date filter for simplicity)
        from memosphere.services.routine_status_service import (
            get_routines_by_status as _get,
        )
        completed_cnt = len(_get(user_id, "completed"))
        pending_cnt = len(_get(user_id, "pending"))
        missed_cnt = len(_get(user_id, "missed"))
    else:  # Authorized contact
        # get active contacts for this user
        contacts = get_contacts(user_id=user_id)
        active_contacts = [c for c in contacts if c.is_active]
        if not active_contacts:
            st.info("No active trusted contacts. Add a contact first.")
            routines = []
            completed_cnt = pending_cnt = missed_cnt = 0
            can_edit = False
        else:
            # use the first active contact for demo purposes
            contact = active_contacts[0]
            contact_id = contact.id
            # fetch routines this contact is permitted to see
            shared_ids = get_shared_routines(contact_id)  # returns list of routine IDs
            # fetch all routines owned by the user
            all_routines = _routines_owner(user_id, date_from, date_to)
            # keep only those with active permission
            routines = [r for r in all_routines if r["id"] in shared_ids]
            completed_cnt = pending_cnt = missed_cnt = 0  # we won't count here; just show table
            can_edit = False

    # -----------------------------------------------------------------
    # 3️⃣  Summary cards (owner mode only)
    # -----------------------------------------------------------------
    if view_mode == "Owner":
        col1, col2, col3 = st.columns(3)
        col1.metric("Completed", completed_cnt, delta=None)
        col2.metric("Pending", pending_cnt, delta=None)
        col3.metric("Missed", missed_cnt, delta=None)

    # -----------------------------------------------------------------
    # 4️⃣  Routine table
    # -----------------------------------------------------------------
    st.subheader("Routines")
    if not routines:
        st.info("No routines match the selected filter.")
    else:
        rows = []
        for r in routines:
            can_edit = view_mode == "Owner"
            row = _routine_to_table_row(r, can_edit)
            rows.append(row)
        import pandas as pd
        df = pd.DataFrame(rows, columns=["#", "Routine", "Frequency", "Priority", "Due date", "Status", "Last completed", "Edit/Complete"])
        st.dataframe(df, hide_index=True, use_container_width=True)

        # -----------------------------------------------------------------
        # 5️⃣  Owner: mark complete functionality
        # -----------------------------------------------------------------
        if view_mode == "Owner" and can_edit:
            st.markdown("**Mark as complete**")
            # select a routine to mark
            routine_options = {r["title"]: r["id"] for r in routines}
            if routine_options:
                selected_title = st.selectbox("Select routine to mark complete", options=list(routine_options.keys()))
                if st.button("Mark as complete"):
                    r_id = routine_options[selected_title]
                    ok = mark_routine_completed(r_id, user_id)
                    if ok:
                        st.success(f"✅ Routine '{selected_title}' marked as completed.")
                        st.experimental_rerun()
                    else:
                        st.error("❌ Could not mark complete (routine may already be completed or you don't own it).")
            else:
                st.info("No routines to mark.")

    # -----------------------------------------------------------------
    # 6️⃣  Contact view: read‑only note
    # -----------------------------------------------------------------
    if view_mode == "Authorized contact" and not can_edit:
        st.info(
            "You have read‑only access. Only routines for which you have an active "
            "sharing permission are shown above. Revoking a permission immediately "
            "removes the routine from this list."
        )

# ----------------------------------------------------------------------
# End of file
# ----------------------------------------------------------------------