"""Test doubles and builders shared by the suite."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from memory_agent.config import AgentSettings, InMemorySettingsStore
from memory_agent.core.conversation import InMemoryConversationStore
from memory_agent.factory import AgentRuntime, build_runtime
from memory_agent.integrations.contracts import AgentIntegrations
from memory_agent.integrations.mocks import MockIntegrationSuite
from memory_agent.providers.base import AIProvider
from memory_agent.providers.schemas import (
    ConnectionTestResult,
    FinishReason,
    ModelInfo,
    ProviderInfo,
    ProviderRequest,
    ProviderResponse,
    ProviderToolRequest,
)
from memory_agent.security.api_key_manager import ApiKeyManager, InMemoryCredentialStore
from memory_agent.security.consent_manager import ConsentManager
from memory_agent.security.permission_guard import PermissionGuard
from memory_agent.services.suggestion_service import InMemorySuggestionStore


class Checker:
    """Permission/session checker used by PermissionGuard."""

    def __init__(
        self,
        valid_users: Sequence[str] = ("user_001",),
        denied: Sequence[str] = (),
    ) -> None:
        self.valid_users = set(valid_users)
        self.denied = set(denied)
        self.checks: list[tuple[str, str]] = []

    def validate_session(self, user_id: str) -> bool:
        return user_id in self.valid_users

    def has_permission(self, user_id: str, permission: str) -> bool:
        self.checks.append((user_id, permission))
        return user_id in self.valid_users and permission not in self.denied


@dataclass
class Harness:
    runtime: AgentRuntime
    suite: MockIntegrationSuite
    checker: Checker
    consent: ConsentManager
    guard: PermissionGuard
    settings_store: InMemorySettingsStore

    @property
    def settings(self) -> AgentSettings:
        return self.settings_store.load()


def make_harness(
    tmp_path: Path,
    *,
    settings: Optional[AgentSettings] = None,
    denied: Sequence[str] = (),
    valid_users: Sequence[str] = ("user_001",),
) -> Harness:
    suite = MockIntegrationSuite()
    checker = Checker(valid_users=valid_users, denied=denied)
    guard = PermissionGuard(checker)
    consent = ConsentManager(tmp_path / "consent.json")
    settings = settings or AgentSettings(
        enabled=True, provider_id="gemini", models={"gemini": "scripted-model"}
    )
    settings_store = InMemorySettingsStore(settings)
    runtime = build_runtime(
        integrations=AgentIntegrations(
            memories=suite.memories,
            people=suite.people,
            places=suite.places,
            activities=suite.activities,
            routines=suite.routines,
            reminders=suite.reminders,
            suggestions=suite.suggestions,
        ),
        guard=guard,
        consent=consent,
        settings_store=settings_store,
        key_manager=ApiKeyManager(InMemoryCredentialStore()),
        conversation_store=InMemoryConversationStore(),
        suggestion_store=InMemorySuggestionStore(),
    )
    return Harness(
        runtime=runtime,
        suite=suite,
        checker=checker,
        consent=consent,
        guard=guard,
        settings_store=settings_store,
    )


def tool_call(name: str, arguments: Optional[dict] = None, call_id: str = "call_1") -> ProviderResponse:
    return ProviderResponse(
        tool_calls=[ProviderToolRequest(id=call_id, name=name, arguments=arguments or {})],
        finish_reason=FinishReason.TOOL_CALLS,
        provider_id="gemini",
        model="scripted-model",
    )


def answer(text: str) -> ProviderResponse:
    return ProviderResponse(
        text=text, finish_reason=FinishReason.STOP, provider_id="gemini", model="scripted-model"
    )


class ScriptedProvider(AIProvider):
    """Deterministic provider. Each generate() advances the script."""

    info = ProviderInfo(
        id="gemini",
        label="Scripted Gemini",
        requires_api_key=False,
        supports_tools=True,
    )

    def __init__(self, script: Sequence[ProviderResponse] | Callable[[ProviderRequest, int], ProviderResponse]):
        self._script = script
        self.requests: list[ProviderRequest] = []
        self.closed = False

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        index = len(self.requests)
        self.requests.append(request)
        if callable(self._script):
            return self._script(request, index)
        return self._script[min(index, len(self._script) - 1)]

    def validate_api_key(self, api_key: Optional[str] = None) -> ConnectionTestResult:
        return ConnectionTestResult(ok=True, provider_id="gemini", message="scripted")

    def get_available_models(self) -> list[ModelInfo]:
        return [ModelInfo(id="scripted-model")]

    def close(self) -> None:
        self.closed = True


def ask(harness: Harness, provider: AIProvider, text: str = "Where did I keep my wallet?"):
    return harness.runtime.agent.ask(
        user_id="user_001",
        text=text,
        settings=harness.settings,
        provider=provider,
    )
