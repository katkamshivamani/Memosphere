# data/demo_data.py
# Seed script – populate a fresh SQLite DB with demo data for Circle of Trust.
# Run once: python -m data.demo_data  (or from project root: python data/demo_data.py)

import sys
import os
sys.path.insert(0, os.path.dirname(__file__) + os.sep + "..")

import sqlite3
from datetime import date, timedelta

from memosphere.db import init_db

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "memosphere", "memosphere.db")

# ---------------------------------------------------------------------------
# Initialise the database (creates all tables & runs migrations)
# ---------------------------------------------------------------------------
init_db()


def main():
    conn = sqlite3.connect(DB_PATH)

    # -----------------------------------------------------------------
    # 1️⃣  Demo users  (owner records) – insert only if they do not exist
    # -----------------------------------------------------------------
    users = [
        {"id": 1, "name": "Alex", "role": "Family"},
        {"id": 2, "name": "Sam",   "role": "Caregiver"},
        {"id": 3, "name": "Jordan","role": "Study Buddy"},
        {"id": 4, "name": "Casey", "role": "Roommate"},
    ]
    for u in users:
        cur = conn.execute(
            "SELECT COUNT(*) FROM users WHERE id = ?",
            (u["id"],),
        )
        if cur.fetchone()[0] == 0:               # only insert if absent
            conn.execute(
                "INSERT INTO users (id, name, role) VALUES (?, ?, ?)",
                (u["id"], u["name"], u["role"]),
            )

    # -----------------------------------------------------------------
    # 2️⃣  Trusted contacts – insert only if (user_id, contact_name) does not exist
    # -----------------------------------------------------------------
    contacts = [
        # Alex's contacts
        (1, "Mom", "Family", "share"),
        (1, "Dad",   "Family", "view"),
        # Sam's contacts
        (2, "Nurse Rita", "Caregiver", "admin"),
        (2, "Brother Ben", "Caregiver", "view"),
        # Jordan's contacts
        (3, "Study Partner Lee", "Study Buddy", "share"),
        # Casey's contacts
        (4, "Roommate Sam", "Roommate", "view"),
    ]
    for user_id, name, role, perm in contacts:
        cur = conn.execute(
            "SELECT COUNT(*) FROM trusted_contacts "
            "WHERE user_id = ? AND contact_name = ?",
            (user_id, name),
        )
        if cur.fetchone()[0] == 0:               # only insert if absent
            conn.execute(
                "INSERT INTO trusted_contacts (user_id, contact_name, role, permission_level) "
                "VALUES (?, ?, ?, ?)",
                (user_id, name, role, perm),
            )

    # -----------------------------------------------------------------
    # 3️⃣  Routines – insert only if (owner_id, title) does not already exist
    # -----------------------------------------------------------------
    routines = [
        # (owner_id, title, frequency, priority, status, due_date)
        (1, "Morning Meditation", "daily", "High", "completed", "2025-02-01"),
        (1, "Hydration Reminder", "daily", "Medium", "pending", "2025-02-02"),
        (1, "Night Journaling", "daily", "Low", "missed", "2025-01-15"),
        # Sam's routines
        (2, "Medication Check", "daily", "High", "missed", "2025-01-30"),
        (2, "Exercise Walk", "daily", "Medium", "completed", "2025-02-01"),
        # Jordan's routines
        (3, "Weekly Review", "weekly", "High", "pending", "2025-02-05"),
        # Casey's routines
        (4, "Trash Night", "weekly", "Low", "pending", "2025-02-10"),
    ]
    for owner_id, title, freq, prio, status, due in routines:
        cur = conn.execute(
            "SELECT COUNT(*) FROM routines "
            "WHERE owner_id = ? AND title = ?",
            (owner_id, title),
        )
        if cur.fetchone()[0] == 0:               # only insert if absent
            conn.execute(
                """
                INSERT INTO routines
                (owner_id, title, description, frequency, priority, status, last_completed, due_date)
                VALUES
                (?, ?, NULL, ?, ?, ?, NULL, ?)
                """,
                (owner_id, title, freq, prio, status, due),
            )

    # -----------------------------------------------------------------
    # 4️⃣  Permissions – use INSERT OR IGNORE (UNIQUE on routine_id,contact_id)
    # -----------------------------------------------------------------
    perm_examples = [
        (1, 1, "view"),   # Mom views routine 1
        (1, 2, "share"),  # Mom shares routine 1
        (2, 2, "admin"),  # Nurse Rita admin of routine 2
    ]
    for routine_id, contact_id, level in perm_examples:
        conn.execute(
            "INSERT OR IGNORE INTO permissions (routine_id, contact_id, permission_level) "
            "VALUES (?, ?, ?)",
            (routine_id, contact_id, level),
        )

    conn.commit()
    conn.close()
    print("✅ Demo data seeded successfully.")
    print(f"DB located at: {os.path.abspath(DB_PATH)}")


if __name__ == "__main__":
    main()