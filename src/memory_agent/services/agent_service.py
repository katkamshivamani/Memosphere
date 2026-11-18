"""Application service that wires the agent to the settings, keys and stores.

This is the boundary the UI uses.  It resolves the provider (including secure key
retrieval), enforces the enabled/privacy preconditions, runs the agent and
persists any suggestions as *pending*.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict

from memory_agent.config import AgentSettings, ContextMode, SettingsStore
from memory_agent.core.agent import PersonalMemoryAgent
from memory_agent.core.conversation import ConversationManager
from memory_agent.core.exceptions import (
    AgentDisabledError,
    AgentError,
    ConsentRequiredError,
    LocalOnlyUnavailableError,
    MissingApiKeyError,
)
from memory_agent.core.orchestrator import AgentTurnResult, CancellationToken
from memory_agent.models.suggestion import Suggestion
from memory_agent.providers.base import AIProvider
from memory_agent.providers.registry import create_provider, get_provider_info, list_provider_info
from memory_agent.providers.schemas import ConnectionTestResult, ModelInfo
from memory_agent.security.api_key_manager import ApiKeyManager
from memory_agent.security.consent_manager import ConsentManager, ConsentScope
from memory_agent.security.permission_guard import PermissionGuard
from memory_agent.services.suggestion_service import SuggestionService

logger = logging.getLogger("memory_agent.service")


class ChatOutcome(BaseModel):
    """Result returned to the UI for one message."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    turn: AgentTurnResult
    suggestions: list[Suggestion] = []
    provider_id: str = ""


class AgentService:
    def __init__(
        self,
        *,
        agent: PersonalMemoryAgent,
        conversations: ConversationManager,
        settings_store: SettingsStore,
        key_manager: ApiKeyManager,
        consent: ConsentManager,
        suggestions: SuggestionService,
        guard: PermissionGuard,
        provider_factory: Optional[Callable[..., AIProvider]] = None,
    ) -> None:
        self._agent = agent
        self._conversations = conversations
        self._settings_store = settings_store
        self._keys = key_manager
        self._consent = consent
        self._suggestions = suggestions
        self._guard = guard
        self._provider_factory = provider_factory or create_provider

    # ------------------------------------------------------------------ #
    # Settings / provider state
    # ------------------------------------------------------------------ #
    def settings(self) -> AgentSettings:
        return self._settings_store.load()

    def update_settings(self, settings: AgentSettings) -> AgentSettings:
        """Validate and persist settings; secrets are rejected by the store."""
        if settings.context_mode is ContextMode.FULL_AUTHORIZED and not self._consent.is_granted(
            ConsentScope.FULL_CONTEXT
        ):
            raise ConsentRequiredError(
                "Full authorized context requires explicit consent before it can be enabled.",
            )
        if settings.context_mode is ContextMode.LOCAL_ONLY:
            if not get_provider_info(settings.provider_id).is_local:
                raise LocalOnlyUnavailableError(
                    "Local-only mode requires a local provider to be selected.",
                )
        self._settings_store.save(settings)
        return settings

    def set_enabled(self, enabled: bool) -> AgentSettings:
        settings = self._settings_store.load().model_copy(update={"enabled": enabled})
        if enabled:
            self.ensure_ready(settings)
        self._settings_store.save(settings)
        return settings

    def set_context_mode(self, mode: ContextMode) -> AgentSettings:
        settings = self._settings_store.load().model_copy(update={"context_mode": mode})
        return self.update_settings(settings)

    def ensure_ready(self, settings: Optional[AgentSettings] = None) -> None:
        """Raise a precise error when the agent cannot run as configured."""
        settings = settings or self._settings_store.load()
        info = get_provider_info(settings.provider_id)
        if not info.requires_api_key:
            return
        if not self._keys.has_key(settings.provider_id):
            raise MissingApiKeyError(
                f"No API key stored for {settings.provider_id}.",
            )

    def provider_status(self) -> list[dict]:
        settings = self._settings_store.load()
        statuses = self._keys.provider_status()
        for item in statuses:
            item["selected"] = item["provider_id"] == settings.provider_id
            item["model"] = settings.model_for(str(item["provider_id"]))
        return statuses

    def available_models(self, provider_id: Optional[str] = None) -> list[ModelInfo]:
        settings = self._settings_store.load()
        provider_id = provider_id or settings.provider_id
        provider = self._build_provider(settings, provider_id=provider_id)
        return provider.get_available_models()

    def test_connection(
        self,
        *,
        provider_id: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> ConnectionTestResult:
        settings = self._settings_store.load()
        provider_id = provider_id or settings.provider_id
        return self._keys.test_connection(
            provider_id,
            api_key=api_key,
            model=model or settings.model_for(provider_id),
            base_url=base_url or settings.base_urls.get(provider_id),
            timeout_s=min(20.0, settings.provider_timeout_s),
        )

    def save_provider_settings(
        self, provider_id: str, model: Optional[str] = None, base_url: Optional[str] = None
    ) -> AgentSettings:
        get_provider_info(provider_id)  # validates
        settings = self._settings_store.load()
        models = dict(settings.models)
        if model:
            models[provider_id] = model
        base_urls = dict(settings.base_urls)
        if base_url:
            base_urls[provider_id] = base_url
        updated = settings.model_copy(
            update={"provider_id": provider_id, "models": models, "base_urls": base_urls}
        )
        return self.update_settings(updated)

    # ------------------------------------------------------------------ #
    # Consent
    # ------------------------------------------------------------------ #
    def grant_full_context_consent(self, categories: list[str]) -> None:
        self._consent.grant(ConsentScope.FULL_CONTEXT, categories=categories)

    def withdraw_full_context_consent(self) -> None:
        self._consent.revoke(ConsentScope.FULL_CONTEXT)
        settings = self._settings_store.load()
        if settings.context_mode is ContextMode.FULL_AUTHORIZED:
            self._settings_store.save(
                settings.model_copy(update={"context_mode": ContextMode.MINIMAL})
            )

    def grant_cloud_transcription_consent(self) -> None:
        self._consent.grant(ConsentScope.CLOUD_TRANSCRIPTION, categories=["audio"])

    def withdraw_cloud_transcription_consent(self) -> None:
        self._consent.revoke(ConsentScope.CLOUD_TRANSCRIPTION)

    def has_full_context_consent(self) -> bool:
        return self._consent.is_granted(ConsentScope.FULL_CONTEXT)

    def has_cloud_transcription_consent(self) -> bool:
        return self._consent.is_granted(ConsentScope.CLOUD_TRANSCRIPTION)

    # ------------------------------------------------------------------ #
    # Chat
    # ------------------------------------------------------------------ #
    def send_message(
        self,
        *,
        user_id: str,
        text: str,
        conversation_id: Optional[str] = None,
        token: Optional[CancellationToken] = None,
    ) -> ChatOutcome:
        self._guard.ensure_session(user_id)
        settings = self._settings_store.load()
        if not settings.enabled:
            raise AgentDisabledError("The assistant is disabled in settings.")
        self.ensure_ready(settings)

        if settings.context_mode is ContextMode.FULL_AUTHORIZED and not self.has_full_context_consent():
            raise ConsentRequiredError("Full context consent is missing.")
        if settings.context_mode is ContextMode.LOCAL_ONLY and not get_provider_info(
            settings.provider_id
        ).is_local:
            raise LocalOnlyUnavailableError(
                "Local-only mode requires a local provider. Cloud providers are disabled in this mode."
            )

        provider = self._build_provider(settings)
        try:
            conversation_id, turn = self._agent.ask(
                user_id=user_id,
                text=text,
                settings=settings,
                provider=provider,
                conversation_id=conversation_id,
                token=token,
            )
        except AgentError:
            raise
        finally:
            provider.close()

        persisted: list[Suggestion] = []
        for suggestion in turn.suggestions:
            try:
                persisted.append(
                    self._suggestions.create_from_agent(
                        suggestion.model_copy(
                            update={
                                "user_id": user_id,
                                "conversation_id": conversation_id,
                                "status": suggestion.status,
                            }
                        )
                    )
                )
            except Exception as exc:
                logger.error("Could not persist suggestion: %s", type(exc).__name__)

        return ChatOutcome(
            conversation_id=conversation_id,
            turn=turn,
            suggestions=persisted,
            provider_id=turn.provider_id or settings.provider_id,
        )

    def list_conversations(self, user_id: str, limit: int = 20):
        self._guard.ensure_session(user_id)
        return self._conversations.store.list_conversations(user_id, limit=limit)

    # ------------------------------------------------------------------ #
    # Credentials (never return the key itself)
    # ------------------------------------------------------------------ #
    def save_api_key(self, provider_id: str, api_key: str) -> None:
        self._keys.store_key(provider_id, api_key)

    def delete_api_key(self, provider_id: str) -> None:
        self._keys.delete_key(provider_id)

    @property
    def credential_store_status(self) -> str:
        return self._keys.store_status

    @property
    def credential_store_available(self) -> bool:
        return self._keys.store_available

    def masked_api_key(self, provider_id: str) -> Optional[str]:
        return self._keys.masked_key(provider_id)

    def conversation_messages(self, user_id: str, conversation_id: str, limit: int = 100):
        self._guard.ensure_session(user_id)
        return self._conversations.messages(user_id, conversation_id, limit=limit)

    def clear_conversation(self, user_id: str, conversation_id: str) -> None:
        self._guard.ensure_session(user_id)
        self._agent.clear_conversation(user_id, conversation_id)

    # ------------------------------------------------------------------ #
    # Suggestions (user actions from the UI only)
    # ------------------------------------------------------------------ #
    def list_pending_suggestions(self, user_id: str):
        return self._suggestions.list_pending(user_id)

    def approve_suggestion(self, user_id: str, suggestion_id: str):
        return self._suggestions.approve(user_id, suggestion_id)

    def reject_suggestion(self, user_id: str, suggestion_id: str):
        return self._suggestions.reject(user_id, suggestion_id)

    def edit_suggestion(
        self,
        user_id: str,
        suggestion_id: str,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        payload_updates: Optional[dict] = None,
    ):
        return self._suggestions.edit(
            user_id,
            suggestion_id,
            title=title,
            description=description,
            payload_updates=payload_updates,
        )

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #
    def _build_provider(
        self, settings: AgentSettings, provider_id: Optional[str] = None
    ) -> AIProvider:
        provider_id = provider_id or settings.provider_id
        info = get_provider_info(provider_id)
        api_key = None
        if info.requires_api_key:
            api_key = self._keys.get_key(provider_id)
            if not api_key:
                raise MissingApiKeyError(
                    f"No API key stored for {provider_id}.",
                    user_message="Add an API key in Assistant settings before asking a question.",
                )
        return self._provider_factory(
            provider_id,
            api_key=api_key,
            model=settings.model_for(provider_id),
            base_url=settings.base_urls.get(provider_id),
            timeout_s=settings.provider_timeout_s,
        )

    def provider_catalog(self) -> list[dict]:
        return [
            {
                "id": info.id,
                "label": info.label,
                "is_local": info.is_local,
                "requires_api_key": info.requires_api_key,
                "supports_tools": info.supports_tools,
                "supports_streaming": info.supports_streaming,
                "supports_audio_transcription": info.supports_audio_transcription,
                "notes": info.notes,
                "documentation_url": info.documentation_url,
            }
            for info in list_provider_info()
        ]
