import sqlite3, sys
sys.path.insert(0, r'C:\Users\Giridhar.R\Memosphere')
from memosphere.db import init_db, DB_PATH
init_db()

conn = sqlite3.connect(DB_PATH)
# insert a few routines for testing
conn.execute(
    "INSERT INTO routines (owner_id, title, frequency, priority, status, due_date) VALUES (1, 'Morning Meditation', 'daily', 'High', 'pending', '2025-02-01')"
)
conn.execute(
    "INSERT INTO routines (owner_id, title, frequency, priority, status, due_date) VALUES (1, 'Exercise Walk', 'daily', 'Medium', 'pending', '2025-03-01')"
)
conn.execute(
    "INSERT INTO routines (owner_id, title, frequency, priority, status, due_date) VALUES (1, 'Night Journaling', 'daily', 'Low', 'pending', '2025-01-15')"
)
conn.commit()

# verify
cur = conn.execute("SELECT id, title, status, due_date FROM routines")
print("Routines:", cur.fetchall())
conn.close()

# now test mark_routine_completed
from memosphere.services.routine_status_service import mark_routine_completed, update_missing_routines, get_routines_by_status

# 1. Mark first routine completed
result = mark_routine_completed(1, 1)
print("mark_routine_completed(1,1):", result)

# check status
conn2 = sqlite3.connect(DB_PATH)
cur2 = conn2.execute("SELECT status, last_completed FROM routines WHERE id=1")
print("after mark:", cur2.fetchone())
conn2.close()

# 2. Update missing routines
changed = update_missing_routines(1)
print("update_missing_routines changed:", changed)

# check statuses
conn3 = sqlite3.connect(DB_PATH)
cur3 = conn3.execute("SELECT id, title, status, due_date FROM routines")
print("after update_missing:", cur3.fetchall())
conn3.close()

# 3. Get routines by status
from memosphere.services.routine_status_service import get_routines_by_status
completed = get_routines_by_status(1, "completed")
pending = get_routines_by_status(1, "pending")
missed = get_routines_by_status(1, "missed")
print("completed:", completed)
print("pending:", pending)
print("missed:", missed)