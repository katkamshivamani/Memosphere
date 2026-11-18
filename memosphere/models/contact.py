# memosphere/models/contact.py
# Data model for a trusted contact.

from datetime import datetime


class Contact:
    """Represents a single trusted contact row from the database."""

    def __init__(
        self,
        contact_id,
        owner_user_id,
        contact_name,
        email=None,
        phone=None,
        role="Family",
        active=True,
        created_at=None,
        updated_at=None,
    ):
        self.id = contact_id
        self.owner_user_id = owner_user_id
        self.name = contact_name
        self.email = email
        self.phone = phone
        self.role = role
        self.active = active
        self.created_at = created_at if created_at else datetime.now()
        self.updated_at = updated_at if updated_at else datetime.now()

    # -----------------------------------------------------------------
    # Human‑readable helpers
    # -----------------------------------------------------------------
    @property
    def is_active(self):
        return bool(self.active)

    def deactivate(self):
        self.active = False
        self.updated_at = datetime.now()

    def reactivate(self):
        self.active = True
        self.updated_at = datetime.now()

    def __repr__(self):
        return f"<Contact {self.name} (role={self.role}, active={self.active})>"