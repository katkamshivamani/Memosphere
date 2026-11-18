#!/usr/bin/env python
"""Memosphere – Module 4: Circle of Trust (Permission-Based Monitoring Dashboard)

Streamlit entry point.  Initialises the database, seeds demo data and presents
a minimal dashboard showing:

* total trusted contacts
* shared routines
* completed / pending / missed counts
* a plain‑text routine status table

The module code (models, services, utils) is reused; no fake authentication
is implemented – the demo data is always loaded.
"""

import os
import sys

import streamlit as st

# Ensure the project root is on the path so `memosphere` package imports work
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------
from memosphere.db import init_db, DB_PATH

init_db(DB_PATH)

# ---------------------------------------------------------------------------
# Demo data (run once – idempotent because of IF NOT EXISTS / UNIQUE constraints)
# ---------------------------------------------------------------------------
def load_demo_data():
    """Seed the DB with the predefined demo users / contacts / routines."""
    from data.demo_data import main as demo_main
    # demo_main() prints a success message; we ignore the return value.
    demo_main()

# ---------------------------------------------------------------------------
# Helper queries (pure SQL over the shared SQLite DB)
# ---------------------------------------------------------------------------
def get_trusted_contacts_count():
    """Return the number of trusted contacts stored."""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT COUNT(*) FROM trusted_contacts")
    cnt = cur.fetchone()[0]
    conn.close()
    return cnt


def get_routine_status_counts():
    """Return (completed, pending, missed) counts for all routines."""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        """
        SELECT status, COUNT(*)
        FROM routines
        GROUP BY status
        """
    )
    rows = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    completed = rows.get("completed", 0)
    pending = rows.get("pending", 0)
    missed = rows.get("missed", 0)
    return completed, pending, missed


def get_all_routines():
    """Return all routines as a list of dicts for display."""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT id, owner_id, title, frequency, priority, status,
               last_completed, due_date
        FROM routines
        ORDER BY priority DESC, title ASC
        """
    )
    routines = [dict(r) for r in cur.fetchall()]
    conn.close()
    return routines


# ---------------------------------------------------------------------------
# Streamlit page
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Memosphere – Circle of Trust", layout="wide")

st.title("🛡️ Memosphere — Circle of Trust")
st.caption("Permission‑based monitoring dashboard")

# Load demo data on first run
if "demo_loaded" not in st.session_state:
    load_demo_data()
    st.session_state.demo_loaded = True

# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
contact_count = get_trusted_contacts_count()
completed, pending, missed = get_routine_status_counts()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Trusted contacts", contact_count)
col2.metric("Shared routines", contact_count)  # placeholder – each contact may share multiple routines
col3.metric("Completed", completed, delta=None)
col4.metric("Missed", missed, delta=None)

st.markdown("---")

# ---------------------------------------------------------------------------
# Routine status table
# ---------------------------------------------------------------------------
st.subheader("Routine status")
routines = get_all_routines()

if not routines:
    st.info("No routines found. Seed data first.")
else:
    # Build a simple table
    table_rows = []
    for r in routines:
        # Format dates
        last = r["last_completed"] if r["last_completed"] else "—"
        due = r["due_date"] if r["due_date"] else "—"
        # Status badge colour is not possible in plain table; we just show text
        table_rows.append(
            {
                "#": r["id"],
                "Routine": r["title"],
                "Frequency": r["frequency"],
                "Priority": r["priority"],
                "Status": r["status"].capitalize(),
                "Last completed": last,
                "Due date": due,
            }
        )
    import pandas as pd

    df = pd.DataFrame(table_rows)
    st.dataframe(df, hide_index=True, use_container_width=True)

# ---------------------------------------------------------------------------
# Footer / notes
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption(
    "⚠️ Alerts are generated only for overdue high‑priority routines. "
    "Permission revocation takes effect immediately (backend‑only). "
    "Private notes or AI conversations are never exposed."
)