import os
import sqlite3


DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "memosphere.db"
)


# ----------------------------------------------------------------------
# Migration 1 – Trusted contacts (already added in Stage 3)
# ----------------------------------------------------------------------
def _add_missing_columns(conn):
    """Add missing columns to the trusted_contacts table.

    The function checks the current column list with PRAGMA table_info and
    adds any that are absent.  All changes are purely additive – no data is
    dropped or rewritten.
    """
    cur = conn.execute("PRAGMA table_info(trusted_contacts)")
    existing = {row[1] for row in cur.fetchall()}   # column names

    additions = []
    if "email" not in existing:
        additions.append("email TEXT")
    if "phone" not in existing:
        additions.append("phone TEXT")
    if "active" not in existing:
        additions.append("active INTEGER DEFAULT 1")
    if "updated_at" not in existing:
        additions.append("updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    for sql in additions:
        try:
            conn.execute(f"ALTER TABLE trusted_contacts ADD COLUMN {sql}")
        except sqlite3.OperationalError:
            pass

    if additions:
        conn.commit()


# ----------------------------------------------------------------------
# Migration 2 – Permissions table (Stage 4)
#    Adds owner_user_id, status, updated_at and a partial unique index.
#    Designed to be run repeatedly; each statement is safe if the object
#    already exists.
# ----------------------------------------------------------------------
def _upgrade_permissions_schema(conn):
    """Add columns and index to the permissions table.

    The migration is idempotent – if a column or index already exists the
    statement is simply ignored.
    """
    # 1️⃣  owner_user_id  – who owned the routine when the permission was granted
    try:
        conn.execute(
            "ALTER TABLE permissions ADD COLUMN owner_user_id INTEGER NOT NULL DEFAULT 1"
        )
    except sqlite3.OperationalError:
        pass

    # 2️⃣  status – 'active' or 'revoked'
    try:
        conn.execute(
            "ALTER TABLE permissions "
            "ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
            " CHECK(status IN ('active','revoked'))"
        )
    except sqlite3.OperationalError:
        pass

    # 3️⃣  updated_at – timestamp of last change
    try:
        conn.execute(
            "ALTER TABLE permissions ADD COLUMN updated_at "
            "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
        )
    except sqlite3.OperationalError:
        pass

    # 4️⃣  Populate owner_user_id from trusted_contacts (the contact's owner)
    try:
        conn.execute(
            """
            UPDATE permissions
            SET owner_user_id = (
                SELECT user_id FROM trusted_contacts WHERE id = permissions.contact_id
            )
            """
        )
    except sqlite3.OperationalError:
        # Table may be empty or schema already migrated; ignore.
        pass

    # 5️⃣  Ensure every row has status = 'active' (old rows have no status column)
    try:
        conn.execute(
            "UPDATE permissions SET status = 'active' WHERE status IS NULL"
        )
    except sqlite3.OperationalError:
        pass

    # 6️⃣  Create partial unique index – prevents two active permissions for the same
    #    (owner_user_id, contact_id, routine_id) combination, but revoked rows can coexist.
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_permission "
            "ON permissions (owner_user_id, contact_id, routine_id) "
            "WHERE status = 'active'"
        )
    except sqlite3.OperationalError:
        pass

    conn.commit()


# ----------------------------------------------------------------------
# Migration 3 – Routine due‑date index (Stage 5)
#    Adds a non‑unique index on (status, due_date) to speed up overdue queries.
#    Idempotent because of CREATE INDEX IF NOT EXISTS.
# ----------------------------------------------------------------------
def _add_routine_due_index(conn):
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_routines_due "
            "ON routines (status, due_date)"
        )
    except sqlite3.OperationalError:
        pass


# ----------------------------------------------------------------------
# Migration 1 – Trusted contacts (already added in Stage 3)
# ----------------------------------------------------------------------
def _add_missing_columns(conn):
    """Add missing columns to the trusted_contacts table.

    The function checks the current column list with PRAGMA table_info and
    adds any that are absent.  All changes are purely additive – no data is
    dropped or rewritten.
    """
    cur = conn.execute("PRAGMA table_info(trusted_contacts)")
    existing = {row[1] for row in cur.fetchall()}   # column names

    additions = []
    if "email" not in existing:
        additions.append("email TEXT")
    if "phone" not in existing:
        additions.append("phone TEXT")
    if "active" not in existing:
        additions.append("active INTEGER DEFAULT 1")
    if "updated_at" not in existing:
        additions.append("updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    for sql in additions:
        try:
            conn.execute(f"ALTER TABLE trusted_contacts ADD COLUMN {sql}")
        except sqlite3.OperationalError:
            pass

    if additions:
        conn.commit()


# ----------------------------------------------------------------------
# Migration 2 – Permissions table (Stage 4)
#    Adds owner_user_id, status, updated_at and a partial unique index.
#    Designed to be run repeatedly; each statement is safe if the object
#    already exists.
# ----------------------------------------------------------------------
def _upgrade_permissions_schema(conn):
    """Add columns and index to the permissions table.

    The migration is idempotent – if a column or index already exists the
    statement is simply ignored.
    """
    # 1️⃣  owner_user_id  – who owned the routine when the permission was granted
    try:
        conn.execute(
            "ALTER TABLE permissions ADD COLUMN owner_user_id INTEGER NOT NULL DEFAULT 1"
        )
    except sqlite3.OperationalError:
        pass

    # 2️⃣  status – 'active' or 'revoked'
    try:
        conn.execute(
            "ALTER TABLE permissions "
            "ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
            " CHECK(status IN ('active','revoked'))"
        )
    except sqlite3.OperationalError:
        pass

    # 3️⃣  updated_at – timestamp of last change
    try:
        conn.execute(
            "ALTER TABLE permissions ADD COLUMN updated_at "
            "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
        )
    except sqlite3.OperationalError:
        pass

    # 4️⃣  Populate owner_user_id from trusted_contacts (the contact's owner)
    try:
        conn.execute(
            """
            UPDATE permissions
            SET owner_user_id = (
                SELECT user_id FROM trusted_contacts WHERE id = permissions.contact_id
            )
            """
        )
    except sqlite3.OperationalError:
        # Table may be empty or schema already migrated; ignore.
        pass

    # 5️⃣  Ensure every row has status = 'active' (old rows have no status column)
    try:
        conn.execute(
            "UPDATE permissions SET status = 'active' WHERE status IS NULL"
        )
    except sqlite3.OperationalError:
        pass

    # 6️⃣  Create partial unique index – prevents two active permissions for the same
    #    (owner_user_id, contact_id, routine_id) combination, but revoked rows can coexist.
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_permission "
            "ON permissions (owner_user_id, contact_id, routine_id) "
            "WHERE status = 'active'"
        )
    except sqlite3.OperationalError:
        pass

    conn.commit()


# ----------------------------------------------------------------------
# Migration 3 – Routine due‑date index (Stage 5)
#    Adds a non‑unique index on (status, due_date) to speed up overdue queries.
#    Idempotent because of CREATE INDEX IF NOT EXISTS.
# ----------------------------------------------------------------------
def _add_routine_due_index(conn):
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_routines_due "
            "ON routines (status, due_date)"
        )
    except sqlite3.OperationalError:
        pass


def init_db(db_path=None):
    """Initialise the SQLite database using the schema defined in schema.sql.

    The function is idempotent – it creates all tables (IF NOT EXISTS) and
    then runs three backward‑compatible migrations:
      1️⃣  Add columns required by the Trusted‑Contact Management feature
          (email, phone, active, updated_at) – Stage 3.
      2️⃣  Upgrade the permissions table (owner_user_id, status, updated_at,
          partial unique index) – Stage 4.
      3️⃣  Add a non‑unique index on (status, due_date) for overdue queries – Stage 5.
    Existing rows are preserved; new columns receive their defaults.
    """
    if db_path is None:
        db_path = DB_PATH

    # Ensure the parent directory exists (e.g. when called from a test temp dir)
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(db_path)

    # Read the schema from the sibling schema.sql file
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn.executescript(schema_sql)
    conn.commit()

    # ----- Stage 3 migration -------------------------------
    _add_missing_columns(conn)

    # ----- Stage 4 migration -------------------------------
    _upgrade_permissions_schema(conn)

    # ----- Stage 5 migration -------------------------------
    _add_routine_due_index(conn)

    # ----- Stage 6 migration -------------------------------
    # Adds a unique index on escalation_logs(routine_id, contact_id, DATE(alerted_at))
    # to prevent duplicate alerts for the same routine‑contact‑day.
    # The function is imported from the dedicated migration module so that the
    # logic stays separate and testable.
    from memosphere.db.migration_escalation_index import add_escalation_unique_index
    add_escalation_unique_index(conn)

    conn.close()