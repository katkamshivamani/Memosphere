"""
MEMOSPHERE Multi-Provider Compatibility Regression Tests

Covers the confirmed findings of the compatibility audit:
  1. NVIDIA NIM adapter registration and OpenAI-compatible request/response contract.
  2. Per-provider model variables (no cross-provider model collision).
  3. Complete common BaseAIProvider contract on every provider.
  4. Gemini HTTP 400/404 error classification (bad key vs bad model/payload).
  5. Sanitized api_warning (no raw model output or exception text leakage).
  6. Location casing preservation in the deterministic fallback engine.
  7. Graceful /api/ai/test and /api/ai/settings handling of invalid input.

All external HTTP calls are mocked. No API keys are used or required.
"""
import os
import unittest
from unittest.mock import MagicMock, patch

from app import create_app
from config import Config
from backend.services.ai.ai_client import (
    AIClient,
    AIProviderError,
    BaseAIProvider,
    RuleBasedFallbackEngine,
)
from backend.services.ai.gemini_provider import GeminiProvider
from backend.services.ai.groq_provider import GroqProvider
from backend.services.ai.nvidia_nim_provider import NvidiaNimProvider
from backend.services.ai.openai_provider import OpenAIProvider
from backend.services.ai.provider_factory import ProviderFactory


class FakeProvider(BaseAIProvider):
    """Deterministic in-memory provider used to exercise the common contract."""

    provider_name = "fake"

    def __init__(self, answer="Grounded answer.", **kwargs):
        super().__init__(**kwargs)
        self.answer = answer

    def generate_completion(self, messages, json_mode=False):
        if json_mode:
            return (
                '{"category": "Items", "title": "Keys", "content": "Keys in drawer", '
                '"entity_name": "Keys", "location": "Drawer", "event_date": "2026-11-18"}'
            )
        return self.answer


class LeakyProvider(BaseAIProvider):
    """Simulates a provider whose parse failure contains sensitive raw model text."""

    provider_name = "leaky"

    def generate_completion(self, messages, json_mode=False):
        raise ValueError("SECRET_MODEL_OUTPUT_FRAGMENT must never reach the browser")


class TestMultiProviderCompatibility(unittest.TestCase):
    def setUp(self):
        self._runtime_models = dict(Config._RUNTIME_MODELS)
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        })
        self.client = self.app.test_client()

    def tearDown(self):
        Config._RUNTIME_MODELS = self._runtime_models

    def test_nvidia_nim_is_registered_with_official_endpoint(self):
        provider = ProviderFactory.create_provider("nvidia_nim", api_key="nvapi-test")
        self.assertIsInstance(provider, NvidiaNimProvider)
        self.assertEqual(provider.provider_name, "nvidia_nim")
        self.assertEqual(provider.model, "meta/llama-3.1-70b-instruct")
        self.assertEqual(
            provider.api_url,
            "https://integrate.api.nvidia.com/v1/chat/completions",
        )
        self.assertIn("nvidia_nim",
                      [p["id"] for p in AIClient().get_status()["supported_providers"]])

    @patch("backend.services.ai.nvidia_nim_provider.requests.post")
    def test_nvidia_nim_request_and_response_contract(self, mock_post):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"choices": [{"message": {"content": "OK"}}]}
        mock_post.return_value = response

        provider = ProviderFactory.create_provider(
            "nvidia_nim", api_key="nvapi-test", model="meta/llama-3.1-70b-instruct"
        )
        result = provider.generate_completion([
            {"role": "system", "content": "Reply OK"},
            {"role": "user", "content": "Ping"},
        ])

        self.assertEqual(result, "OK")
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://integrate.api.nvidia.com/v1/chat/completions")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer nvapi-test")
        self.assertEqual(kwargs["json"]["model"], "meta/llama-3.1-70b-instruct")
        self.assertEqual(kwargs["json"]["messages"][0]["role"], "system")
        self.assertEqual(kwargs["timeout"], provider.timeout)

    @patch("requests.post")
    def test_openai_compatible_endpoints_and_headers(self, mock_post):
        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.json.return_value = {"choices": [{"message": {"content": "OK"}}]}
        mock_post.return_value = ok_response

        cases = (
            (
                GroqProvider,
                "groq",
                "gsk-test",
                "llama-3.3-70b-versatile",
                "https://api.groq.com/openai/v1/chat/completions",
            ),
            (
                OpenAIProvider,
                "openai",
                "sk-test",
                "gpt-4o-mini",
                "https://api.openai.com/v1/chat/completions",
            ),
        )
        for index, (provider_cls, name, key, model, expected_url) in enumerate(cases):
            with self.subTest(provider=name):
                provider = provider_cls(api_key=key, model=model)
                reply = provider.generate_completion([{"role": "user", "content": "Ping"}])
                self.assertEqual(reply, "OK")
                args, kwargs = mock_post.call_args_list[index]
                self.assertEqual(args[0], expected_url)
                self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {key}")
                self.assertEqual(kwargs["json"]["model"], model)
                self.assertEqual(kwargs["timeout"], provider.timeout)

    def test_per_provider_models_never_collide(self):
        env = {
            "AI_MODEL": "legacy-wrong-model",
            "GROQ_MODEL": "groq-specific",
            "NVIDIA_NIM_MODEL": "nvidia-specific",
            "GEMINI_MODEL": "gemini-specific",
            "OPENAI_MODEL": "openai-specific",
        }
        with patch.dict(os.environ, env):
            expected = {
                "groq": "groq-specific",
                "nvidia_nim": "nvidia-specific",
                "gemini": "gemini-specific",
                "openai": "openai-specific",
            }
            for provider, model in expected.items():
                self.assertEqual(Config.get_ai_model(provider), model)
                self.assertEqual(
                    ProviderFactory.create_provider(provider, api_key="").model, model
                )

    def test_common_provider_contract_is_complete(self):
        required = (
            "generate_response",
            "extract_memories",
            "classify_information",
            "answer_memory_question",
            "test_connection",
        )
        for provider_cls in ProviderFactory.PROVIDERS.values():
            for method in required:
                self.assertTrue(hasattr(provider_cls, method),
                                f"{provider_cls.__name__} missing {method}")

        fake = FakeProvider(api_key="k", model="m")
        self.assertEqual(fake.generate_response([{"role": "user", "content": "hi"}]), "Grounded answer.")
        self.assertEqual(
            fake.answer_memory_question(
                question="Where are my keys?",
                retrieved_memories=[{"id": 1, "content": "Keys in drawer", "category": "Items"}],
            ),
            "Grounded answer.",
        )
        extracted = fake.extract_memories("I kept my keys in the drawer.")
        self.assertEqual(extracted["category"], "Items")
        self.assertEqual(fake.classify_information("I kept my keys in the drawer.")["category"], "Items")

    @patch("backend.services.ai.gemini_provider.requests.post")
    def test_gemini_http_400_does_not_always_mean_bad_key(self, mock_post):
        provider = GeminiProvider(api_key="test-key", model="some-model")
        messages = [{"role": "user", "content": "Ping"}]

        bad_request = MagicMock()
        bad_request.status_code = 400
        bad_request.json.return_value = {
            "error": {"code": 400, "message": "Model not found", "status": "INVALID_ARGUMENT"}
        }
        mock_post.return_value = bad_request
        with self.assertRaises(AIProviderError) as ctx:
            provider.generate_completion(messages)
        self.assertEqual(ctx.exception.error_code, "invalid_request")
        self.assertEqual(ctx.exception.status_code, 400)

        bad_key = MagicMock()
        bad_key.status_code = 400
        bad_key.json.return_value = {
            "error": {"code": 400, "message": "API key not valid. Please pass a valid API key.",
                      "status": "INVALID_ARGUMENT"}
        }
        mock_post.return_value = bad_key
        with self.assertRaises(AIProviderError) as ctx:
            provider.generate_completion(messages)
        self.assertEqual(ctx.exception.error_code, "invalid_api_key")

        not_found = MagicMock()
        not_found.status_code = 404
        mock_post.return_value = not_found
        with self.assertRaises(AIProviderError) as ctx:
            provider.generate_completion(messages)
        self.assertEqual(ctx.exception.error_code, "invalid_model")

    def test_api_warning_is_sanitized(self):
        result = AIClient(provider_override=LeakyProvider(api_key="k", model="m")).extract_memory(
            "I kept my keys in the drawer."
        )
        warning = result.get("api_warning", "")
        self.assertNotIn("SECRET_MODEL_OUTPUT_FRAGMENT", warning)
        self.assertIn("unexpected response format", warning)
        self.assertTrue(result["used_fallback"])

    def test_location_casing_is_preserved(self):
        result = RuleBasedFallbackEngine.extract_structured_memory(
            "I met Rahul at the college workshop yesterday.",
            reference_date="2026-11-18",
        )
        self.assertEqual(result["location"], "College workshop")
        self.assertEqual(result["category"], "People")

    def test_invalid_provider_connection_test_does_not_crash(self):
        response = self.client.post("/api/ai/test", json={"provider": "not_a_provider"})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertFalse(payload["connected"])
        self.assertEqual(payload["error_code"], "unsupported_provider")

    def test_settings_switch_updates_only_selected_provider_model(self):
        response = self.client.post(
            "/api/ai/settings",
            json={"provider": "gemini", "model": "gemini-custom-model", "api_key": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Config.get_ai_model("gemini"), "gemini-custom-model")
        self.assertNotEqual(Config.get_ai_model("openai"), "gemini-custom-model")
        self.assertEqual(response.get_json()["status"]["selected_provider"], "gemini")


if __name__ == "__main__":
    unittest.main()
