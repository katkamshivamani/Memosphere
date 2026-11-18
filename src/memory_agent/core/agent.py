"""High-level Personal Memory Agent facade.

Combines conversation state, orchestration and an evidence-first answer policy.
Application services (``memory_agent.services``) own provider/key resolution and
suggestion persistence.
"""

from __future__ import annotations

from typing import Optional

from memory_agent.config import AgentSettings
from memory_agent.core.conversation import ConversationManager
from memory_agent.core.exceptions import InvalidRequestError
from memory_agent.core.intent import IntentClassifier
from memory_agent.core.orchestrator import AgentTurnResult, CancellationToken, Orchestrator
from memory_agent.models.message import Conversation, Message
from memory_agent.providers.base import AIProvider
from memory_agent.security.permission_guard import PermissionGuard


class PersonalMemoryAgent:
    """Evidence-based personal memory assistant."""

    def __init__(
        self,
        *,
        orchestrator: Orchestrator,
        conversations: ConversationManager,
        guard: PermissionGuard,
        classifier: Optional[IntentClassifier] = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._conversations = conversations
        self._guard = guard
        self._classifier = classifier or IntentClassifier()

    # ------------------------------------------------------------------ #
    # Conversation helpers
    # ------------------------------------------------------------------ #
    def ensure_conversation(
        self, user_id: str, conversation_id: Optional[str] = None, *, first_message: str = ""
    ) -> Conversation:
        self._guard.ensure_session(user_id)
        title = (first_message or "").strip()
        if len(title) > 60:
            title = title[:57].rstrip() + "…"
        return self._conversations.ensure_conversation(
            user_id, conversation_id, title=title or "New conversation"
        )

    def list_conversations(self, user_id: str, limit: int = 20) -> list[Conversation]:
        self._guard.ensure_session(user_id)
        return self._conversations.store.list_conversations(user_id, limit=limit)

    def messages(self, user_id: str, conversation_id: str, limit: int = 100) -> list[Message]:
        self._guard.ensure_session(user_id)
        return list(self._conversations.messages(user_id, conversation_id, limit=limit))

    def clear_conversation(self, user_id: str, conversation_id: str) -> None:
        self._guard.ensure_session(user_id)
        self._conversations.clear(user_id, conversation_id)

    # ------------------------------------------------------------------ #
    # Ask
    # ------------------------------------------------------------------ #
    def ask(
        self,
        *,
        user_id: str,
        text: str,
        settings: AgentSettings,
        provider: AIProvider,
        conversation_id: Optional[str] = None,
        token: Optional[CancellationToken] = None,
    ) -> tuple[str, AgentTurnResult]:
        """Answer one question. Returns ``(conversation_id, result)``.

        The user message is persisted before the provider call; the assistant
        message is persisted only after a grounded answer is produced.
        """
        if not text or not text.strip():
            raise InvalidRequestError("Empty user message.", user_message="Type a question first.")

        self._guard.ensure_session(user_id)
        conversation = self.ensure_conversation(user_id, conversation_id, first_message=text)
        history = self._conversations.history(
            user_id, conversation.id, max_chars=settings.max_context_chars
        )
        self._conversations.record_user(conversation.id, text.strip())

        result = self._orchestrator.run(
            user_id=user_id,
            user_text=text,
            settings=settings,
            provider=provider,
            history=history,
            conversation_id=conversation.id,
            token=token,
        )

        self._conversations.record_assistant(
            conversation.id,
            result.text,
            evidence=result.evidence_dict(),
            tool_trace=[entry.model_dump() for entry in result.tool_trace],
            error_code=result.error_code,
        )
        return conversation.id, result

    # ------------------------------------------------------------------ #
    # Introspection used by the settings UI / docs
    # ------------------------------------------------------------------ #
    def classify(self, text: str):
        return self._classifier.classify(text)
