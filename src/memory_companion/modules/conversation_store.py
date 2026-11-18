"""SQL implementation of the agent's ConversationStore contract.

Conversation text lives in the same SQLCipher database as the user's other
personal records - there is no second store.
"""

from __future__ import annotations

import json
from typing import Optional

from memory_agent.core.conversation import ConversationStore
from memory_agent.models.message import Conversation, Message, Role
from memory_companion.modules.common import utc_now_iso


class SqlConversationStore(ConversationStore):
    def __init__(self, db) -> None:
        self._db = db

    def create_conversation(self, user_id: str, title: str = "") -> Conversation:
        conversation = Conversation(user_id=user_id, title=title or "New conversation")
        with self._db.write() as conn:
            conn.execute(
                "INSERT INTO agent_conversations (id, user_id, title, context_mode, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    conversation.id,
                    user_id,
                    conversation.title,
                    conversation.context_mode,
                    conversation.created_at.isoformat(),
                    conversation.updated_at.isoformat(),
                ),
            )
        return conversation

    def get_conversation(self, user_id: str, conversation_id: str) -> Optional[Conversation]:
        row = self._db.connection().execute(
            "SELECT id, user_id, title, context_mode, created_at, updated_at "
            "FROM agent_conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).fetchone()
        if row is None:
            return None
        return Conversation(
            id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            context_mode=row["context_mode"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_conversations(self, user_id: str, limit: int = 20) -> list[Conversation]:
        rows = self._db.connection().execute(
            "SELECT id, user_id, title, context_mode, created_at, updated_at "
            "FROM agent_conversations WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [
            Conversation(
                id=row["id"],
                user_id=row["user_id"],
                title=row["title"],
                context_mode=row["context_mode"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def add_message(self, message: Message) -> Message:
        with self._db.write() as conn:
            conn.execute(
                "INSERT INTO agent_messages (id, conversation_id, user_id, role, content, "
                "evidence_json, tool_trace_json, error_code, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    message.id,
                    message.conversation_id,
                    self._message_user(message.conversation_id),
                    message.role.value,
                    message.content,
                    json.dumps(message.evidence, ensure_ascii=False) if message.evidence else None,
                    json.dumps(message.tool_trace, ensure_ascii=False) if message.tool_trace else None,
                    message.error_code,
                    message.created_at.isoformat(),
                ),
            )
            conn.execute(
                "UPDATE agent_conversations SET updated_at = ? WHERE id = ?",
                (utc_now_iso(), message.conversation_id),
            )
        return message

    def _message_user(self, conversation_id: str) -> str:
        row = self._db.connection().execute(
            "SELECT user_id FROM agent_conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if row is None:
            raise KeyError("Unknown conversation")
        return row["user_id"]

    def list_messages(
        self, user_id: str, conversation_id: str, limit: int = 100
    ) -> list[Message]:
        rows = self._db.connection().execute(
            "SELECT m.id, m.conversation_id, m.role, m.content, m.evidence_json, "
            "m.tool_trace_json, m.error_code, m.created_at "
            "FROM agent_messages m JOIN agent_conversations c ON c.id = m.conversation_id "
            "WHERE m.conversation_id = ? AND c.user_id = ? "
            "ORDER BY m.created_at ASC LIMIT ?",
            (conversation_id, user_id, limit),
        ).fetchall()
        messages: list[Message] = []
        for row in rows:
            messages.append(
                Message(
                    id=row["id"],
                    conversation_id=row["conversation_id"],
                    role=Role(row["role"]),
                    content=row["content"],
                    evidence=json.loads(row["evidence_json"]) if row["evidence_json"] else None,
                    tool_trace=json.loads(row["tool_trace_json"]) if row["tool_trace_json"] else None,
                    error_code=row["error_code"],
                    created_at=row["created_at"],
                )
            )
        return messages

    def clear_conversation(self, user_id: str, conversation_id: str) -> None:
        with self._db.write() as conn:
            owned = conn.execute(
                "SELECT 1 FROM agent_conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
            if owned:
                conn.execute(
                    "DELETE FROM agent_messages WHERE conversation_id = ?", (conversation_id,)
                )

    def delete_conversation(self, user_id: str, conversation_id: str) -> None:
        with self._db.write() as conn:
            conn.execute(
                "DELETE FROM agent_conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            )
