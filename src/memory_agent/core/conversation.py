"""Conversation state and provider-facing history.

Conversation content is personal data.  The host application stores it in the
shared encrypted database; :class:`InMemoryConversationStore` exists only for
tests and development.
"""

from __future__ import annotations

import abc
import threading
from typing import Optional, Sequence

from memory_agent.models.message import Conversation, Message, Role, utc_now
from memory_agent.providers.schemas import ProviderMessage, ProviderRole


class ConversationStore(abc.ABC):
    """Storage contract implemented by the host application."""

    @abc.abstractmethod
    def create_conversation(self, user_id: str, title: str = "") -> Conversation: ...

    @abc.abstractmethod
    def get_conversation(self, user_id: str, conversation_id: str) -> Optional[Conversation]: ...

    @abc.abstractmethod
    def list_conversations(self, user_id: str, limit: int = 20) -> list[Conversation]: ...

    @abc.abstractmethod
    def add_message(self, message: Message) -> Message: ...

    @abc.abstractmethod
    def list_messages(
        self, user_id: str, conversation_id: str, limit: int = 100
    ) -> list[Message]: ...

    @abc.abstractmethod
    def clear_conversation(self, user_id: str, conversation_id: str) -> None: ...


class InMemoryConversationStore(ConversationStore):
    """Thread-safe store for tests. NOT used by the desktop application."""

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}
        self._messages: dict[str, list[Message]] = {}
        self._lock = threading.RLock()

    def create_conversation(self, user_id: str, title: str = "") -> Conversation:
        conversation = Conversation(user_id=user_id, title=title or "New conversation")
        with self._lock:
            self._conversations[conversation.id] = conversation
            self._messages[conversation.id] = []
        return conversation

    def get_conversation(self, user_id: str, conversation_id: str) -> Optional[Conversation]:
        with self._lock:
            conversation = self._conversations.get(conversation_id)
            if conversation and conversation.user_id == user_id:
                return conversation
            return None

    def list_conversations(self, user_id: str, limit: int = 20) -> list[Conversation]:
        with self._lock:
            items = [c for c in self._conversations.values() if c.user_id == user_id]
        return sorted(items, key=lambda c: c.updated_at, reverse=True)[:limit]

    def add_message(self, message: Message) -> Message:
        with self._lock:
            if message.conversation_id not in self._conversations:
                raise KeyError("Unknown conversation")
            self._messages.setdefault(message.conversation_id, []).append(message)
            conversation = self._conversations[message.conversation_id]
            self._conversations[message.conversation_id] = conversation.model_copy(
                update={"updated_at": utc_now(), "title": conversation.title}
            )
        return message

    def list_messages(self, user_id: str, conversation_id: str, limit: int = 100) -> list[Message]:
        with self._lock:
            conversation = self._conversations.get(conversation_id)
            if conversation is None or conversation.user_id != user_id:
                return []
            messages = list(self._messages.get(conversation_id, []))
        return messages[-limit:]

    def clear_conversation(self, user_id: str, conversation_id: str) -> None:
        with self._lock:
            conversation = self._conversations.get(conversation_id)
            if conversation and conversation.user_id == user_id:
                self._messages[conversation_id] = []


class ConversationManager:
    """Creates conversations and builds bounded provider history."""

    def __init__(
        self,
        store: ConversationStore,
        *,
        max_history_messages: int = 12,
        max_history_chars: int = 8000,
    ) -> None:
        self._store = store
        self._max_messages = max_history_messages
        self._max_chars = max_history_chars

    @property
    def store(self) -> ConversationStore:
        return self._store

    def ensure_conversation(
        self, user_id: str, conversation_id: Optional[str] = None, *, title: str = ""
    ) -> Conversation:
        if conversation_id:
            existing = self._store.get_conversation(user_id, conversation_id)
            if existing is not None:
                return existing
        return self._store.create_conversation(user_id, title=title)

    def history(
        self, user_id: str, conversation_id: str, *, max_chars: Optional[int] = None
    ) -> list[ProviderMessage]:
        """Return recent user/assistant turns, oldest first, within a char budget."""
        messages = self._store.list_messages(
            user_id, conversation_id, limit=self._max_messages * 2
        )
        budget = max_chars or self._max_chars
        selected: list[Message] = []
        used = 0
        for message in reversed(messages):
            if message.role not in (Role.USER, Role.ASSISTANT):
                continue
            if not message.content:
                continue
            size = len(message.content)
            if used + size > budget and selected:
                break
            used += size
            selected.append(message)
            if len(selected) >= self._max_messages:
                break
        selected.reverse()
        return [
            ProviderMessage(
                role=ProviderRole.USER if message.role is Role.USER else ProviderRole.ASSISTANT,
                text=message.content,
            )
            for message in selected
        ]

    def record_user(self, conversation_id: str, text: str) -> Message:
        return self._store.add_message(
            Message(conversation_id=conversation_id, role=Role.USER, content=text)
        )

    def record_assistant(
        self,
        conversation_id: str,
        text: str,
        *,
        evidence: Optional[dict] = None,
        tool_trace: Optional[list[dict]] = None,
        error_code: Optional[str] = None,
    ) -> Message:
        return self._store.add_message(
            Message(
                conversation_id=conversation_id,
                role=Role.ASSISTANT,
                content=text,
                evidence=evidence,
                tool_trace=tool_trace,
                error_code=error_code,
            )
        )

    def messages(self, user_id: str, conversation_id: str, limit: int = 100) -> Sequence[Message]:
        return self._store.list_messages(user_id, conversation_id, limit=limit)

    def clear(self, user_id: str, conversation_id: str) -> None:
        self._store.clear_conversation(user_id, conversation_id)
