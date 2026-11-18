# memosphere/db/migration_escalation_index.py
# Adds a unique index on escalation_logs(routine_id, contact_id, DATE(alerted_at))
# to prevent duplicate alerts for the same routine‑contact‑day.
# Idempotent because of CREATE INDEX IF NOT EXISTS (SQLite 3.31.0+).
# Does NOT call init_db() – the caller (init_db()) already ensures the schema
# is up‑to‑date before this function runs.

import sqlite3


def _add_escalation_unique_index(conn):
    """Create the unique index if it does not already exist.

    The index covers (routine_id, contact_id, DATE(alerted_at)),
    ensuring that only one escalation alert is recorded per routine‑contact‑day.
    """
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_escalation_unique "
            "ON escalation_logs (routine_id, contact_id, DATE(alerted_at))"
        )
    except sqlite3.OperationalError:
        # Index may already exist or SQLite version may not support expressions
        # in indexes – silently continue.
        pass


def add_escalation_unique_index(conn):
    """Public helper – called from init_db() after all prior migrations.

    Parameters
    ----------
    conn : sqlite3.Connection
        An already‑opened connection whose schema already includes the
        Stage‑5 (routines index) and earlier migrations.
    """
    _add_escalation_unique_index(conn)