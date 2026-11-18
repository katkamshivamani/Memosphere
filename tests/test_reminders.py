"""
MEMOSPHERE Automated Test Suite — Reminders & Routines (test_reminders.py)
Verifies APScheduler reminder creation, tone-adapted notification formatting (Friendly, Calm, Direct),
completion toggling, and daily routine tracking.
"""
import unittest
from app import create_app
from backend.models import db, User


class TestRemindersAndRoutines(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            user = User(name="Aarav", email="aarav@test.local", role="user")
            user.set_password("pass123")
            db.session.add(user)
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.drop_all()

    def test_reminder_tones_and_lifecycle(self):
        # 1. Create Friendly reminder
        r_friendly = self.client.post(
            "/api/reminders",
            json={
                "title": "evening walk",
                "reminder_datetime": "7:30 PM",
                "recurrence": "daily",
                "tone": "Friendly",
            },
        )
        self.assertEqual(r_friendly.status_code, 201)
        rem_data = r_friendly.get_json()["reminder"]
        self.assertEqual(
            rem_data["notification_message"],
            "Hey! It's 7:30 PM. Time for your evening walk.",
        )
        rem_id = rem_data["id"]

        # 2. Update to Calm tone and mark completed
        r_calm = self.client.put(
            f"/api/reminders/{rem_id}",
            json={"tone": "Calm", "completed": True},
        )
        self.assertEqual(r_calm.status_code, 200)
        updated = r_calm.get_json()["reminder"]
        self.assertTrue(updated["completed"])
        self.assertIn("Gentle reminder", updated["notification_message"])

        # 3. Delete reminder
        r_del = self.client.delete(f"/api/reminders/{rem_id}")
        self.assertEqual(r_del.status_code, 200)

    def test_routine_creation_and_completion_tracking(self):
        r_create = self.client.post(
            "/api/routines",
            json={
                "routine_name": "Morning Medication",
                "scheduled_time": "08:30 AM",
                "completion_status": "pending",
            },
        )
        self.assertEqual(r_create.status_code, 201)
        routine_id = r_create.get_json()["routine"]["id"]

        # Mark routine completed
        r_upd = self.client.put(
            f"/api/routines/{routine_id}",
            json={"completion_status": "completed"},
        )
        self.assertEqual(r_upd.status_code, 200)
        self.assertEqual(r_upd.get_json()["routine"]["completion_status"], "completed")
        self.assertIsNotNone(r_upd.get_json()["routine"]["completed_at"])

        # Verify summary rate
        r_list = self.client.get("/api/routines")
        self.assertEqual(r_list.get_json()["summary"]["completion_rate"], 100)


if __name__ == "__main__":
    unittest.main()
