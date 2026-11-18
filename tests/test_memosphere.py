import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app
from database import init_db


class TestMemosphereDementiaCompanion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db(force_reseed=True)
        cls.client = TestClient(app)

    def test_01_authentication_and_selective_permissions(self):
        # Patient login
        res = self.client.post("/api/auth/login", json={"username": "patient", "password": "patient123"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])
        self.assertEqual(res.json()["user"]["role"], "patient")

        # Caregiver permissions update
        p_res = self.client.patch("/api/auth/permissions", json={"canViewMemories": False})
        self.assertEqual(p_res.status_code, 200)
        self.assertFalse(p_res.json()["permissions"]["canViewMemories"])
        # Restore permission
        self.client.patch("/api/auth/permissions", json={"canViewMemories": True})

    def test_02_existing_people_and_a1_familiar_faces_recognition(self):
        res = self.client.get("/api/people?q=coffee")
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertTrue(any("Ananya" in p["name"] for p in data))

        rec_res = self.client.get("/api/people/recognize?q=Ananya")
        self.assertEqual(rec_res.status_code, 200)
        self.assertGreaterEqual(len(rec_res.json()["matches"]), 1)
        self.assertIn("never automatically identified", rec_res.json()["disclaimer"])

    def test_03_a2_daily_orientation_and_a3_memory_album(self):
        ori = self.client.get("/api/orientation")
        self.assertEqual(ori.status_code, 200)
        self.assertIn("dayOfWeek", ori.json())
        self.assertIn("timeOfDay", ori.json())

        mem_create = self.client.post(
            "/api/memories",
            json={
                "title": "Conoor Tea Estate Family Trip",
                "category": "Family Memory",
                "storyText": "We rode the Nilgiri Mountain Toy Train together in 1998.",
                "eraOrYear": "1998",
                "favouriteMusic": "Ilaiyaraaja Instrumental",
            },
        )
        self.assertEqual(mem_create.status_code, 201)

    def test_04_a4_environment_guide_and_existing_places(self):
        env_res = self.client.get("/api/environment-guide")
        self.assertEqual(env_res.status_code, 200)
        names = [e["locationName"] for e in env_res.json()["data"]]
        self.assertIn("Bathroom", names)
        self.assertIn("Drinking Water", names)

    def test_05_a6_medication_confirmation_never_auto_taken(self):
        meds = self.client.get("/api/medications").json()["data"]
        pending_med = next(m for m in meds if m["status"] == "PENDING")

        # Snooze ("Remind Me Later") must NOT mark medication as TAKEN
        s_res = self.client.post(f"/api/medications/{pending_med['id']}/confirm", json={"action": "REMIND_LATER"})
        self.assertEqual(s_res.status_code, 200)
        self.assertEqual(s_res.json()["data"]["status"], "SNOOZED")

        # Explicit TAKEN confirmation records timestamp
        t_res = self.client.post(f"/api/medications/{pending_med['id']}/confirm", json={"action": "TAKEN"})
        self.assertEqual(t_res.status_code, 200)
        self.assertEqual(t_res.json()["data"]["status"], "TAKEN")
        self.assertIsNotNone(t_res.json()["recordedTimestamp"])

    def test_06_module_b_persistent_reminders_acknowledge_and_snooze(self):
        rem_res = self.client.post(
            "/api/reminders",
            json={
                "title": "08:00 AM Morning BP Tablet Check",
                "category": "Medication",
                "scheduledTime": "08:00 AM",
                "priority": "Critical",
                "repeatIntervalSec": 120,
                "snoozeDurationMins": 5,
            },
        )
        self.assertEqual(rem_res.status_code, 201)
        rem_id = rem_res.json()["data"]["id"]

        snz = self.client.post(f"/api/reminders/{rem_id}/snooze", json={"snoozeDurationMins": 5})
        self.assertEqual(snz.status_code, 200)
        self.assertEqual(snz.json()["data"]["status"], "SNOOZED")

        ack = self.client.post(f"/api/reminders/{rem_id}/acknowledge")
        self.assertEqual(ack.status_code, 200)
        self.assertEqual(ack.json()["data"]["status"], "ACKNOWLEDGED")

    def test_07_module_c_voice_memory_capture_and_patient_repeated_questions(self):
        # Voice proposal
        prop = self.client.post(
            "/api/voice/propose-capture",
            json={"utterance": "Remember that I kept my glasses on the bedside table."},
        )
        self.assertEqual(prop.status_code, 200)
        self.assertEqual(prop.json()["proposal"]["targetModule"], "places")

        # Confirm voice capture
        conf = self.client.post("/api/voice/confirm-capture", json=prop.json()["proposal"])
        self.assertEqual(conf.status_code, 201)

        # Patient asks repeated question ("Where are my glasses?")
        q1 = self.client.post("/api/ai-assistant", json={"mode": "ask", "prompt": "Where are my glasses?"})
        q2 = self.client.post("/api/ai-assistant", json={"mode": "ask", "prompt": "Where are my glasses?"})
        self.assertEqual(q1.status_code, 200)
        self.assertEqual(q2.status_code, 200)
        self.assertIn("bedside table", q2.json()["answer"].lower())
        self.assertGreaterEqual(q2.json()["repeatCount"], 2)

    def test_08_backend_api_key_never_exposed_and_geofence_reports(self):
        cfg = self.client.get("/api/ai/config").json()["config"]
        self.assertNotIn("gemini_api_key", cfg)
        self.assertNotIn("openai_api_key", cfg)
        self.assertIn("hasApiKeyConfigured", cfg)

        geo = self.client.get("/api/safety/geofence")
        self.assertEqual(geo.status_code, 200)
        self.assertIn("currentDistanceMeters", geo.json())

        rep = self.client.get("/api/reports/weekly")
        self.assertEqual(rep.status_code, 200)
        self.assertIn("weeklyCompletionPercentage", rep.json()["metrics"])


if __name__ == "__main__":
    unittest.main()
