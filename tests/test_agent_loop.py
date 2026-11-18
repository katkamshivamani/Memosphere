"""Agent loop behaviour: grounding, limits, cancellation, duplicates."""

from __future__ import annotations

import pytest

from memory_agent.core.exceptions import ResponseCancelledError
from memory_agent.core.orchestrator import CancellationToken
from tests.helpers import ScriptedProvider, answer, ask, make_harness, tool_call


def test_grounded_answer_uses_tool_and_cites_source(tmp_path):
    harness = make_harness(tmp_path)
    provider = ScriptedProvider(
        [
            tool_call("search_memories", {"query": "wallet"}),
            answer("Your wallet is in the top drawer of the study desk."),
        ]
    )
    conversation_id, result = ask(harness, provider)

    assert conversation_id.startswith("conv_")
    assert result.evidence.grounding.value == "recorded"
    assert [source.title for source in result.evidence.sources] == ["Wallet location"]
    assert result.tool_trace[0].tool == "search_memories"
    assert result.tool_trace[0].ok is True
    assert result.rounds == 2


def test_unsupported_claim_is_replaced_with_missing_evidence_statement(tmp_path):
    harness = make_harness(tmp_path)
    provider = ScriptedProvider([answer("Your passport is in the kitchen drawer.")])
    _, result = ask(harness, provider, text="Where is my passport?")

    assert result.evidence.grounding.value == "missing"
    assert "saved memories" in result.text.lower()
    assert "kitchen drawer" not in result.text.lower()


def test_tool_rounds_are_hard_capped(tmp_path):
    def script(request, index):
        return tool_call("search_memories", {"query": f"wallet {index}"}, call_id=f"call_{index}")

    harness = make_harness(tmp_path)
    provider = ScriptedProvider(script)
    _, result = ask(harness, provider)

    assert result.rounds <= 5
    assert any(entry.error_code == "tool_round_limit" for entry in result.tool_trace) or (
        "limit" in result.text.lower()
    )


def test_duplicate_tool_call_is_not_executed_twice(tmp_path):
    from memory_agent.providers.schemas import FinishReason, ProviderResponse, ProviderToolRequest

    first = ProviderResponse(
        tool_calls=[
            ProviderToolRequest(id="c1", name="search_memories", arguments={"query": "wallet"}),
            ProviderToolRequest(id="c2", name="search_memories", arguments={"query": "wallet"}),
        ],
        finish_reason=FinishReason.TOOL_CALLS,
        provider_id="gemini",
    )
    harness = make_harness(tmp_path)
    provider = ScriptedProvider([first, answer("Your wallet is in the top drawer of the study desk.")])
    _, result = ask(harness, provider)

    assert len(result.tool_trace) == 2
    assert result.tool_trace[0].ok is True
    assert result.tool_trace[1].ok is False
    assert result.tool_trace[1].error_code == "duplicate_tool_call"
    assert result.tool_trace[1].duplicate is True


def test_cancellation_before_start_raises(tmp_path):
    harness = make_harness(tmp_path)
    provider = ScriptedProvider([answer("Anything")])
    token = CancellationToken()
    token.cancel()
    with pytest.raises(ResponseCancelledError):
        harness.runtime.agent.ask(
            user_id="user_001",
            text="Where is my wallet?",
            settings=harness.settings,
            provider=provider,
            token=token,
        )
    assert provider.requests == []


def test_invalid_session_is_refused(tmp_path):
    harness = make_harness(tmp_path, valid_users=())
    provider = ScriptedProvider([answer("Anything")])
    with pytest.raises(Exception) as info:
        ask(harness, provider)
    assert "session" in str(info.value).lower() or getattr(info.value, "code", "") != ""


def test_conversation_history_is_persisted(tmp_path):
    harness = make_harness(tmp_path)
    provider = ScriptedProvider(
        [tool_call("search_memories", {"query": "wallet"}), answer("Top drawer of the study desk.")]
    )
    conversation_id, _ = ask(harness, provider)
    stored = harness.runtime.conversations.store.list_messages("user_001", conversation_id)
    assert len(stored) == 2
    assert stored[0].role.value == "user"
    assert stored[1].role.value == "assistant"
