# memosphere/components/contact_manager.py
# Streamlit UI widgets for trusted‑contact management.
# All operations enforce ownership via the current user object.

import streamlit as st

from memosphere.services.contact_service import (
    add_contact,
    get_contacts,
    edit_contact,
    set_active,
)
from memosphere.models.contact import Contact


# ----------------------------------------------------------------------
# Helper: ensure a "current user" exists for the demo.
# In a real app this would come from an auth system.
# ----------------------------------------------------------------------
def _current_user_id():
    """Return the mock user ID, or None if not initialised."""
    if "current_user" in st.session_state and st.session_state.current_user:
        return st.session_state.current_user.id
    return None


# ----------------------------------------------------------------------
# UI: Add Contact form
# ----------------------------------------------------------------------
def show_add_contact_form():
    """Render a form to add a new trusted contact."""
    st.subheader("➕ Add Trusted Contact")
    with st.form(key="add_contact_form", clear_on_submit=True):
        name = st.text_input("Contact name *", placeholder="e.g. Mom")
        role = st.selectbox(
            "Role *",
            options=["Family", "Caregiver", "Study Buddy", "Roommate"],
        )
        email = st.text_input("Email (optional)", placeholder="example@example.com")
        phone = st.text_input("Phone (optional)", placeholder="+1‑555‑123‑4567")
        submit = st.form_submit_button("Add contact")

    if submit:
        user_id = _current_user_id()
        if user_id is None:
            st.error("User not logged in. Please start the app from the main dashboard.")
            return

        new_contact = add_contact(user_id=user_id, name=name, role=role, email=email or None, phone=phone or None)
        if new_contact is None:
            st.error("❌ Failed to add contact – please check the input (name required, valid role).")
        else:
            st.success(f"✅ Contact **{new_contact.name}** added successfully (role: {new_contact.role}).")
            # Rerun to refresh the list
        st.rerun()


# ----------------------------------------------------------------------
# UI: Display contacts table
# ----------------------------------------------------------------------
def _contact_rows(contacts):
    """Return a list of dicts ready for a Streamlit data editor or table."""
    rows = []
    for c in contacts:
        rows.append(
            {
                "ID": c.id,
                "Name": c.name,
                "Role": c.role,
                "Email": c.email or "",
                "Phone": c.phone or "",
                "Active": "✅" if c.is_active else "❌",
                "Created": c.created_at.split(" ")[0] if c.created_at else "",
            }
        )
    return rows


def show_contacts_list():
    """Render a table of the current user’s trusted contacts with edit / toggle actions."""
    user_id = _current_user_id()
    if user_id is None:
        st.error("User not logged in.")
        return

    contacts = get_contacts(user_id=user_id)

    if not contacts:
        st.info("No trusted contacts yet. Use the **Add Contact** form above.")
        return

    st.subheader("👥 My trusted contacts")
    # Simple editable table using st.data_editor
    df = st.data_editor(
        _contact_rows(contacts),
        column_config={
            "ID": st.column_config.NumberColumn("ID", disabled=True),
            "Name": st.column_config.TextColumn("Name", required=True),
            "Role": st.column_config.SelectboxColumn(
                "Role",
                options=["Family", "Caregiver", "Study Buddy", "Roommate"],
                required=True,
            ),
            "Email": st.column_config.TextColumn("Email"),
            "Phone": st.column_config.TextColumn("Phone"),
            "Active": st.column_config.CheckboxColumn("Active", default=False),
            "Created": st.column_config.TextColumn("Created", disabled=True),
        },
        hide_index=True,
        use_container_width=True,
    )

    # -----------------------------------------------------------------
    # Apply changes (save button)
    # -----------------------------------------------------------------
    if st.button("💾 Save changes", type="primary"):
        # Map rows back to Contact objects and persist
        for idx, row in df.iterrows():
            c_id = int(row["ID"])
            new_name = row["Name"] or None
            new_role = row["Role"]
            new_email = row["Email"] or None
            new_phone = row["Phone"] or None
            new_active = bool(row["Active"])

            # Find the original contact to compare
            original = next((c for c in contacts if c.id == c_id), None)
            if original is None:
                continue

            # If nothing changed, skip
            if (
                (new_name or "") == (original.name or "")
                and new_role == original.role
                and (new_email or "") == (original.email or "")
                and (new_phone or "") == (original.phone or "")
                and new_active == original.is_active
            ):
                continue

            updated = edit_contact(
                contact_id=c_id,
                user_id=user_id,
                name=new_name,
                role=new_role,
                email=new_email,
                phone=new_phone,
            )
            if updated is None:
                st.error(f"❌ Could not update contact ID {c_id} (ownership issue).")
            else:
                # Also update the in‑memory list for immediate feedback
                # (not strictly necessary since we’ll rerun)
                pass

        st.success("✅ All changes saved.")
        st.rerun()


# ----------------------------------------------------------------------
# UI: Activate / Deactivate toggle (separate section)
# ----------------------------------------------------------------------
def show_activate_toggle():
    """Allow the user to toggle a contact’s active status."""
    user_id = _current_user_id()
    if user_id is None:
        st.error("User not logged in.")
        return

    contacts = get_contacts(user_id=user_id)
    if not contacts:
        st.info("No contacts to toggle.")
        return

    st.subheader("🔘 Activate / Deactivate contact")
    # Build a simple selectbox
    options = {f"{c.name} (ID {c.id})": c.id for c in contacts}
    selected_label = st.selectbox("Select contact", options=options.keys())
    selected_id = options[selected_label]

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Activate"):
            updated = set_active(contact_id=selected_id, user_id=user_id, active=True)
            if updated is None:
                st.error("❌ Failed to activate (ownership issue).")
            else:
                st.success(f"✅ {updated.name} is now **active**.")
                st.rerun()
    with col2:
        if st.button("Deactivate"):
            updated = set_active(contact_id=selected_id, user_id=user_id, active=False)
            if updated is None:
                st.error("❌ Failed to deactivate (ownership issue).")
            else:
                st.success(f"✅ {updated.name} is now **inactive**.")
                st.rerun()