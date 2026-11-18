"""Live provider checks. Skipped unless real credentials are supplied.

Run explicitly with, for example:

    $env:GEMINI_API_KEY="..."
    python -m pytest tests/live -m live

These tests make real network calls and may consume free-tier quota. They are
never part of the default suite.
"""

from __future__ import annotations

import os

import pytest

from memory_agent.providers.registry import create_provider
from memory_agent.providers.schemas import ProviderMessage, ProviderRequest, ProviderRole

pytestmark = pytest.mark.live

GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY")


def _skip_unless(value, label):
    if not value:
        pytest.skip(f"{label} not set; live test skipped")


def test_gemini_lists_models_and_answers():
    _skip_unless(GEMINI_KEY, "GEMINI_API_KEY")
    provider = create_provider("gemini", api_key=GEMINI_KEY, timeout_s=30.0)
    models = provider.get_available_models()
    assert models, "Gemini returned no models for this key"
    response = provider.generate(
        ProviderRequest(
            messages=[
                ProviderMessage(role=ProviderRole.USER, text="Reply with the single word: ready")
            ],
            max_output_tokens=20,
            temperature=0.0,
        )
    )
    assert response.text
    assert response.provider_id == "gemini"


def test_openai_connection():
    _skip_unless(OPENAI_KEY, "OPENAI_API_KEY")
    provider = create_provider("openai", api_key=OPENAI_KEY, timeout_s=30.0)
    result = provider.validate_api_key()
    assert result.ok, result.message


def test_local_provider_connection():
    base_url = os.environ.get("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    provider = create_provider("local", base_url=base_url, timeout_s=5.0)
    result = provider.validate_api_key()
    if not result.ok:
        pytest.skip(f"No local OpenAI-compatible server at {base_url}: {result.message}")
    assert result.ok
