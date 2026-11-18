"""Privacy modes, consent enforcement and untrusted-data handling."""

from __future__ import annotations

import pytest

from memory_agent.config import ContextMode
from memory_agent.core.exceptions import ConsentRequiredError, LocalOnlyUnavailableError
from memory_agent.core.intent import IntentClassifier
from memory_agent.security.consent_manager import ConsentScope

from tests.helpers import make_harness

CLASSIFIER = IntentClassifier()


def _build(harness, mode, text="Where did I keep my wallet?", provider_is_local=False, settings=None):
    intent = CLASSIFIER.classify(text)
    return harness.runtime.context_builder.build(
        user_id="user_001",
        query=text,
        mode=mode,
        intent=intent,
        settings=settings or harness.settings,
        provider_is_local=provider_is_local,
    )


def test_minimal_mode_only_includes_relevant_categories(tmp_path):
    harness = make_harness(tmp_path)
    bundle = _build(harness, ContextMode.MINIMAL)
    assert "memory" in bundle.categories
    assert "people" not in bundle.categories
    assert bundle.records
    assert "Wallet location" in bundle.rendered


def test_full_authorized_requires_consent(tmp_path):
    harness = make_harness(tmp_path)
    with pytest.raises(ConsentRequiredError):
        _build(harness, ContextMode.FULL_AUTHORIZED)


def test_full_authorized_includes_multiple_categories_with_consent(tmp_path):
    harness = make_harness(tmp_path)
    harness.consent.grant(
        ConsentScope.FULL_CONTEXT,
        categories=["memory", "people", "places", "activities", "routines", "reminders"],
    )
    bundle = _build(harness, ContextMode.FULL_AUTHORIZED, text="What should I know today?")
    assert set(bundle.categories) >= {"memory", "person", "place"}
    assert bundle.char_count <= harness.settings.max_context_chars


def test_local_only_refuses_cloud_provider(tmp_path):
    harness = make_harness(tmp_path)
    with pytest.raises(LocalOnlyUnavailableError):
        _build(harness, ContextMode.LOCAL_ONLY, provider_is_local=False)


def test_local_only_works_with_local_provider(tmp_path):
    harness = make_harness(tmp_path)
    bundle = _build(harness, ContextMode.LOCAL_ONLY, provider_is_local=True)
    assert bundle.mode is ContextMode.LOCAL_ONLY
    assert "Wallet location" in bundle.rendered


def test_secret_like_content_is_redacted(tmp_path):
    harness = make_harness(tmp_path)
    harness.suite.memories.rows.append(
        {
            "id": "mem_secret",
            "user_id": "user_001",
            "title": "Service account",
            "content": "api_key=sk-abcdefghijklmnopqrstuvwxyz123456 and password: hunter2",
            "category": "documents",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
    )
    bundle = _build(harness, ContextMode.MINIMAL, text="service account api key")
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in bundle.rendered
    assert "hunter2" not in bundle.rendered
    assert "[redacted]" in bundle.rendered


def test_instruction_like_record_is_wrapped_as_untrusted(tmp_path):
    harness = make_harness(tmp_path)
    bundle = _build(harness, ContextMode.MINIMAL, text="Search my memory for instructions")
    assert bundle.injection.has_findings, bundle.injection
    # The injected instruction text stays inside an untrusted-data wrapper.
    lowered = bundle.rendered.lower()
    assert "untrusted" in lowered
    assert lowered.index("untrusted") < lowered.index("ignore previous")


def test_injection_report_lists_record_ids(tmp_path):
    harness = make_harness(tmp_path)
    bundle = _build(harness, ContextMode.MINIMAL, text="Search my memory for instructions")
    assert "mem_injection" in bundle.injection.flagged_record_ids


def test_full_context_respects_character_budget(tmp_path):
    harness = make_harness(tmp_path)
    harness.consent.grant(ConsentScope.FULL_CONTEXT, categories=["memory", "people"])
    settings = harness.settings.model_copy(update={"max_context_chars": 600})
    bundle = _build(
        harness,
        ContextMode.FULL_AUTHORIZED,
        text="What should I know today?",
        settings=settings,
    )
    assert bundle.char_count <= 600
    assert bundle.truncated in (True, False)


def test_greeting_does_not_send_personal_records(tmp_path):
    harness = make_harness(tmp_path)
    bundle = _build(harness, ContextMode.MINIMAL, text="hello")
    assert bundle.records == []
    assert bundle.rendered == ""
