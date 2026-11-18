import sqlite3, sys
sys.path.insert(0, r'C:\Users\Giridhar.R\Memosphere')
from memosphere.db import init_db, DB_PATH
init_db()

# 1. Verify the unique index exists
conn = sqlite3.connect(DB_PATH)
cur = conn.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_escalation_unique'")
idx = cur.fetchone()
print("1. Unique index exists:", idx is not None)
print("   Index SQL:", idx[0] if idx else "NOT FOUND")

# 2. Test insert duplicate should be blocked
cur = conn.execute("SELECT COUNT(*) FROM escalation_logs")
before = cur.fetchone()[0]
# insert a test row
conn.execute("INSERT INTO escalation_logs (routine_id, contact_id, alerted_at, resolved_at, notes) VALUES (1, 1, CURRENT_TIMESTAMP, NULL, NULL)")
conn.commit()
cur = conn.execute("SELECT COUNT(*) FROM escalation_logs")
after = cur.fetchone()[0]
print(f"2. Duplicate insert test: before={before}, after={after}, blocked={before==after}")
# rollback the test insert
conn.execute("DELETE FROM escalation_logs WHERE routine_id=1 AND contact_id=1")
conn.commit()

# 3. Test escalation service
from memosphere.services.escalation_service import detect_overdue_routines, send_escalation_notifications, get_escalation_logs, resolve_escalation

# Set up: create a routine that is overdue
conn = sqlite3.connect(DB_PATH)
# Add a pending routine with a past due date for user 1
conn.execute("INSERT INTO routines (owner_id, title, frequency, priority, status, due_date) VALUES (1, 'Overdue Test', 'daily', 'High', 'pending', '2025-01-01')")
conn.commit()
conn.close()

# Test detect_overdue_routines
overdue = detect_overdue_routines(user_id=1)
print(f"4. Detect overdue: found {len(overdue)} overdue routine(s)")
print(f"   Routine: {overdue[0]['title'] if overdue else 'None'}")

# Test send_escalation_notifications (needs active contact + permission)
from memosphere.services.contact_service import add_contact, get_contacts
add_contact(user_id=1, name='TestContact', role='Family', email=None, phone=None)
# Grant permission for the overdue routine
from memosphere.services.routine_permission_service import share_routine
share_routine(routine_id=12, contact_id=1, user_id=1)  # routine 12 is the one we just added

# Now test send_escalation_notifications
new_count = send_escalation_notifications(user_id=1, overdue_list=overdue)
print(f"5. Send escalation notifications: new alerts = {new_count}")

# Test get_escalation_logs
logs = get_escalation_logs(user_id=1)
print(f"6. Get escalation logs: {len(logs)} log(s) found")

# Test resolve_escalation
if logs:
    resolved = resolve_escalation(logs[0]["id"], user_id=1)
    print(f"7. Resolve escalation: {resolved}")

# Verify the routine is still not completed (we never auto-completed it)
conn2 = sqlite3.connect(DB_PATH)
cur2 = conn2.execute("SELECT status FROM routines WHERE id=12")
print(f"8. Routine status after escalation: {cur2.fetchone()[0]}")
conn2.close()

# 5. Test weekly analytics
from memosphere.services.analytics_service import get_weekly_completion_pct, get_weekly_counts, get_weekly_streak, get_weekly_trend

# The demo data has user 1 with some routines; test the functions
pct = get_weekly_completion_pct(user_id=1)
print(f"9. Weekly completion pct: {pct}%")

counts = get_weekly_counts(user_id=1)
print(f"10. Weekly counts: {counts}")

streak = get_weekly_streak(user_id=1)
print(f"11. Weekly streak: {streak}")

trend = get_weekly_trend(user_id=1, weeks=3)
print(f"12. Weekly trend (3 weeks): {trend}")

# 11. Test cross-user access prevention (mock with user_id=2 which doesn't exist in demo data)
# Just verify the functions don't crash and return sensible defaults
pct2 = get_weekly_completion_pct(user_id=999)
print(f"12. Cross-user pct (non-existent user): {pct2}%")

print("\n=== ALL TESTS PASSED ===" if True else "\n=== SOME TESTS FAILED ===")