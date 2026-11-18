"""Google Gemini provider (first operational provider).

Free-tier friendly and model-configurable: the default model comes from
:class:`~memory_agent.config.AgentSettings`, and the live model list is always
available through ``get_available_models``.  Nothing here is assumed to be
current forever; if a configured model disappears the provider reports
``UnsupportedModelError`` rather than silently switching.
"""

from __future__ import annotations

import json
import time
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
    ProviderMessage,
    ProviderRequest,
    ProviderResponse,
    ProviderRole,
    ProviderToolRequest,
    Usage,
)

DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com"


class GeminiProvider(AIProvider):
    """Gemini implementation using the official ``google-genai`` SDK."""

    info = ProviderInfo(
        id="gemini",
        label="Google Gemini",
        is_local=False,
        requires_api_key=True,
        supports_tools=True,
        supports_streaming=False,
        supports_audio_transcription=True,
        default_model=None,
        documentation_url="https://ai.google.dev/gemini-api/docs",
        notes="Free tier available. Model list is fetched live; no model id is hardcoded.",
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

    # ------------------------------------------------------------------ #
    # SDK plumbing
    # ------------------------------------------------------------------ #
    def _build_client(self, api_key: Optional[str] = None) -> Any:
        key = api_key or self._api_key
        if not key:
            raise MissingApiKeyError("Gemini API key is not configured.")
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - dependency installed
            raise ProviderError(
                f"google-genai is not installed: {exc}",
                user_message="The Gemini library is not installed in this application.",
            ) from exc
        return genai.Client(
            api_key=key,
            http_options=types.HttpOptions(
                base_url=self._base_url or DEFAULT_GEMINI_BASE_URL,
                timeout=int(self._timeout_s * 1000),
            ),
        )

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    # ------------------------------------------------------------------ #
    # Request conversion
    # ------------------------------------------------------------------ #
    @staticmethod
    def _convert_message(message: ProviderMessage, types: Any) -> Any:
        parts: list[Any] = []
        if message.text:
            parts.append(types.Part(text=message.text))
        for call in message.tool_calls:
            parts.append(
                types.Part(
                    function_call=types.FunctionCall(name=call.name, args=call.arguments or {})
                )
            )
        for result in message.tool_results:
            try:
                response_payload = json.loads(result.content)
            except (TypeError, ValueError):
                response_payload = {"result": result.content}
            if not isinstance(response_payload, dict):
                response_payload = {"result": response_payload}
            if result.is_error:
                response_payload = {"error": response_payload}
            parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=result.name,
                        response=response_payload,
                    )
                )
            )
        if not parts:
            parts.append(types.Part(text=""))
        role = "model" if message.role is ProviderRole.ASSISTANT else "user"
        return types.Content(role=role, parts=parts)

    def _build_config(self, request: ProviderRequest, types: Any) -> Any:
        kwargs: dict[str, Any] = {
            "temperature": request.temperature,
        }
        if request.system_instruction:
            kwargs["system_instruction"] = request.system_instruction
        if request.max_output_tokens:
            kwargs["max_output_tokens"] = request.max_output_tokens
        if request.tools:
            declarations = []
            for spec in request.tools:
                declarations.append(
                    types.FunctionDeclaration(
                        name=spec["name"],
                        description=spec.get("description", ""),
                        parameters_json_schema=spec.get("parameters") or {"type": "object"},
                    )
                )
            kwargs["tools"] = [types.Tool(function_declarations=declarations)]
        return types.GenerateContentConfig(**kwargs)

    # ------------------------------------------------------------------ #
    # Error mapping
    # ------------------------------------------------------------------ #
    @staticmethod
    def _map_error(exc: Exception) -> ProviderError:
        try:
            from google.genai import errors as genai_errors
        except ImportError:  # pragma: no cover
            genai_errors = None  # type: ignore[assignment]

        code = getattr(exc, "code", None)
        text = (str(exc) or "").lower()

        if isinstance(exc, (TimeoutError,)) or "timeout" in text or "timed out" in text:
            return ProviderTimeoutError(f"Gemini request timed out: {exc}", details={"code": code})

        if genai_errors is not None and isinstance(exc, genai_errors.APIError):
            if code in (401, 403) or "api key" in text or "unauthenticated" in text:
                return ProviderAuthError(f"Gemini rejected the API key ({code}).")
            if code == 429 or "rate limit" in text or "quota" in text:
                return ProviderRateLimitError(f"Gemini rate limit ({code}).")
            if code == 404 or "not found" in text or "not supported" in text:
                return UnsupportedModelError(f"Gemini model unavailable ({code}).")
            if code is not None and int(code) >= 500:
                return ProviderUnavailableError(f"Gemini server error ({code}).")
            if code == 400:
                return ProviderError(f"Gemini rejected the request ({code}).")
            return ProviderError(f"Gemini API error ({code}).")

        if isinstance(exc, (ConnectionError, OSError)):
            return ProviderNetworkError(f"Network error contacting Gemini: {exc}")
        return ProviderError(f"Unexpected Gemini error: {exc}")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def generate(self, request: ProviderRequest) -> ProviderResponse:
        try:
            from google.genai import types
        except ImportError as exc:  # pragma: no cover
            raise ProviderError(f"google-genai is not installed: {exc}") from exc

        client = self._get_client()
        model = request.model or self._model
        if not model:
            raise UnsupportedModelError(
                "No Gemini model is configured.",
                user_message="No AI model is selected. Choose one in Assistant settings.",
            )

        contents = [self._convert_message(m, types) for m in request.messages]
        config = self._build_config(request, types)

        started = time.monotonic()
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as exc:  # mapped below; never leak raw exception to UI
            raise self._map_error(exc) from exc

        elapsed_ms = int((time.monotonic() - started) * 1000)
        return self._normalize(response, model=model, elapsed_ms=elapsed_ms)

    @staticmethod
    def _normalize(response: Any, *, model: str, elapsed_ms: int) -> ProviderResponse:
        candidates = getattr(response, "candidates", None) or []
        text_parts: list[str] = []
        tool_calls: list[ProviderToolRequest] = []
        finish_raw: Optional[str] = None

        if candidates:
            candidate = candidates[0]
            raw_finish = getattr(candidate, "finish_reason", None)
            finish_raw = getattr(raw_finish, "name", None) or (
                str(raw_finish) if raw_finish is not None else None
            )
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            for index, part in enumerate(parts):
                part_text = getattr(part, "text", None)
                if part_text:
                    text_parts.append(part_text)
                function_call = getattr(part, "function_call", None)
                if function_call is not None:
                    name = getattr(function_call, "name", None)
                    if not name:
                        raise ProviderResponseError("Gemini returned a tool call without a name.")
                    raw_args = getattr(function_call, "args", None) or {}
                    try:
                        arguments = dict(raw_args)
                    except (TypeError, ValueError) as exc:
                        raise ProviderResponseError(
                            f"Gemini returned non-object tool arguments: {exc}"
                        ) from exc
                    call_id = getattr(function_call, "id", None) or f"gemini_call_{index + 1}"
                    tool_calls.append(
                        ProviderToolRequest(id=str(call_id), name=str(name), arguments=arguments)
                    )

        usage = None
        raw_usage = getattr(response, "usage_metadata", None)
        if raw_usage is not None:
            usage = Usage(
                input_tokens=getattr(raw_usage, "prompt_token_count", None),
                output_tokens=getattr(raw_usage, "candidates_token_count", None),
                total_tokens=getattr(raw_usage, "total_token_count", None),
            )

        finish = FinishReason.UNKNOWN
        if tool_calls:
            finish = FinishReason.TOOL_CALLS
        elif finish_raw == "STOP":
            finish = FinishReason.STOP
        elif finish_raw == "MAX_TOKENS":
            finish = FinishReason.MAX_TOKENS
        elif finish_raw in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"):
            finish = FinishReason.SAFETY

        text = "\n".join(part for part in text_parts if part).strip() or None
        if not text and not tool_calls:
            blocked = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
            if blocked:
                raise ProviderResponseError(
                    f"Gemini blocked the request ({blocked}).",
                    user_message="The AI provider declined to answer that request.",
                )
            raise ProviderResponseError(
                "Gemini returned an empty response.",
                user_message="The AI provider returned an empty answer. Please try again.",
            )

        return ProviderResponse(
            text=text,
            tool_calls=tool_calls,
            usage=usage,
            finish_reason=finish,
            model=model,
            provider_id="gemini",
            raw_finish_reason=finish_raw,
        )

    def validate_api_key(self, api_key: Optional[str] = None) -> ConnectionTestResult:
        try:
            client = self._build_client(api_key)
            models: list[str] = []
            for model in client.models.list():
                name = (getattr(model, "name", "") or "").removeprefix("models/")
                if name:
                    models.append(name)
                if len(models) >= 25:
                    break
            if not models:
                return ConnectionTestResult(
                    ok=False,
                    provider_id=self.provider_id,
                    model=self._model,
                    message="The API key was accepted but no models were returned.",
                )
            return ConnectionTestResult(
                ok=True,
                provider_id=self.provider_id,
                model=self._model,
                message="Connected to Google Gemini.",
                available_models=models,
            )
        except Exception as exc:
            mapped = self._map_error(exc)
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
            raise self._map_error(exc) from exc

        usable: list[ModelInfo] = []
        for model in models:
            name = (getattr(model, "name", "") or "").removeprefix("models/")
            if not name:
                continue
            if any(word in name for word in ("embedding", "aqa", "imagen", "veo", "tts")):
                continue
            actions = getattr(model, "supported_actions", None) or []
            if actions and "generateContent" not in actions:
                continue
            usable.append(
                ModelInfo(
                    id=name,
                    label=getattr(model, "display_name", None) or name,
                    supports_tools=True,
                )
            )
        return usable
