# data/demo_data.py
# Seed script – populate a fresh SQLite DB with demo data for Circle of Trust.
# Run once: python -m data.demo_data  (or from project root: python data/demo_data.py)

import sys
import os
sys.path.insert(0, os.path.dirname(__file__) + os.sep + "..")

import sqlite3
from datetime import date, timedelta

from memosphere.db import init_db  # DB_PATH is defined locally later
from memosphere.models.user import User
from memosphere.models.routine import Routine


DB_PATH = os.path.join(os.path.dirname(__file__), "..", "memosphere.db")
# Ensure a clean slate for demo purposes
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)


def main():
    init_db()

    conn = sqlite3.connect(DB_PATH)

    # ---- Demo users (owner) ----
    users = [
        User(user_id=1, name="Alex", role="Family"),
        User(user_id=2, name="Sam", role="Caregiver"),
        User(user_id=3, name="Jordan", role="Study Buddy"),
        User(user_id=4, name="Casey", role="Roommate"),
    ]
    for u in users:
        conn.execute(
            "INSERT INTO users (id, name, role) VALUES (?, ?, ?)",
            (u.id, u.name, u.role),
        )

    # ---- Trusted contacts ----
    contacts = [
        # Alex's contacts
        (1, "Mom", "Family", "share"),
        (1, "Dad", "Family", "view"),
        # Sam's contacts
        (2, "Nurse Rita", "Caregiver", "admin"),
        (2, "Brother Ben", "Caregiver", "view"),
        # Jordan's contacts
        (3, "Study Partner Lee", "Study Buddy", "share"),
        # Casey's contacts
        (4, "Roommate Sam", "Roommate", "view"),
    ]
    for user_id, name, role, perm in contacts:
        conn.execute(
            "INSERT INTO trusted_contacts (user_id, contact_name, role, permission_level) VALUES (?, ?, ?, ?)",
            (user_id, name, role, perm),
        )

    # ---- Demo routines ----
    # Vary priorities, frequencies, and due dates so some are overdue high‑priority.
    routines = [
        # Alex's routines
        {
            "owner_id": 1,
            "title": "Morning Meditation",
            "frequency": "daily",
            "priority": "High",
            "status": "completed",
            "last_completed": date.today() - timedelta(days=1),
            "due_date": date.today() + timedelta(days=1),
        },
        {
            "owner_id": 1,
            "title": "Hydration Reminder",
            "frequency": "daily",
            "priority": "Medium",
            "status": "pending",
            "last_completed": None,
            "due_date": date.today() + timedelta(days=1),
        },
        {
            "owner_id": 1,
            "title": "Night Journaling",
            "frequency": "daily",
            "priority": "Low",
            "status": "missed",
            "last_completed": None,
            "due_date": date.today() - timedelta(days=3),
        },
        # Sam's routines
        {
            "owner_id": 2,
            "title": "Medication Check",
            "frequency": "daily",
            "priority": "High",
            "status": "missed",
            "last_completed": None,
            "due_date": date.today() - timedelta(days=2),  # overdue high‑priority
        },
        {
            "owner_id": 2,
            "title": "Exercise Walk",
            "frequency": "daily",
            "priority": "Medium",
            "status": "completed",
            "last_completed": date.today() - timedelta(days=1),
            "due_date": date.today() + timedelta(days=2),
        },
        # Jordan's routines
        {
            "owner_id": 3,
            "title": "Weekly Review",
            "frequency": "weekly",
            "priority": "High",
            "status": "pending",
            "last_completed": date.today() - timedelta(weeks=1),
            "due_date": date.today() + timedelta(days=3),
        },
        # Casey's routines
        {
            "owner_id": 4,
            "title": "Trash Night",
            "frequency": "weekly",
            "priority": "Low",
            "status": "pending",
            "last_completed": None,
            "due_date": date.today() + timedelta(days=5),
        },
    ]

    for r in routines:
        conn.execute(
            """
            INSERT INTO routines
            (owner_id, title, description, frequency, priority, status, last_completed, due_date)
            VALUES
            (:owner_id, :title, :description, :frequency, :priority, :status, :last_completed, :due_date)
            """,
            {
                "owner_id": r["owner_id"],
                "title": r["title"],
                "description": r.get("description"),
                "frequency": r["frequency"],
                "priority": r["priority"],
                "status": r["status"],
                "last_completed": r["last_completed"],
                "due_date": r["due_date"],
            },
        )

    # ---- Grant some permissions (example) ----
    # Alex shares Medium priority routine with Dad (view) and Mom (share)
    conn.execute(
        "INSERT INTO permissions (routine_id, contact_id, permission_level) VALUES (?, ?, ?)",
        (1, 2, "view"),  # Dad can view routine id 1
    )
    conn.execute(
        "INSERT INTO permissions (routine_id, contact_id, permission_level) VALUES (?, ?, ?)",
        (1, 3, "share"),  # Mom can share routine id 1
    )
    # Sam's overdue high‑priority routine is visible to Nurse Rita (admin) only
    conn.execute(
        "INSERT INTO permissions (routine_id, contact_id, permission_level) VALUES (?, ?, ?)",
        (5, 2, "admin"),  # Nurse Rita can admin routine id 5 (Medication Check)
    )

    conn.commit()
    conn.close()
    print("✅ Demo data seeded successfully.")
    print(f"DB located at: {os.path.abspath(DB_PATH)}")


if __name__ == "__main__":
    main()