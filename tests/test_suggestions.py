"""Suggestion lifecycle and approval gating."""

from __future__ import annotations

import pytest

from memory_agent.core.exceptions import InvalidRequestError, PermissionDeniedError
from memory_agent.models.suggestion import Suggestion, SuggestionStatus, SuggestionType

from tests.helpers import make_harness


def _suggestion(**overrides) -> Suggestion:
    data = {
        "user_id": "user_001",
        "type": SuggestionType.SAVE_MEMORY,
        "title": "Wallet location",
        "description": "Wallet is in the study desk drawer.",
        "reason": "You asked me to remember this.",
        "payload": {
            "title": "Wallet location",
            "content": "Wallet is in the study desk drawer.",
            "category": "objects",
        },
    }
    data.update(overrides)
    return Suggestion(**data)


def test_agent_suggestions_must_be_pending(tmp_path):
    harness = make_harness(tmp_path)
    approved = _suggestion(status=SuggestionStatus.APPROVED)
    with pytest.raises(InvalidRequestError):
        harness.runtime.suggestions.create_from_agent(approved)


def test_pending_suggestion_is_not_executed_until_approved(tmp_path):
    harness = make_harness(tmp_path)
    pending = harness.runtime.suggestions.create_from_agent(_suggestion())
    assert harness.suite.suggestions.executed == []
    assert harness.runtime.suggestions.list_pending("user_001")[0].id == pending.id

    completed = harness.runtime.suggestions.approve("user_001", pending.id)
    assert completed.status is SuggestionStatus.COMPLETED
    assert completed.payload["result_record_id"].startswith("mock_")
    assert len(harness.suite.suggestions.executed) == 1


def test_rejected_suggestion_is_not_executed(tmp_path):
    harness = make_harness(tmp_path)
    pending = harness.runtime.suggestions.create_from_agent(_suggestion())
    rejected = harness.runtime.suggestions.reject("user_001", pending.id)
    assert rejected.status is SuggestionStatus.REJECTED
    assert harness.suite.suggestions.executed == []
    with pytest.raises(InvalidRequestError):
        harness.runtime.suggestions.approve("user_001", pending.id)


def test_editing_a_pending_suggestion_keeps_it_pending(tmp_path):
    harness = make_harness(tmp_path)
    pending = harness.runtime.suggestions.create_from_agent(_suggestion())
    edited = harness.runtime.suggestions.edit(
        "user_001",
        pending.id,
        title="Wallet in the desk",
        payload_updates={"content": "Wallet is in the top drawer."},
    )
    assert edited.title == "Wallet in the desk"
    assert edited.payload["content"] == "Wallet is in the top drawer."
    assert edited.status is SuggestionStatus.PENDING_APPROVAL


def test_completed_suggestion_cannot_be_reapproved(tmp_path):
    harness = make_harness(tmp_path)
    pending = harness.runtime.suggestions.create_from_agent(_suggestion())
    harness.runtime.suggestions.approve("user_001", pending.id)
    with pytest.raises(InvalidRequestError):
        harness.runtime.suggestions.approve("user_001", pending.id)


def test_approval_requires_write_permission(tmp_path):
    harness = make_harness(tmp_path, denied={"memory.create"})
    pending = harness.runtime.suggestions.create_from_agent(_suggestion())
    with pytest.raises(PermissionDeniedError):
        harness.runtime.suggestions.approve("user_001", pending.id)
    assert harness.suite.suggestions.executed == []


def test_unknown_suggestion_is_reported_safely(tmp_path):
    harness = make_harness(tmp_path)
    with pytest.raises(Exception) as info:
        harness.runtime.suggestions.approve("user_001", "suggestion_missing")
    assert getattr(info.value, "user_message", "")


def test_suggestion_from_agent_tool_is_pending(tmp_path):
    from memory_agent.core.exceptions import AgentError

    harness = make_harness(tmp_path, denied={"memory.suggest_create"})
    # With the suggestion permission denied the tool must refuse to produce one.
    from tests.helpers import ScriptedProvider, answer, ask, tool_call

    provider = ScriptedProvider(
        [
            tool_call(
                "suggest_memory_save",
                {
                    "title": "Blue bowl",
                    "content": "Spare keys are in the blue bowl.",
                    "reason": "You asked me to remember this.",
                },
            ),
            answer("I could not prepare that suggestion."),
        ]
    )
    try:
        _, result = ask(harness, provider)
    except AgentError:
        return
    assert result.suggestions == []
