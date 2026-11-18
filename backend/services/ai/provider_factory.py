"""
MEMOSPHERE AI Provider Factory
Instantiates the selected external AI provider (Groq, NVIDIA NIM, Gemini or OpenAI)
based on environment configuration without requiring all keys to be set.
"""
from config import Config
from backend.services.ai.ai_client import BaseAIProvider, AIProviderError
from backend.services.ai.groq_provider import GroqProvider
from backend.services.ai.nvidia_nim_provider import NvidiaNimProvider
from backend.services.ai.gemini_provider import GeminiProvider
from backend.services.ai.openai_provider import OpenAIProvider


class ProviderFactory:
    """Factory for creating provider-specific AI clients from environment configuration."""

    PROVIDERS = {
        "groq": GroqProvider,
        "nvidia_nim": NvidiaNimProvider,
        "gemini": GeminiProvider,
        "openai": OpenAIProvider,
    }

    @classmethod
    def supported_providers(cls) -> list[str]:
        return list(cls.PROVIDERS.keys())

    @classmethod
    def create_provider(
        cls,
        provider_name: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> BaseAIProvider:
        selected = (provider_name or Config.get_ai_provider() or "groq").strip().lower()
        if selected not in cls.PROVIDERS:
            raise AIProviderError(
                "Unsupported AI_PROVIDER '{}'. Supported providers: {}.".format(
                    selected, ", ".join(cls.supported_providers())
                ),
                error_code="unsupported_provider",
                status_code=400,
            )

        provider_cls = cls.PROVIDERS[selected]
        resolved_key = api_key if api_key is not None else Config.get_api_key(selected)
        resolved_model = model if model is not None else Config.get_ai_model(selected)
        resolved_timeout = timeout if timeout is not None else Config.get_timeout()

        return provider_cls(
            api_key=resolved_key,
            model=resolved_model,
            timeout=resolved_timeout,
        )
