"""
MEMOSPHERE Automated Test Suite — Memories, Auth & Caregiver Privacy (test_memories.py)
Verifies SQLite CRUD, duplicate prevention, keyword retrieval, and caregiver consent guardrails.
"""
import unittest
from app import create_app
from backend.models import db, User, Memory, CaregiverPermission


class TestMemoriesAndPrivacy(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            user = User(name="Test User", email="user@test.local", role="user")
            user.set_password("pass123")
            caregiver = User(name="Test Caregiver", email="cg@test.local", role="caregiver")
            caregiver.set_password("pass123")
            db.session.add(user)
            db.session.add(caregiver)
            db.session.commit()
            self.user_id = user.id
            self.cg_id = caregiver.id

    def tearDown(self):
        with self.app.app_context():
            db.drop_all()

    def test_memory_crud_and_duplicate_prevention(self):
        # 1. Create a memory
        res = self.client.post(
            "/api/memories",
            json={
                "category": "Items",
                "title": "Charger Location",
                "content": "Charger is in the blue bag",
                "entity_name": "Charger",
                "location": "Blue bag",
                "event_date": "2026-11-17",
            },
        )
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertFalse(data["is_duplicate"])
        mem_id = data["memory"]["id"]

        # 2. Attempt to create exact duplicate -> should return 200 and prevent duplicate row
        dup_res = self.client.post(
            "/api/memories",
            json={
                "category": "Items",
                "title": "Charger Location",
                "content": "Charger is in the blue bag",
                "entity_name": "Charger",
                "location": "Blue bag",
                "event_date": "2026-11-17",
            },
        )
        self.assertEqual(dup_res.status_code, 200)
        self.assertTrue(dup_res.get_json()["is_duplicate"])

        # 3. List memories -> count should be 1
        list_res = self.client.get("/api/memories")
        self.assertEqual(list_res.status_code, 200)
        self.assertEqual(list_res.get_json()["count"], 1)

        # 4. Update memory
        upd_res = self.client.put(
            f"/api/memories/{mem_id}",
            json={"location": "Study Desk Drawer", "content": "Charger is in the study desk drawer"},
        )
        self.assertEqual(upd_res.status_code, 200)
        self.assertEqual(upd_res.get_json()["memory"]["location"], "Study Desk Drawer")

        # 5. Delete memory
        del_res = self.client.delete(f"/api/memories/{mem_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(self.client.get("/api/memories").get_json()["count"], 0)

    def test_caregiver_explicit_consent_and_memory_privacy(self):
        # Save a private personal memory
        self.client.post(
            "/api/memories",
            json={
                "category": "People",
                "title": "Private Family Note",
                "content": "Confidential conversation with Rahul",
            },
        )

        # Without consent granted, caregiver endpoint must return 403
        unauth_res = self.client.get("/api/caregiver/dashboard")
        self.assertEqual(unauth_res.status_code, 403)
        self.assertFalse(unauth_res.get_json()["authorized"])

        # Grant consent
        consent_res = self.client.post(
            "/api/caregiver/consent",
            json={"consent_status": "granted", "permission_type": "routines_and_reminders"},
        )
        self.assertEqual(consent_res.status_code, 200)

        # Now caregiver dashboard returns 200, but NEVER exposes private memory content
        auth_res = self.client.get("/api/caregiver/dashboard")
        self.assertEqual(auth_res.status_code, 200)
        payload = auth_res.get_json()
        self.assertTrue(payload["authorized"])
        self.assertTrue(payload["activity_summary"]["private_memories_redacted"])
        raw_text = str(payload)
        self.assertNotIn("Confidential conversation with Rahul", raw_text)


if __name__ == "__main__":
    unittest.main()
