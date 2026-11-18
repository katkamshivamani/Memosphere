"""OpenAI provider plus shared OpenAI-compatible conversion helpers.

The helpers are reused by the local provider (Ollama / LM Studio expose an
OpenAI-compatible chat completions API), which keeps response normalization in
one place.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from memory_agent.core.exceptions import (
    MissingApiKeyError,
    ProviderAuthError,
    ProviderError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UnsupportedModelError,
)
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
    Usage,
)


# --------------------------------------------------------------------------- #
# Shared conversion helpers
# --------------------------------------------------------------------------- #
def to_openai_messages(request: ProviderRequest) -> list[dict[str, Any]]:
    """Convert neutral messages to OpenAI chat-completions message dicts."""
    messages: list[dict[str, Any]] = []
    if request.system_instruction:
        messages.append({"role": "system", "content": request.system_instruction})

    for message in request.messages:
        if message.role is ProviderRole.ASSISTANT:
            entry: dict[str, Any] = {"role": "assistant"}
            entry["content"] = message.text or ""
            if message.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments or {}, ensure_ascii=False),
                        },
                    }
                    for call in message.tool_calls
                ]
            messages.append(entry)
        elif message.role is ProviderRole.TOOL:
            for result in message.tool_results:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": result.tool_call_id,
                        "content": result.content,
                    }
                )
        else:
            messages.append({"role": message.role.value, "content": message.text or ""})
    return messages


def to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": spec["name"],
                "description": spec.get("description", ""),
                "parameters": spec.get("parameters") or {"type": "object", "properties": {}},
            },
        }
        for spec in tools
    ]


def normalize_openai_payload(
    payload: dict[str, Any], *, provider_id: str, model: str
) -> ProviderResponse:
    """Normalize a chat-completions JSON payload to :class:`ProviderResponse`."""
    choices = payload.get("choices") or []
    if not choices:
        raise ProviderResponseError(
            "Provider returned no choices.",
            user_message="The AI provider returned an empty answer. Please try again.",
        )
    choice = choices[0]
    message = choice.get("message") or {}
    text = message.get("content")
    if isinstance(text, list):  # some compatible servers return content parts
        text = "".join(part.get("text", "") for part in text if isinstance(part, dict))
    text = (text or "").strip() or None

    tool_calls: list[ProviderToolRequest] = []
    for index, raw_call in enumerate(message.get("tool_calls") or []):
        function = raw_call.get("function") or {}
        name = function.get("name")
        if not name:
            raise ProviderResponseError("Provider returned a tool call without a name.")
        raw_args = function.get("arguments") or "{}"
        if isinstance(raw_args, dict):
            arguments = raw_args
        else:
            try:
                arguments = json.loads(raw_args)
            except (TypeError, ValueError) as exc:
                raise ProviderResponseError(
                    f"Provider returned malformed tool arguments: {exc}"
                ) from exc
        if not isinstance(arguments, dict):
            raise ProviderResponseError("Provider returned non-object tool arguments.")
        tool_calls.append(
            ProviderToolRequest(
                id=str(raw_call.get("id") or f"{provider_id}_call_{index + 1}"),
                name=str(name),
                arguments=arguments,
            )
        )

    usage = None
    raw_usage = payload.get("usage") or {}
    if raw_usage:
        usage = Usage(
            input_tokens=raw_usage.get("prompt_tokens"),
            output_tokens=raw_usage.get("completion_tokens"),
            total_tokens=raw_usage.get("total_tokens"),
        )

    finish_raw = choice.get("finish_reason")
    finish = FinishReason.UNKNOWN
    if tool_calls or finish_raw == "tool_calls":
        finish = FinishReason.TOOL_CALLS
    elif finish_raw == "stop":
        finish = FinishReason.STOP
    elif finish_raw == "length":
        finish = FinishReason.MAX_TOKENS
    elif finish_raw == "content_filter":
        finish = FinishReason.SAFETY

    if not text and not tool_calls:
        raise ProviderResponseError(
            "Provider returned an empty response.",
            user_message="The AI provider returned an empty answer. Please try again.",
        )

    return ProviderResponse(
        text=text,
        tool_calls=tool_calls,
        usage=usage,
        finish_reason=finish,
        model=payload.get("model") or model,
        provider_id=provider_id,
        raw_finish_reason=str(finish_raw) if finish_raw else None,
    )


def map_common_http_error(status: Optional[int], text: str, provider_label: str) -> ProviderError:
    lowered = (text or "").lower()
    if status in (401, 403) or "api key" in lowered or "unauthorized" in lowered:
        return ProviderAuthError(f"{provider_label} rejected the credentials ({status}).")
    if status == 429 or "rate limit" in lowered:
        return ProviderRateLimitError(f"{provider_label} rate limited the request.")
    if status == 404 or "model" in lowered and "not found" in lowered:
        return UnsupportedModelError(f"{provider_label} model not found ({status}).")
    if status is not None and status >= 500:
        return ProviderUnavailableError(f"{provider_label} server error ({status}).")
    if status == 400:
        return ProviderError(f"{provider_label} rejected the request ({status}).")
    return ProviderError(f"{provider_label} request failed ({status}).")


# --------------------------------------------------------------------------- #
# OpenAI provider
# --------------------------------------------------------------------------- #
class OpenAIProvider(AIProvider):
    info = ProviderInfo(
        id="openai",
        label="OpenAI",
        is_local=False,
        requires_api_key=True,
        supports_tools=True,
        supports_streaming=False,
        supports_audio_transcription=False,
        default_model=None,
        documentation_url="https://platform.openai.com/docs",
        notes="Paid API. Model list is fetched live from the account.",
    )

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        client: object | None = None,
        timeout_s: float = 45.0,
    ) -> None:
        super().__init__(api_key, model=model, base_url=base_url, client=client)
        self._timeout_s = timeout_s

    def _build_client(self, api_key: Optional[str] = None) -> Any:
        key = api_key or self._api_key
        if not key:
            raise MissingApiKeyError("OpenAI API key is not configured.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ProviderError(
                f"openai is not installed: {exc}",
                user_message="The OpenAI library is not installed in this application.",
            ) from exc
        kwargs: dict[str, Any] = {"api_key": key, "timeout": self._timeout_s}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return OpenAI(**kwargs)

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _map_sdk_error(self, exc: Exception) -> ProviderError:
        status = getattr(exc, "status_code", None)
        name = type(exc).__name__
        text = str(exc)
        if name in ("APITimeoutError", "TimeoutError") or "timed out" in text.lower():
            return ProviderTimeoutError(f"OpenAI request timed out: {text}")
        if name in ("APIConnectionError", "ConnectError"):
            return ProviderNetworkError(f"Network error contacting OpenAI: {text}")
        if name in ("RateLimitError",):
            return ProviderRateLimitError(f"OpenAI rate limited the request: {text}")
        if name in ("AuthenticationError", "PermissionDeniedError"):
            return ProviderAuthError(f"OpenAI rejected the API key: {text}")
        if name in ("NotFoundError",):
            return UnsupportedModelError(f"OpenAI model not found: {text}")
        if name in ("BadRequestError",):
            return ProviderError(f"OpenAI rejected the request: {text}")
        if name in ("InternalServerError",):
            return ProviderUnavailableError(f"OpenAI server error: {text}")
        if status:
            return map_common_http_error(int(status), text, "OpenAI")
        return ProviderError(f"Unexpected OpenAI error: {text}")

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        client = self._get_client()
        model = request.model or self._model
        if not model:
            raise UnsupportedModelError(
                "No OpenAI model is configured.",
                user_message="No AI model is selected. Choose one in Assistant settings.",
            )
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": to_openai_messages(request),
            "temperature": request.temperature,
        }
        if request.max_output_tokens:
            kwargs["max_tokens"] = request.max_output_tokens
        if request.tools:
            kwargs["tools"] = to_openai_tools(request.tools)
            kwargs["tool_choice"] = "auto"
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise self._map_sdk_error(exc) from exc

        payload = response.model_dump() if hasattr(response, "model_dump") else dict(response)
        return normalize_openai_payload(payload, provider_id="openai", model=model)

    def validate_api_key(self, api_key: Optional[str] = None) -> ConnectionTestResult:
        try:
            client = self._build_client(api_key)
            ids: list[str] = []
            for model in client.models.list():
                model_id = getattr(model, "id", None)
                if model_id:
                    ids.append(str(model_id))
                if len(ids) >= 50:
                    break
            return ConnectionTestResult(
                ok=True,
                provider_id=self.provider_id,
                model=self._model,
                message="Connected to OpenAI.",
                available_models=ids,
            )
        except Exception as exc:
            mapped = self._map_sdk_error(exc)
            return ConnectionTestResult(
                ok=False,
                provider_id=self.provider_id,
                model=self._model,
                message=mapped.user_message,
            )

    def get_available_models(self) -> list[ModelInfo]:
        client = self._get_client()
        try:
            models = list(client.models.list())
        except Exception as exc:
            raise self._map_sdk_error(exc) from exc
        result = []
        for model in models:
            model_id = str(getattr(model, "id", "") or "")
            if not model_id:
                continue
            if any(word in model_id for word in ("embedding", "whisper", "tts", "dall-e", "moderation")):
                continue
            result.append(ModelInfo(id=model_id, label=model_id, supports_tools=True))
        return result
