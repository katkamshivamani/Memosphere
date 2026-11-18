"""Provider registry: the only place that knows concrete provider classes."""

from __future__ import annotations

from typing import Callable, Optional

from memory_agent.core.exceptions import ConfigurationError
from memory_agent.providers.base import AIProvider
from memory_agent.providers.gemini import GeminiProvider
from memory_agent.providers.local import LocalProvider
from memory_agent.providers.openai import OpenAIProvider
from memory_agent.providers.schemas import ProviderInfo

ProviderFactory = Callable[..., AIProvider]

_FACTORIES: dict[str, ProviderFactory] = {
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
    "local": LocalProvider,
}

# Order matters only for UI presentation.
_SUPPORTED = ("gemini", "openai", "local")


def supported_provider_ids() -> list[str]:
    return list(_SUPPORTED)


def list_provider_info() -> list[ProviderInfo]:
    infos: list[ProviderInfo] = []
    for provider_id in _SUPPORTED:
        factory = _FACTORIES[provider_id]
        infos.append(factory.info)  # type: ignore[attr-defined]
    return infos


def get_provider_info(provider_id: str) -> ProviderInfo:
    factory = _FACTORIES.get(provider_id)
    if factory is None:
        raise ConfigurationError(
            f"Unknown AI provider: {provider_id!r}",
            user_message="The selected AI provider is not supported.",
        )
    return factory.info  # type: ignore[attr-defined]


def create_provider(
    provider_id: str,
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout_s: float = 45.0,
    client: object | None = None,
) -> AIProvider:
    """Instantiate a provider. Unknown ids are rejected, never guessed."""
    factory = _FACTORIES.get(provider_id)
    if factory is None:
        raise ConfigurationError(
            f"Unknown AI provider: {provider_id!r}",
            user_message="The selected AI provider is not supported.",
        )
    return factory(
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout_s=timeout_s,
        client=client,
    )


def register_provider(provider_id: str, factory: ProviderFactory) -> None:
    """Allow future providers (or test doubles) to be registered explicitly."""
    if not provider_id.strip():
        raise ValueError("provider_id must not be blank")
    _FACTORIES[provider_id] = factory
    if provider_id not in _SUPPORTED:
        _SUPPORTED.append(provider_id)  # type: ignore[arg-type]
