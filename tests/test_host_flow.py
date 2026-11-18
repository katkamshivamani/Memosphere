"""Full host-application flow: service gating, suggestions, consent."""

from __future__ import annotations

import pytest

from memory_agent.config import AgentSettings, ContextMode
from memory_agent.core.exceptions import (
    AgentDisabledError,
    ConsentRequiredError,
    LocalOnlyUnavailableError,
    MissingApiKeyError,
)
from memory_agent.security.api_key_manager import InMemoryCredentialStore
from memory_companion.composition import build_context
from memory_companion.config import AppPaths
from memory_companion.demo_data import ensure_demo_user

from tests.helpers import ScriptedProvider, answer, tool_call


def _setup(tmp_path, **settings_updates):
    ctx = build_context(
        paths=AppPaths(data_dir=tmp_path), credential_store=InMemoryCredentialStore()
    )
    user_id, _ = ensure_demo_user(ctx)
    ctx.key_manager.store_key("gemini", "test-key-not-real")
    settings = AgentSettings(
        enabled=True, provider_id="gemini", models={"gemini": "scripted-model"}
    ).model_copy(update=settings_updates)
    ctx.agent_runtime.settings_store.save(settings)
    return ctx, user_id


def test_send_message_refuses_when_disabled(tmp_path):
    ctx, user_id = _setup(tmp_path, enabled=False)
    try:
        with pytest.raises(AgentDisabledError):
            ctx.agent_runtime.service.send_message(user_id=user_id, text="Hello")
    finally:
        ctx.close()


def test_send_message_refuses_without_api_key(tmp_path):
    ctx = build_context(
        paths=AppPaths(data_dir=tmp_path), credential_store=InMemoryCredentialStore()
    )
    try:
        user_id, _ = ensure_demo_user(ctx)
        ctx.agent_runtime.settings_store.save(
            AgentSettings(enabled=True, provider_id="gemini")
        )
        with pytest.raises(MissingApiKeyError):
            ctx.agent_runtime.service.send_message(user_id=user_id, text="Hello")
    finally:
        ctx.close()


def test_full_context_requires_consent_at_service_level(tmp_path):
    ctx, user_id = _setup(tmp_path, context_mode=ContextMode.FULL_AUTHORIZED)
    try:
        with pytest.raises(ConsentRequiredError):
            ctx.agent_runtime.service.send_message(user_id=user_id, text="Where is my wallet?")
        with pytest.raises(ConsentRequiredError):
            ctx.agent_runtime.service.update_settings(
                AgentSettings(enabled=True, context_mode=ContextMode.FULL_AUTHORIZED)
            )
    finally:
        ctx.close()


def test_local_only_rejects_cloud_provider(tmp_path):
    ctx, user_id = _setup(tmp_path, context_mode=ContextMode.LOCAL_ONLY)
    try:
        with pytest.raises(LocalOnlyUnavailableError):
            ctx.agent_runtime.service.send_message(user_id=user_id, text="Where is my wallet?")
    finally:
        ctx.close()


def test_end_to_end_answer_and_pending_suggestion(tmp_path):
    ctx, user_id = _setup(tmp_path)
    provider = ScriptedProvider(
        [
            tool_call(
                "suggest_memory_save",
                {
                    "title": "Hearing aid batteries",
                    "content": "Spare hearing aid batteries are in the kitchen drawer.",
                    "category": "objects",
                    "reason": "You said you keep forgetting where they are.",
                },
            ),
            answer("I prepared a suggestion for you to review."),
        ]
    )
    ctx.agent_runtime.service._provider_factory = lambda *a, **k: provider
    try:
        before = ctx.memories.count(user_id)
        outcome = ctx.agent_runtime.service.send_message(
            user_id=user_id, text="Remember that spare hearing aid batteries are in the kitchen drawer."
        )
        assert outcome.conversation_id.startswith("conv_")
        assert outcome.provider_id == "gemini"
        assert len(outcome.suggestions) == 1
        pending = outcome.suggestions[0]
        assert pending.status.value == "pending_approval"
        assert ctx.memories.count(user_id) == before

        completed = ctx.agent_runtime.service.approve_suggestion(user_id, pending.id)
        assert completed.status.value == "completed"
        assert ctx.memories.count(user_id) == before + 1
        assert any(
            row["title"] == "Hearing aid batteries"
            for row in ctx.memories.search_memories(user_id, "batteries")
        )
    finally:
        ctx.close()


def test_provider_is_closed_after_a_turn(tmp_path):
    ctx, user_id = _setup(tmp_path)
    provider = ScriptedProvider([answer("I cannot find that in your records.")])
    ctx.agent_runtime.service._provider_factory = lambda *a, **k: provider
    try:
        ctx.agent_runtime.service.send_message(user_id=user_id, text="Where is my wallet?")
        assert provider.closed is True
    finally:
        ctx.close()


def test_suggestion_requires_write_permission_in_host_executor(tmp_path):
    ctx, user_id = _setup(tmp_path)
    provider = ScriptedProvider(
        [
            tool_call(
                "suggest_memory_save",
                {"title": "TV remote", "content": "Remote is on the sofa.", "reason": "Note."},
            ),
            answer("Suggestion prepared."),
        ]
    )
    ctx.agent_runtime.service._provider_factory = lambda *a, **k: provider
    try:
        ctx.auth.set_permission(user_id, "memory.create", False)
        outcome = ctx.agent_runtime.service.send_message(user_id=user_id, text="Remember the remote.")
        pending = outcome.suggestions[0]
        with pytest.raises(Exception):
            ctx.agent_runtime.service.approve_suggestion(user_id, pending.id)
    finally:
        ctx.close()
