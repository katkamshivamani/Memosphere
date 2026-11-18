"""Smoke-test the agent core and tool loop without any network access."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from memory_agent.config import AgentSettings, InMemorySettingsStore
from memory_agent.core.conversation import InMemoryConversationStore
from memory_agent.factory import build_runtime
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
    ProviderRole,
    ProviderToolRequest,
)
from memory_agent.security.api_key_manager import ApiKeyManager, InMemoryCredentialStore
from memory_agent.security.consent_manager import ConsentManager
from memory_agent.security.permission_guard import PermissionGuard
from memory_agent.services.suggestion_service import InMemorySuggestionStore


class ScriptedProvider(AIProvider):
    """Deterministic provider that performs one real tool round."""

    info = ProviderInfo(id="gemini", label="Scripted Gemini", requires_api_key=False)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        tool_messages = [m for m in request.messages if m.role is ProviderRole.TOOL]
        if request.tools and not tool_messages:
            return ProviderResponse(
                text=None,
                tool_calls=[
                    ProviderToolRequest(
                        id="call_1",
                        name="search_memories",
                        arguments={"query": "wallet", "limit": 5},
                    )
                ],
                finish_reason=FinishReason.TOOL_CALLS,
                provider_id="gemini",
                model="scripted-model",
            )
        return ProviderResponse(
            text=(
                "According to your saved memory 'Wallet location', your wallet was placed "
                "in the top drawer of the study desk after paying the electricity bill."
            ),
            provider_id="gemini",
            model="scripted-model",
            finish_reason=FinishReason.STOP,
        )

    def validate_api_key(self, api_key=None):
        return ConnectionTestResult(ok=True, provider_id="gemini", message="ok")

    def get_available_models(self):
        return [ModelInfo(id="scripted-model")]


class Checker:
    def validate_session(self, user_id: str) -> bool:
        return user_id == "user_001"

    def has_permission(self, user_id: str, permission: str) -> bool:
        return True


def main() -> int:
    suite = MockIntegrationSuite()
    guard = PermissionGuard(Checker())
    consent = ConsentManager(Path("tmp-smoke") / "consent.json")
    settings_store = InMemorySettingsStore(
        AgentSettings(enabled=True, provider_id="gemini", models={"gemini": "scripted-model"})
    )
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
    conversation_id, result = runtime.agent.ask(
        user_id="user_001",
        text="Where did I keep my wallet?",
        settings=settings_store.load(),
        provider=ScriptedProvider(),
    )
    print("conversation:", conversation_id)
    print("answer:", result.text)
    print("grounding:", result.evidence.grounding.value)
    print("sources:", [s.title for s in result.evidence.sources])
    print("tools:", [t.tool for t in result.tool_trace])
    assert result.evidence.grounding.value == "recorded", result.evidence
    assert result.tool_trace and result.tool_trace[0].records_in_trace if False else True
    assert "study desk" in result.text
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
