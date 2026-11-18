# memosphere/db/migration_routine_index.py
# Adds the idx_routines_due index on routines(status, due_date).
# Called from init_db() after the Stage‑4 migration; idempotent (IF NOT EXISTS).

import sqlite3

from memosphere.db import DB_PATH, init_db


def add_routine_index():
    """Create the index if it does not already exist.

    The index covers the two columns used to find overdue routines:
        status   – the three possible states (completed, pending, missed)
        due_date – the scheduled date for the routine
    """
    init_db()  # ensure schema + earlier migrations are up‑to‑date
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_routines_due "
            "ON routines (status, due_date)"
        )
        conn.commit()
    except sqlite3.OperationalError:
        # index may already exist or table may be absent – ignore
        pass
    finally:
        conn.close()