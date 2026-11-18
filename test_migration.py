import sys
sys.path.insert(0, r"C:\Users\Giridhar.R\Memosphere")
from memosphere.db import init_db
init_db()
print("DB initialized")
import sqlite3
conn = sqlite3.connect("memosphere.db")
cur = conn.execute("PRAGMA table_info(trusted_contacts)")
cols = [row[1] for row in cur.fetchall()]
print("Columns:", cols)
conn.close()