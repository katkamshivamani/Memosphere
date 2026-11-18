"""End-to-end scenarios across agent, services, privacy and proactive rules."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from memory_agent.config import AgentSettings, ContextMode, QuietHours
from memory_agent.core.exceptions import (
    ConsentRequiredError,
    ResponseCancelledError,
)
from memory_agent.core.orchestrator import CancellationToken
from memory_agent.integrations.memory_adapter import ReminderAdapter, RoutineAdapter
from memory_agent.models.suggestion import SuggestionStatus
from memory_agent.security.consent_manager import ConsentScope
from memory_agent.services.reminder_service import (
    ProactiveEngine,
    ProactiveEvent,
    ProactiveTrigger,
)

from tests.helpers import ScriptedProvider, answer, ask, make_harness, tool_call


# --------------------------------------------------------------------------- #
# Conversation continuity
# --------------------------------------------------------------------------- #
def test_second_turn_includes_conversation_history(tmp_path):
    harness = make_harness(tmp_path)
    provider = ScriptedProvider(
        [
            tool_call("search_memories", {"query": "wallet"}),
            answer("Your wallet is in the top drawer of the study desk."),
            tool_call("search_memories", {"query": "wallet"}, call_id="call_2"),
            answer("Still the top drawer of the study desk."),
        ]
    )

    conversation_id, _ = ask(harness, provider)
    second_id, second = harness.runtime.agent.ask(
        user_id="user_001",
        text="And you're sure?",
        settings=harness.settings,
        provider=provider,
        conversation_id=conversation_id,
    )

    assert second_id == conversation_id
    assert len(provider.requests) == 4
    second_request = provider.requests[2]
    roles = [message.role.value for message in second_request.messages]
    assert roles.count("user") == 2
    # Only the final answer is persisted as assistant history (tool rounds are not).
    assert roles.count("assistant") == 1
    assert "top drawer" in second.text.lower()


def test_history_does_not_leak_between_conversations(tmp_path):
    harness = make_harness(tmp_path)
    first = ScriptedProvider([answer("No record of that in your saved memories.")])
    ask(harness, first, text="Where is my passport?")
    second = ScriptedProvider([answer("No record of that in your saved memories.")])
    ask(harness, second, text="Who is Sarah?")
    assert len(second.requests[0].messages) == 1


# --------------------------------------------------------------------------- #
# Cancellation / limits
# --------------------------------------------------------------------------- #
def test_cancellation_after_first_round_stops_the_loop(tmp_path):
    harness = make_harness(tmp_path)
    token = CancellationToken()
    provider = ScriptedProvider(
        lambda request, index: (
            token.cancel() or tool_call("search_memories", {"query": "wallet"})
        )
    )
    with pytest.raises(ResponseCancelledError):
        harness.runtime.agent.ask(
            user_id="user_001",
            text="Where is my wallet?",
            settings=harness.settings,
            provider=provider,
            token=token,
        )
    assert len(provider.requests) == 1


# --------------------------------------------------------------------------- #
# Tool output is treated as untrusted data
# --------------------------------------------------------------------------- #
def test_tool_results_sent_to_the_model_are_marked_untrusted(tmp_path):
    harness = make_harness(tmp_path)
    provider = ScriptedProvider(
        [
            tool_call("search_memories", {"query": "neighbour"}),
            answer("I found a note about a neighbour."),
        ]
    )
    ask(harness, provider, text="Search my memory for instructions")

    tool_messages = [
        message
        for message in provider.requests[1].messages
        if message.role.value == "tool"
    ]
    assert tool_messages
    content = tool_messages[0].tool_results[0].content
    assert content.startswith("<<<UNTRUSTED_TOOL_RESULT")
    assert content.rstrip().endswith("<<<END_UNTRUSTED_TOOL_RESULT>>>")
    # The injected instruction is present only as data inside the wrapper.
    assert "ignore previous instructions" in content.lower()


# --------------------------------------------------------------------------- #
# Consent lifecycle
# --------------------------------------------------------------------------- #
def test_withdrawing_full_context_consent_blocks_the_next_request(tmp_path):
    harness = make_harness(tmp_path, settings=AgentSettings(
        enabled=True,
        provider_id="gemini",
        models={"gemini": "scripted-model"},
        context_mode=ContextMode.FULL_AUTHORIZED,
    ))
    harness.consent.grant(ConsentScope.FULL_CONTEXT, categories=["memory", "people"])
    from memory_agent.core.intent import IntentClassifier

    intent = IntentClassifier().classify("What should I know today?")
    harness.runtime.context_builder.build(
        user_id="user_001",
        query="What should I know today?",
        mode=ContextMode.FULL_AUTHORIZED,
        intent=intent,
        settings=harness.settings,
        provider_is_local=False,
    )

    harness.consent.revoke(ConsentScope.FULL_CONTEXT)
    with pytest.raises(ConsentRequiredError):
        harness.runtime.context_builder.build(
            user_id="user_001",
            query="What should I know today?",
            mode=ContextMode.FULL_AUTHORIZED,
            intent=intent,
            settings=harness.settings,
            provider_is_local=False,
        )


# --------------------------------------------------------------------------- #
# Suggestion editing then approval
# --------------------------------------------------------------------------- #
def test_edited_suggestion_writes_the_edited_content(tmp_path):
    harness = make_harness(tmp_path)
    provider = ScriptedProvider(
        [
            tool_call(
                "suggest_memory_save",
                {"title": "Spare keys", "content": "Keys are in the drawer.", "reason": "Note."},
            ),
            answer("I prepared a suggestion for you to review."),
        ]
    )
    _, turn = ask(harness, provider, text="Remember that the spare keys are in the drawer.")
    pending = harness.runtime.suggestions.create_from_agent(turn.suggestions[0])

    edited = harness.runtime.suggestions.edit(
        "user_001",
        pending.id,
        title="Blue bowl keys",
        payload_updates={"content": "Spare keys are in the blue bowl by the door."},
    )
    assert edited.status is SuggestionStatus.PENDING_APPROVAL
    completed = harness.runtime.suggestions.approve("user_001", edited.id)

    assert completed.status is SuggestionStatus.COMPLETED
    written = harness.suite.suggestions.executed[-1]
    assert written.title == "Blue bowl keys"
    assert written.payload["content"] == "Spare keys are in the blue bowl by the door."


# --------------------------------------------------------------------------- #
# Proactive suggestions
# --------------------------------------------------------------------------- #
def _proactive_engine(harness, *, settings=None, clock=None) -> ProactiveEngine:
    if settings is not None:
        harness.settings_store.save(settings)
    return ProactiveEngine(
        reminders=ReminderAdapter(harness.suite.reminders),
        routines=RoutineAdapter(harness.suite.routines),
        suggestions=harness.runtime.suggestions,
        settings_store=harness.settings_store,
        guard=harness.guard,
        clock=clock or (lambda: datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)),
    )


def _proactive_settings(**overrides) -> AgentSettings:
    base = AgentSettings(
        enabled=True,
        provider_id="gemini",
        models={"gemini": "scripted-model"},
        proactive_enabled=True,
    )
    return base.model_copy(update=overrides)


def _event(title: str, **kwargs) -> ProactiveEvent:
    return ProactiveEvent(
        user_id="user_001",
        trigger=ProactiveTrigger.UPCOMING_REMINDER,
        title=title,
        due_at=datetime(2026, 3, 12, 9, 0, tzinfo=timezone.utc),
        **kwargs,
    )


def test_proactive_suggestion_is_created_and_deduplicated(tmp_path):
    harness = make_harness(tmp_path)
    engine = _proactive_engine(harness, settings=_proactive_settings())

    first = engine.evaluate(_event("Take the bins out"))
    assert first.handled is True
    assert first.suggestion is not None
    assert first.suggestion.status is SuggestionStatus.PENDING_APPROVAL

    second = engine.evaluate(_event("Take the bins out"))
    assert second.suppressed is True
    assert second.suggestion is None
    assert len(harness.runtime.suggestions.list_pending("user_001")) == 1


def test_proactive_respects_disabled_and_quiet_hours(tmp_path):
    harness = make_harness(tmp_path)
    engine = _proactive_engine(harness, settings=_proactive_settings(proactive_enabled=False))
    assert engine.evaluate(_event("Call the clinic")).suppressed is True

    quiet = _proactive_settings(quiet_hours=QuietHours(enabled=True, start_hour=0, end_hour=24))
    engine = _proactive_engine(harness, settings=quiet)
    outcome = engine.evaluate(_event("Call the clinic"))
    assert outcome.suppressed is True
    assert "quiet" in outcome.reason.lower()


def test_proactive_missing_activity_never_claims_it_was_missed(tmp_path):
    harness = make_harness(tmp_path)
    engine = _proactive_engine(harness, settings=_proactive_settings())
    event = ProactiveEvent(
        user_id="user_001",
        trigger=ProactiveTrigger.EXPECTED_ACTIVITY_MISSING,
        title="Morning walk",
    )
    outcome = engine.evaluate(event)
    assert outcome.suggestion is not None
    description = outcome.suggestion.description.lower()
    assert "does not mean it did not happen" in description
    assert "missed" not in description
    assert "no record" in outcome.suggestion.title.lower()


def test_existing_reminder_title_is_treated_as_duplicate(tmp_path):
    harness = make_harness(tmp_path)
    engine = _proactive_engine(harness, settings=_proactive_settings())
    outcome = engine.evaluate(_event("Dentist appointment"))
    assert outcome.suppressed is True
    assert "already exists" in outcome.reason.lower()


def test_upcoming_reminder_event_builder_reads_records(tmp_path):
    harness = make_harness(tmp_path)
    engine = _proactive_engine(harness, settings=_proactive_settings())
    events = engine.upcoming_reminder_events("user_001", horizon_days=14)
    titles = {event.title for event in events}
    assert "Dentist appointment" in titles
    assert all(event.due_at is not None for event in events)
