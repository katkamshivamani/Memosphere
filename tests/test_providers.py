"""Provider abstraction: registry, conversion, normalization and errors.

No network access happens here.  Vendor SDK clients are injected fakes or
``httpx.MockTransport`` instances, so this suite runs offline.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from memory_agent.config import AgentSettings
from memory_agent.core.exceptions import (
    ConfigurationError,
    MissingApiKeyError,
    ProviderError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UnsupportedModelError,
)
from memory_agent.providers.gemini import GeminiProvider
from memory_agent.providers.local import LocalProvider
from memory_agent.providers.openai import (
    OpenAIProvider,
    map_common_http_error,
    normalize_openai_payload,
    to_openai_messages,
    to_openai_tools,
)
from memory_agent.providers.registry import (
    create_provider,
    get_provider_info,
    list_provider_info,
    register_provider,
    supported_provider_ids,
)
from memory_agent.providers.schemas import (
    FinishReason,
    ProviderMessage,
    ProviderRequest,
    ProviderRole,
    ProviderToolRequest,
    ToolResultPayload,
)


def _user_request(text: str = "Where is my wallet?", **kwargs) -> ProviderRequest:
    return ProviderRequest(
        messages=[ProviderMessage(role=ProviderRole.USER, text=text)],
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def test_registry_exposes_the_three_providers():
    assert supported_provider_ids() == ["gemini", "openai", "local"]
    infos = {info.id: info for info in list_provider_info()}
    assert infos["gemini"].requires_api_key is True
    assert infos["local"].is_local is True
    assert infos["local"].requires_api_key is False


def test_unknown_provider_is_rejected_not_guessed():
    with pytest.raises(ConfigurationError):
        get_provider_info("mystery-ai")
    with pytest.raises(ConfigurationError):
        create_provider("mystery-ai", api_key="x" * 32)


def test_register_provider_validates_blank_ids():
    with pytest.raises(ValueError):
        register_provider("   ", GeminiProvider)


def test_default_model_is_never_hardcoded_for_cloud_providers():
    for provider_id in ("gemini", "openai"):
        assert get_provider_info(provider_id).default_model is None


def test_settings_accept_every_supported_provider():
    for provider_id in supported_provider_ids():
        settings = AgentSettings(provider_id=provider_id)
        assert settings.provider_id == provider_id


# --------------------------------------------------------------------------- #
# OpenAI-compatible conversion helpers
# --------------------------------------------------------------------------- #
def test_openai_message_conversion_handles_text_tools_and_results():
    request = ProviderRequest(
        system_instruction="Be careful.",
        messages=[
            ProviderMessage(role=ProviderRole.USER, text="Where is my wallet?"),
            ProviderMessage(
                role=ProviderRole.ASSISTANT,
                text="Let me check.",
                tool_calls=[
                    ProviderToolRequest(
                        id="call_1", name="search_memories", arguments={"query": "wallet"}
                    )
                ],
            ),
            ProviderMessage(
                role=ProviderRole.TOOL,
                tool_results=[
                    ToolResultPayload(
                        tool_call_id="call_1",
                        name="search_memories",
                        content=json.dumps({"ok": True}),
                    )
                ],
            ),
        ],
    )
    converted = to_openai_messages(request)

    assert converted[0] == {"role": "system", "content": "Be careful."}
    assert converted[1] == {"role": "user", "content": "Where is my wallet?"}
    assert converted[2]["role"] == "assistant"
    call = converted[2]["tool_calls"][0]
    assert call["id"] == "call_1"
    assert json.loads(call["function"]["arguments"]) == {"query": "wallet"}
    assert converted[3] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": json.dumps({"ok": True}),
    }


def test_openai_tool_conversion_uses_json_schema():
    tools = to_openai_tools(
        [
            {
                "name": "search_memories",
                "description": "Search memories",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            }
        ]
    )
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["name"] == "search_memories"
    assert tools[0]["function"]["parameters"]["properties"]["query"]["type"] == "string"


def test_openai_payload_normalization_text_and_usage():
    response = normalize_openai_payload(
        {
            "model": "gpt-test",
            "choices": [
                {
                    "message": {"content": "  The wallet is in the drawer. "},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
        provider_id="openai",
        model="gpt-test",
    )
    assert response.text == "The wallet is in the drawer."
    assert response.finish_reason is FinishReason.STOP
    assert response.usage is not None and response.usage.total_tokens == 15
    assert response.provider_id == "openai"


def test_openai_payload_normalization_tool_calls():
    response = normalize_openai_payload(
        {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_9",
                                "function": {
                                    "name": "search_memories",
                                    "arguments": '{"query": "passport"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        },
        provider_id="local",
        model="llama-test",
    )
    assert response.finish_reason is FinishReason.TOOL_CALLS
    assert response.tool_calls[0].name == "search_memories"
    assert response.tool_calls[0].arguments == {"query": "passport"}


def test_openai_payload_rejects_malformed_tool_arguments():
    with pytest.raises(ProviderResponseError):
        normalize_openai_payload(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {"id": "c", "function": {"name": "x", "arguments": "not-json"}}
                            ]
                        }
                    }
                ]
            },
            provider_id="openai",
            model="m",
        )


def test_openai_payload_rejects_empty_and_non_object_arguments():
    with pytest.raises(ProviderResponseError):
        normalize_openai_payload({"choices": []}, provider_id="openai", model="m")
    with pytest.raises(ProviderResponseError):
        normalize_openai_payload(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {"id": "c", "function": {"name": "x", "arguments": "[1, 2]"}}
                            ]
                        }
                    }
                ]
            },
            provider_id="openai",
            model="m",
        )


def test_http_error_mapping_is_specific():
    assert isinstance(map_common_http_error(401, "", "X"), ProviderError)
    assert "auth" in map_common_http_error(401, "", "X").code
    assert isinstance(map_common_http_error(429, "", "X"), ProviderRateLimitError)
    assert isinstance(map_common_http_error(404, "model not found", "X"), UnsupportedModelError)
    assert isinstance(map_common_http_error(503, "", "X"), ProviderUnavailableError)
    assert map_common_http_error(400, "", "X").code == "provider_error"


# --------------------------------------------------------------------------- #
# OpenAI provider with a fake SDK client
# --------------------------------------------------------------------------- #
class _FakeOpenAICompletions:
    def __init__(self, payload):
        self._payload = payload
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(model_dump=lambda: self._payload)


class _FakeOpenAIClient:
    def __init__(self, payload=None):
        self.chat = SimpleNamespace(completions=_FakeOpenAICompletions(payload or {}))


def test_openai_provider_generates_with_injected_client():
    payload = {
        "model": "gpt-test",
        "choices": [{"message": {"content": "Ready."}, "finish_reason": "stop"}],
    }
    client = _FakeOpenAIClient(payload)
    provider = OpenAIProvider(api_key="sk-test-key-1234567890", model="gpt-test", client=client)

    response = provider.generate(_user_request())

    assert response.text == "Ready."
    sent = client.chat.completions.calls[0]
    assert sent["model"] == "gpt-test"
    assert sent["messages"][0]["role"] == "user"


def test_openai_requires_api_key_before_use():
    provider = OpenAIProvider(model="gpt-test")
    with pytest.raises(MissingApiKeyError):
        provider.generate(_user_request())


def test_openai_requires_a_model():
    provider = OpenAIProvider(api_key="sk-test-key-1234567890", client=_FakeOpenAIClient())
    with pytest.raises(UnsupportedModelError):
        provider.generate(ProviderRequest(messages=_user_request().messages))


def test_provider_repr_never_contains_the_key():
    provider = OpenAIProvider(api_key="sk-super-secret-key-value", model="gpt-test")
    assert "sk-super-secret" not in repr(provider)


# --------------------------------------------------------------------------- #
# Gemini normalization (SDK types are real; the response is a fake)
# --------------------------------------------------------------------------- #
def _gemini_response(text: str):
    part = SimpleNamespace(text=text, function_call=None)
    candidate = SimpleNamespace(
        content=SimpleNamespace(parts=[part]),
        finish_reason=SimpleNamespace(name="STOP"),
    )
    return SimpleNamespace(candidates=[candidate], usage_metadata=None)


def test_gemini_normalization_extracts_text_and_finish_reason():
    response = GeminiProvider._normalize(
        _gemini_response("Your wallet is in the drawer."), model="gemini-test", elapsed_ms=5
    )
    assert response.text == "Your wallet is in the drawer."
    assert response.finish_reason is FinishReason.STOP
    assert response.provider_id == "gemini"


def test_gemini_normalization_extracts_function_calls():
    function_call = SimpleNamespace(
        id="fc_1", name="search_memories", args={"query": "passport"}
    )
    part = SimpleNamespace(text=None, function_call=function_call)
    candidate = SimpleNamespace(
        content=SimpleNamespace(parts=[part]),
        finish_reason=SimpleNamespace(name="STOP"),
    )
    response = GeminiProvider._normalize(
        SimpleNamespace(candidates=[candidate], usage_metadata=None),
        model="gemini-test",
        elapsed_ms=1,
    )
    assert response.finish_reason is FinishReason.TOOL_CALLS
    assert response.tool_calls[0].arguments == {"query": "passport"}


def test_gemini_empty_response_is_an_error():
    with pytest.raises(ProviderResponseError):
        GeminiProvider._normalize(
            SimpleNamespace(candidates=[], usage_metadata=None),
            model="gemini-test",
            elapsed_ms=1,
        )


def test_gemini_provider_generates_with_injected_client():
    class FakeModels:
        def generate_content(self, **kwargs):
            self.kwargs = kwargs
            return _gemini_response("Ready.")

    client = SimpleNamespace(models=FakeModels())
    provider = GeminiProvider(api_key="AIza-test-key-1234567890", model="gemini-test", client=client)
    response = provider.generate(_user_request())
    assert response.text == "Ready."
    assert client.models.kwargs["model"] == "gemini-test"


def test_gemini_requires_api_key():
    provider = GeminiProvider(model="gemini-test")
    with pytest.raises(MissingApiKeyError):
        provider._build_client()


# --------------------------------------------------------------------------- #
# Local provider over a mocked HTTP transport (no socket is opened)
# --------------------------------------------------------------------------- #
def _local_provider(handler, **kwargs) -> LocalProvider:
    transport = httpx.MockTransport(handler)
    return LocalProvider(
        model="llama-test",
        base_url="http://local.test/v1",
        client=httpx.Client(transport=transport),
        **kwargs,
    )


def test_local_provider_generate_and_request_shape():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "llama-test",
                "choices": [{"message": {"content": "Local answer"}, "finish_reason": "stop"}],
            },
        )

    provider = _local_provider(handler)
    response = provider.generate(_user_request())

    assert response.text == "Local answer"
    assert captured["url"] == "http://local.test/v1/chat/completions"
    assert captured["body"]["stream"] is False
    assert captured["body"]["model"] == "llama-test"


def test_local_provider_reports_rate_limit_and_server_errors():
    with pytest.raises(ProviderRateLimitError):
        _local_provider(lambda request: httpx.Response(429, text="slow down")).generate(
            _user_request()
        )
    with pytest.raises(ProviderUnavailableError):
        _local_provider(lambda request: httpx.Response(503, text="down")).generate(_user_request())


def test_local_provider_reports_connection_failure():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderNetworkError):
        _local_provider(handler).generate(_user_request())


def test_local_provider_reports_timeout():
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(ProviderTimeoutError):
        _local_provider(handler).generate(_user_request())


def test_local_provider_validate_and_model_list():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "llama3"}, {"id": "qwen2.5"}]})
        return httpx.Response(404)

    provider = _local_provider(handler)
    result = provider.validate_api_key()
    assert result.ok is True
    assert result.available_models == ["llama3", "qwen2.5"]
    assert [model.id for model in provider.get_available_models()] == ["llama3", "qwen2.5"]


def test_local_provider_validate_fails_cleanly_when_unreachable():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    result = _local_provider(handler).validate_api_key()
    assert result.ok is False
    assert "local model server" in result.message.lower()


def test_local_provider_is_the_only_local_one():
    assert create_provider("local").is_local is True
    assert create_provider("gemini", api_key="x" * 20).is_local is False
