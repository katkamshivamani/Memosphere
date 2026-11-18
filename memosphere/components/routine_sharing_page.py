# memosphere/components/routine_sharing_page.py
# Streamlit page – Routine Sharing & Permissions (Stage 4)
# Shows a Share form above a table of current permissions.
# All operations go through the backend service.

import streamlit as st

from memosphere.services.routine_permission_service import (
    share_routine,
    get_shared_routines,
    get_routine_contacts,
    check_permission,
    revoke_permission,
    restore_permission,
)
from memosphere.services.contact_service import get_contacts as get_user_contacts
from memosphere.services.contact_service import (
    add_contact,
    edit_contact,
    set_active,
)
from memosphere.models.contact import Contact


def _current_user_id():
    """Return the mock user ID from session state, or None."""
    if "current_user" in st.session_state and st.session_state.current_user:
        return st.session_state.current_user.id
    return None


def _load_routines(user_id):
    """Return list of Routine objects owned by user_id."""
    from memosphere.services.routine_permission_service import _get_conn
    conn = _get_conn()
    cur = conn.execute(
        "SELECT id, owner_id, title, description, frequency, priority, status, last_completed, due_date FROM routines WHERE owner_id = ?",
        (user_id,),
    )
    routines = [_row_to_routine(r) for r in cur.fetchall()]
    conn.close()
    return routines


def _row_to_routine(row):
    """Minimal conversion – just enough for the UI."""
    routine_id, owner_id, title, description, frequency, priority, status, last_completed, due_date = row
    return {
        "id": routine_id,
        "title": title,
        "description": description,
        "frequency": frequency,
        "priority": priority,
        "status": status,
        "last_completed": last_completed,
        "due_date": due_date,
    }


def show_routine_sharing_page():
    """Render the full Routine Sharing & Permissions page."""
    user_id = _current_user_id()
    if user_id is None:
        st.error("User not logged in. Please start the app from the main dashboard.")
        return

    st.title("🛡️ Routine Sharing & Permissions")

    # -----------------------------------------------------------------
    # 1️⃣  SHARE A NEW ROUTINE form
    # -----------------------------------------------------------------
    st.subheader("Share a new routine")
    with st.form(key="share_routine_form", clear_on_submit=True):
        # contact selector – only active contacts
        contacts = get_user_contacts(user_id=user_id)
        active_contacts = [c for c in contacts if c.is_active]
        contact_options = {f"{c.name} (ID {c.id})": c.id for c in active_contacts}
        if not contact_options:
            st.info("No active trusted contacts yet. Add a contact first.")
            contact_selector = st.selectbox("Contact", options=[], disabled=True)
        else:
            contact_selector = st.selectbox("Trusted contact", options=list(contact_options.keys()))

        # routine selector – all routines owned by the user
        routines = _load_routines(user_id)
        routine_options = {r["title"]: r["id"] for r in routines}
        if not routine_options:
            st.info("No routines found. Create a routine first.")
            routine_selector = st.selectbox("Routine", options=[], disabled=True)
        else:
            routine_selector = st.selectbox("Routine to share", options=list(routine_options.keys()))

        submit_share = st.form_submit_button("Share routine")

    if submit_share:
        contact_id = contact_options.get(contact_selector)
        routine_id = routine_options.get(routine_selector)
        if contact_id is None or routine_id is None:
            st.error("Please select both a contact and a routine.")
        else:
            granted = share_routine(routine_id=routine_id, contact_id=contact_id, user_id=user_id)
            if granted:
                st.success(f"✅ Routine '{routines[[r['id'] for r in routines].index(routine_id)]['title']}' shared with {contact_selector}.")
            else:
                st.error("❌ Could not share – possible reasons: contact inactive, you don't own the routine, or duplicate active permission.")

    # -----------------------------------------------------------------
    # 2️⃣  Currently shared permissions table
    # -----------------------------------------------------------------
    st.markdown("---")
    st.subheader("Currently shared routines")

    # gather permissions for all active contacts
    contacts = get_user_contacts(user_id=user_id)
    # build a dict: contact_id -> list of routine titles
    shared_dict = {c.id: get_shared_routines(c.id) for c in contacts if c.is_active}

    if not any(shared_dict.values()):
        st.info("No routines are currently shared with any contact.")
    else:
        rows = []
        for c in contacts:
            if not c.is_active:
                continue
            cid = c.id
            routine_ids = shared_dict.get(cid, [])
            # fetch routine titles for display
            conn = _get_conn()  # reuse connection helper
            placeholders = ",".join("?" for _ in routine_ids)
            routine_titles = []
            if routine_ids:
                cur = conn.execute(
                    f"SELECT title FROM routines WHERE id IN ({placeholders})",
                    routine_ids,
                )
                routine_titles = [r[0] for r in cur.fetchall()]
            conn.close()
            for rid, title in zip(routine_ids, routine_titles):
                rows.append(
                    {
                        "Contact": c.name,
                        "Role": c.role,
                        "Routine": title,
                        "Status": "Active",
                        "Action": f"Revoke ({cid}, {rid})",
                    }
                )
        import pandas as pd
        df = pd.DataFrame(rows, columns=["Contact", "Role", "Routine", "Status", "Action"])
        st.dataframe(df, hide_index=True, use_container_width=True)

        # -----------------------------------------------------------------
        # Revoke / Restore actions (inline button simulation)
        # -----------------------------------------------------------------
        st.markdown("**Revoke / Restore**")
        with st.expander("Bulk actions (optional)"):
            for idx, row in df.iterrows():
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"{row['Contact']} – {row['Routine']}")
                with col2:
                    if st.button("Revoke", key=f"revoke_{idx}"):
                        # determine contact_id and routine_id from row context
                        # we need to lookup; simplify by asking user to input IDs
                        st.info("Use the individual Revoke button in the future.")
            # Note: full per‑row revocation can be added later.