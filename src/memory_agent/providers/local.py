"""Local provider adapter (Ollama / LM Studio / any OpenAI-compatible server).

This is a real implementation, not a placeholder: it talks HTTP to a locally
running OpenAI-compatible endpoint.  Because it is local, it is the only
provider that may be used in Context Mode C (``local_only``) - see
:mod:`memory_agent.core.context_builder`.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from memory_agent.core.exceptions import (
    ProviderNetworkError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UnsupportedModelError,
)
from memory_agent.providers.base import AIProvider
from memory_agent.providers.openai import (
    map_common_http_error,
    normalize_openai_payload,
    to_openai_messages,
    to_openai_tools,
)
from memory_agent.providers.schemas import (
    ConnectionTestResult,
    ModelInfo,
    ProviderInfo,
    ProviderRequest,
    ProviderResponse,
)

DEFAULT_LOCAL_BASE_URL = "http://127.0.0.1:11434/v1"


class LocalProvider(AIProvider):
    """OpenAI-compatible local endpoint (Ollama, LM Studio, llama.cpp server)."""

    info = ProviderInfo(
        id="local",
        label="Local model (OpenAI-compatible)",
        is_local=True,
        requires_api_key=False,
        supports_tools=True,
        supports_streaming=False,
        supports_audio_transcription=False,
        default_model=None,
        documentation_url="https://github.com/ollama/ollama/blob/main/docs/openai.md",
        notes=(
            "Runs entirely on this computer. Works with Ollama, LM Studio or any "
            "server exposing /v1/chat/completions."
        ),
    )

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        client: httpx.Client | None = None,
        timeout_s: float = 90.0,
    ) -> None:
        super().__init__(api_key, model=model, base_url=base_url or DEFAULT_LOCAL_BASE_URL, client=client)
        self._timeout_s = timeout_s

    @property
    def base_url(self) -> str:
        return (self._base_url or DEFAULT_LOCAL_BASE_URL).rstrip("/")

    def _http(self, timeout: Optional[float] = None) -> httpx.Client:
        if self._client is not None:
            return self._client  # type: ignore[return-value]
        return httpx.Client(timeout=timeout or self._timeout_s)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def is_configured(self) -> bool:
        return bool(self._base_url)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        model = request.model or self._model
        if not model:
            raise UnsupportedModelError(
                "No local model is configured.",
                user_message="Choose the name of a model served by your local runtime.",
            )
        payload: dict[str, Any] = {
            "model": model,
            "messages": to_openai_messages(request),
            "temperature": request.temperature,
            "stream": False,
        }
        if request.max_output_tokens:
            payload["max_tokens"] = request.max_output_tokens
        if request.tools:
            payload["tools"] = to_openai_tools(request.tools)

        client = self._http()
        try:
            response = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=request.timeout_s or self._timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"Local provider timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderNetworkError(
                f"Cannot reach local provider at {self.base_url}: {exc}",
                user_message=(
                    "Could not reach the local model server. Start it (for example "
                    "Ollama) and check the address in Assistant settings."
                ),
            ) from exc

        if response.status_code >= 400:
            raise map_common_http_error(response.status_code, response.text, "Local provider")
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderResponseError(f"Local provider returned invalid JSON: {exc}") from exc
        return normalize_openai_payload(data, provider_id="local", model=model)

    def validate_api_key(self, api_key: Optional[str] = None) -> ConnectionTestResult:
        try:
            client = self._http()
            response = client.get(f"{self.base_url}/models", timeout=10.0)
            if response.status_code >= 400:
                mapped = map_common_http_error(response.status_code, response.text, "Local provider")
                return ConnectionTestResult(
                    ok=False, provider_id=self.provider_id, model=self._model, message=mapped.user_message
                )
            data = response.json()
            ids = [item.get("id") for item in data.get("data", []) if item.get("id")]
            return ConnectionTestResult(
                ok=True,
                provider_id=self.provider_id,
                model=self._model,
                message="Connected to local model server.",
                available_models=ids,
            )
        except Exception as exc:
            return ConnectionTestResult(
                ok=False,
                provider_id=self.provider_id,
                model=self._model,
                message=(
                    "Could not reach the local model server. Start it and verify the "
                    "address in Assistant settings."
                ),
            )

    def get_available_models(self) -> list[ModelInfo]:
        try:
            response = self._http().get(f"{self.base_url}/models", timeout=10.0)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"Local model list unavailable: {exc}") from exc
        models = []
        for item in data.get("data", []):
            model_id = item.get("id")
            if model_id:
                models.append(ModelInfo(id=str(model_id), label=str(model_id)))
        return models
