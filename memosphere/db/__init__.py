import os

import sqlite3


DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "memosphere.db"
)


def init_db(db_path=None):
    """Initialise the SQLite database using the schema defined in schema.sql.

    The function is idempotent – it creates all tables (IF NOT EXISTS) and
    does nothing if the tables already exist.
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
    conn.close()