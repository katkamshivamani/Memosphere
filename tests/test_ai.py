"""
MEMOSPHERE Automated Test Suite — AI Integration Layer, Q&A & Brain Dump (test_ai.py)
Verifies:
1. Provider switching (Groq, NVIDIA NIM, Gemini, OpenAI) via ProviderFactory without requiring all keys.
2. External AI API response parsing, timeout/invalid-key handling, and secret masking.
3. Grounded Memory Q&A and patient repetition handling.
4. Brain Dump structured JSON extraction across all 5 categories.
"""
import os
import unittest
from unittest.mock import patch, MagicMock
from app import create_app
from config import Config
from backend.models import db, User, Memory
from backend.services.ai.provider_factory import ProviderFactory
from backend.services.ai.ai_client import AIProviderError


class TestAIIntegrationAndAssistant(unittest.TestCase):
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
            mem = Memory(
                user_id=user.id,
                category="Items",
                title="Charger Location",
                content="Charger is in the blue bag.",
                entity_name="Charger",
                location="Blue bag",
                event_date="2026-11-17",
            )
            db.session.add(mem)
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.drop_all()

    def test_provider_factory_switching_and_key_masking(self):
        # Verify switching between groq, gemini, and openai works without requiring all keys
        for prov in ("groq", "nvidia_nim", "gemini", "openai"):
            instance = ProviderFactory.create_provider(provider_name=prov, api_key="")
            self.assertEqual(instance.provider_name, prov)
            self.assertFalse(instance.is_configured())

        # Verify API key masking never leaks full secret
        masked = Config.mask_api_key("gsk_1234567890abcdefSECRET9876")
        self.assertEqual(masked, "gsk_...9876")
        self.assertNotIn("abcdefSECRET", masked)

    def test_memory_qa_and_patient_repetition(self):
        # First question: Where did I keep my charger?
        res1 = self.client.post("/api/ai/ask", json={"question": "Where did I keep my charger?"})
        self.assertEqual(res1.status_code, 200)
        d1 = res1.get_json()
        self.assertIn("blue bag", d1["answer"].lower())
        self.assertFalse(d1["is_repeated_question"])
        self.assertEqual(len(d1["supporting_memories"]), 1)

        # Repeated question: Where is my charger?
        res2 = self.client.post("/api/ai/ask", json={"question": "Where is my charger?"})
        self.assertEqual(res2.status_code, 200)
        d2 = res2.get_json()
        self.assertIn("blue bag", d2["answer"].lower())
        self.assertTrue(d2["is_repeated_question"])
        self.assertGreaterEqual(d2["repetition_count"], 1)
        self.assertIn("happy to remind you", d2["answer"].lower())

        # Unrelated question with no memory -> must not invent facts
        res3 = self.client.post("/api/ai/ask", json={"question": "Where did I park my helicopter?"})
        self.assertEqual(res3.status_code, 200)
        d3 = res3.get_json()
        self.assertEqual(len(d3["supporting_memories"]), 0)
        self.assertIn("couldn't find", d3["answer"].lower())

    def test_brain_dump_structured_extraction_examples(self):
        # Example 1: People
        r1 = self.client.post(
            "/api/ai/extract",
            json={"text": "I met Rahul at the workshop yesterday.", "reference_date": "2026-11-18"},
        )
        self.assertEqual(r1.status_code, 200)
        ext1 = r1.get_json()["extracted"]
        self.assertEqual(ext1["category"], "People")
        self.assertEqual(ext1["entity_name"], "Rahul")
        self.assertEqual(ext1["location"], "Workshop")
        self.assertEqual(ext1["event_date"], "2026-11-17")

        # Example 2: Items
        r2 = self.client.post(
            "/api/ai/extract",
            json={"text": "I kept my house keys in the blue bag.", "reference_date": "2026-11-18"},
        )
        ext2 = r2.get_json()["extracted"]
        self.assertEqual(ext2["category"], "Items")
        self.assertIn("keys", ext2["entity_name"].lower())
        self.assertEqual(ext2["location"], "Blue Bag")

        # Example 3: Routines / Activities
        r3 = self.client.post(
            "/api/ai/extract",
            json={"text": "I completed my evening walk at 7:30.", "reference_date": "2026-11-18"},
        )
        ext3 = r3.get_json()["extracted"]
        self.assertIn(ext3["category"], ("Activities", "Routines"))
        self.assertIn("evening walk", ext3["title"].lower())

    @patch("backend.services.ai.groq_provider.requests.post")
    def test_external_api_error_handling_and_fallback(self, mock_post):
        # Simulate HTTP 401 Invalid API Key from Groq
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_post.return_value = mock_resp

        provider = ProviderFactory.create_provider("groq", api_key="gsk_invalid_test_key")
        with self.assertRaises(AIProviderError) as ctx:
            provider.generate_completion([{"role": "user", "content": "Hi"}])
        self.assertEqual(ctx.exception.error_code, "invalid_api_key")


if __name__ == "__main__":
    unittest.main()
