"""Provider-independent AI interface.

The agent core only ever talks to :class:`AIProvider`.  Provider modules own all
vendor SDK usage and normalize every response into
:class:`~memory_agent.providers.schemas.ProviderResponse`.

Contract
--------
``generate(request)`` receives a complete, already-authorized request.  It must
not add tools, widen context or retry indefinitely.  ``validate_api_key()`` must
perform a real remote check and report failures honestly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from memory_agent.providers.schemas import (
    ConnectionTestResult,
    ModelInfo,
    ProviderInfo,
    ProviderRequest,
    ProviderResponse,
)


class AIProvider(ABC):
    """Base class for every AI backend (cloud or local)."""

    info: ProviderInfo

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        client: object | None = None,
    ) -> None:
        self._api_key = api_key or None
        self._model = model or self.info.default_model
        self._base_url = base_url
        self._client = client

    # ------------------------------------------------------------------ #
    # Identity / capability
    # ------------------------------------------------------------------ #
    @property
    def provider_id(self) -> str:
        return self.info.id

    @property
    def is_local(self) -> bool:
        return self.info.is_local

    @property
    def model(self) -> Optional[str]:
        return self._model

    def is_configured(self) -> bool:
        """True when the provider has everything needed to attempt a request."""
        if self.info.is_local:
            return bool(self._base_url)
        return bool(self._api_key)

    # ------------------------------------------------------------------ #
    # Required operations
    # ------------------------------------------------------------------ #
    @abstractmethod
    def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Run one model round-trip and return a normalized response."""

    @abstractmethod
    def validate_api_key(self, api_key: Optional[str] = None) -> ConnectionTestResult:
        """Perform a real connectivity/credential check."""

    @abstractmethod
    def get_available_models(self) -> list[ModelInfo]:
        """Return models usable for chat/tool calling."""

    # ------------------------------------------------------------------ #
    # Optional operations
    # ------------------------------------------------------------------ #
    def close(self) -> None:
        """Release SDK resources. Safe to call more than once."""
        self._client = None

    def __repr__(self) -> str:  # never include credentials
        return f"<{type(self).__name__} provider={self.provider_id} model={self._model}>"
