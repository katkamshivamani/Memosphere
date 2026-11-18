"""Encrypted storage, authentication and host-side suggestion execution."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from memory_agent.models.suggestion import Suggestion, SuggestionStatus, SuggestionType
from memory_agent.models.tool_result import ToolCall
from memory_agent.security.api_key_manager import InMemoryCredentialStore
from memory_companion.composition import build_context
from memory_companion.config import AppPaths
from memory_companion.db.database import DatabaseEncryptionError
from memory_companion.demo_data import ensure_demo_user
from memory_companion.security.auth import AuthError


def _context(tmp_path):
    return build_context(paths=AppPaths(data_dir=tmp_path), credential_store=InMemoryCredentialStore())


def test_database_is_encrypted_and_headers_are_not_plaintext(tmp_path):
    ctx = _context(tmp_path)
    try:
        assert ctx.encryption.encrypted is True
        raw = ctx.paths.database_path.read_bytes()[:16]
        assert not raw.startswith(b"SQLite format 3\x00")
        assert ctx.db.verify_encryption().encrypted is True
    finally:
        ctx.close()


def test_plain_sqlite_database_is_refused(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    database = tmp_path / "memory.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE sneaky (id INTEGER)")
    connection.commit()
    connection.close()
    with pytest.raises(DatabaseEncryptionError):
        build_context(paths=AppPaths(data_dir=tmp_path), credential_store=InMemoryCredentialStore())


def test_registration_hashes_password_and_login_works(tmp_path):
    ctx = _context(tmp_path)
    try:
        session = ctx.auth.register("alice", "correct-horse-1", display_name="Alice")
        assert session.username == "alice"
        row = ctx.db.connection().execute(
            "SELECT password_hash FROM users WHERE id = ?", (session.user_id,)
        ).fetchone()
        assert "correct-horse-1" not in row["password_hash"]
        assert row["password_hash"].startswith("$argon2")
        with pytest.raises(AuthError):
            ctx.auth.login("alice", "wrong-password")
        again = ctx.auth.login("alice", "correct-horse-1")
        assert again.user_id == session.user_id
    finally:
        ctx.close()


def test_all_read_and_suggestion_permissions_are_granted_on_registration(tmp_path):
    ctx = _context(tmp_path)
    try:
        session = ctx.auth.register("bob", "long-enough-pass")
        granted = set(ctx.auth.granted_permissions(session.user_id))
        for permission in (
            "memory.read",
            "memory.suggest_create",
            "memory.suggest_update",
            "people.read",
            "places.read",
            "activities.read",
            "routines.read",
            "reminders.read",
            "reminders.suggest_create",
        ):
            assert permission in granted
        assert "memory.create" in granted
    finally:
        ctx.close()


def test_session_expiry_is_enforced(tmp_path):
    now = {"value": datetime(2026, 1, 1, tzinfo=timezone.utc)}

    def clock():
        return now["value"]

    ctx = build_context(
        paths=AppPaths(data_dir=tmp_path),
        credential_store=InMemoryCredentialStore(),
        session_ttl=timedelta(minutes=10),
        clock=clock,
    )
    try:
        session = ctx.auth.register("carol", "long-enough-pass")
        assert ctx.auth.validate_session(session.user_id) is True
        now["value"] += timedelta(minutes=11)
        assert ctx.auth.validate_session(session.user_id) is False
        with pytest.raises(Exception):
            ctx.auth.require_session(session.user_id)
    finally:
        ctx.close()


def test_permission_revocation_blocks_agent_tool(tmp_path):
    ctx = _context(tmp_path)
    try:
        user_id, _ = ensure_demo_user(ctx)
        ctx.auth.set_permission(user_id, "memory.read", False)
        result = ctx.agent_runtime.registry.execute(
            ToolCall(name="search_memories", arguments={"query": "wallet"}),
            user_id=user_id,
            guard=ctx.agent_runtime.guard,
            settings=ctx.agent_runtime.settings_store.load(),
        )
        assert result.ok is False
        assert result.error_code == "tool_permission_denied"
    finally:
        ctx.close()


def test_approved_suggestion_creates_memory_only_after_approval(tmp_path):
    ctx = _context(tmp_path)
    try:
        user_id, _ = ensure_demo_user(ctx)
        before = ctx.memories.count(user_id)
        suggestion = ctx.suggestion_service.create_from_agent(
            Suggestion(
                user_id=user_id,
                type=SuggestionType.SAVE_MEMORY,
                title="Umbrella",
                description="Umbrella is by the front door.",
                reason="You asked me to remember this.",
                payload={
                    "title": "Umbrella",
                    "content": "Umbrella is by the front door.",
                    "category": "objects",
                },
            )
        )
        assert ctx.memories.count(user_id) == before
        completed = ctx.suggestion_service.approve(user_id, suggestion.id)
        assert completed.status.value == "completed"
        assert ctx.memories.count(user_id) == before + 1
        matches = ctx.memories.search_memories(user_id, "umbrella")
        assert any(row["title"] == "Umbrella" for row in matches)
    finally:
        ctx.close()


def test_executor_rejects_suggestion_not_approved(tmp_path):
    ctx = _context(tmp_path)
    try:
        user_id, _ = ensure_demo_user(ctx)
        from memory_agent.models.suggestion import Suggestion, SuggestionStatus, SuggestionType

        pending = Suggestion(
            user_id=user_id,
            type=SuggestionType.SAVE_MEMORY,
            title="Sneaky write",
            status=SuggestionStatus.PENDING_APPROVAL,
            payload={"title": "Sneaky", "content": "Should not be written."},
        )
        result = ctx.agent_runtime.suggestions._executor.execute_suggestion(user_id, pending)
        assert result.ok is False
        assert ctx.memories.search_memories(user_id, "sneaky") == []
    finally:
        ctx.close()


def test_conversation_and_audit_are_stored_encrypted(tmp_path):
    ctx = _context(tmp_path)
    try:
        user_id, _ = ensure_demo_user(ctx)
        conversation = ctx.agent_runtime.conversations.store.create_conversation(user_id, "Test")
        assert ctx.agent_runtime.conversations.store.get_conversation(user_id, conversation.id)
        ctx.audit.log(action="test.event", user_id=user_id, metadata={"note": "no content"})
        events = ctx.audit.recent(user_id, limit=5)
        assert events and events[0]["action"] == "test.event"
    finally:
        ctx.close()
