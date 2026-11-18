"""End-to-end host + agent integration smoke test (no network)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from memory_agent.core.exceptions import MissingApiKeyError
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
from memory_agent.security.api_key_manager import InMemoryCredentialStore
from memory_companion.composition import build_context
from memory_companion.config import AppPaths
from memory_companion.demo_data import ensure_demo_user


class ScriptedProvider(AIProvider):
    info = ProviderInfo(id="gemini", label="Scripted", requires_api_key=False)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        has_tool_results = any(m.role is ProviderRole.TOOL for m in request.messages)
        if request.tools and not has_tool_results:
            return ProviderResponse(
                tool_calls=[
                    ProviderToolRequest(
                        id="c1", name="search_memories", arguments={"query": "wallet"}
                    )
                ],
                finish_reason=FinishReason.TOOL_CALLS,
                provider_id="gemini",
            )
        return ProviderResponse(
            text="Your wallet is in the top drawer of the study desk.",
            provider_id="gemini",
            model="scripted",
        )

    def validate_api_key(self, api_key=None):
        return ConnectionTestResult(ok=True, provider_id="gemini", message="ok")

    def get_available_models(self):
        return [ModelInfo(id="scripted")]


def main() -> int:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        paths = AppPaths(data_dir=Path(tmp))
        ctx = build_context(paths=paths, credential_store=InMemoryCredentialStore())
        try:
            print("encryption:", ctx.encryption.describe())
            user_id, created = ensure_demo_user(ctx)
            print("demo user created:", created, user_id)

            settings = ctx.agent_runtime.settings_store.load().model_copy(
                update={"enabled": True, "provider_id": "gemini", "models": {"gemini": "scripted"}}
            )
            ctx.agent_runtime.settings_store.save(settings)

            try:
                ctx.agent_runtime.service.send_message(
                    user_id=user_id, text="Where did I keep my wallet?"
                )
                raise AssertionError("service must refuse without a stored API key")
            except MissingApiKeyError:
                print("service correctly refuses without an API key")

            conversation_id, turn = ctx.agent_runtime.agent.ask(
                user_id=user_id,
                text="Where did I keep my wallet?",
                settings=settings,
                provider=ScriptedProvider(),
            )
            print("conversation:", conversation_id)
            print("answer:", turn.text)
            print("grounding:", turn.evidence.grounding.value)
            print("sources:", [s.title for s in turn.evidence.sources])
            assert turn.evidence.grounding.value == "recorded"
            assert turn.tool_trace and turn.tool_trace[0].tool == "search_memories"

            stored = ctx.agent_runtime.conversations.store.list_messages(user_id, conversation_id)
            assert len(stored) == 2, [m.role for m in stored]
            print("conversation persisted in the encrypted database")

            allowed = ctx.auth.has_permission(user_id, "memory.read")
            assert allowed
            print("permissions:", len(ctx.auth.granted_permissions(user_id)), "granted")
        finally:
            ctx.close()
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
