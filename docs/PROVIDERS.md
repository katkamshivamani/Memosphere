# Providers

## 1. Overview

| Provider id | Class | Type | Key required | Default model | Status |
| --- | --- | --- | --- | --- | --- |
| `gemini` | `GeminiProvider` | Cloud (`google-genai`) | Yes | None (fetched live) | Implemented; live call **not verified** in this build |
| `openai` | `OpenAIProvider` | Cloud (`openai`) | Yes | None (fetched live) | Implemented; live call **not verified** |
| `local` | `LocalProvider` | Any OpenAI-compatible local HTTP server | No | None (user picks) | Implemented; tested against a mocked HTTP transport |

No model id is hardcoded as a "current" model. The settings screen lists models from the provider; if a configured model disappears, the provider raises `UnsupportedModelError` instead of silently switching.

## 2. Gemini

- SDK: `google-genai==2.33.0`.
- Tools use `FunctionDeclaration(parameters_json_schema=...)`, so the registry's JSON Schema is passed through unchanged.
- Responses normalize `candidates[0].content.parts`: text, function calls, usage metadata and finish reason.
- `validate_api_key()` lists models; it is a real network check.
- Blocked/empty responses raise `ProviderResponseError` with a user-safe message.
- Base URL is configurable (`base_url`), defaulting to `https://generativelanguage.googleapis.com`.

## 3. OpenAI

- SDK: `openai==3.55.0`.
- Chat-completions payload is normalized to `ProviderResponse` by shared helpers.
- The same conversion helpers are reused by `LocalProvider`.
- Errors map by SDK exception type and HTTP status.
- Base URL is configurable for Azure/proxy-compatible endpoints.

## 4. Local

- Speaks the OpenAI chat-completions protocol over HTTP (Ollama, LM Studio, llama.cpp server, vLLM).
- Default base URL: `http://127.0.0.1:11434/v1`.
- No API key required; an `Authorization` header is sent only if one is configured.
- `generate()` uses `httpx`; timeouts and connection failures map to typed errors.
- `validate_api_key()` performs a `GET /models` check and reports failures honestly.
- This is the **only** provider allowed in Context Mode C (`local_only`). If no local server is running, Mode C refuses to operate; it never claims to work by falling back to cloud.

Example commands:

```powershell
ollama serve
ollama pull llama3
# Settings → Provider: Local model → Base URL http://127.0.0.1:11434/v1 → model llama3
```

## 5. API-key handling

- Keys are stored with **Windows DPAPI** (`CryptProtectData`) in a per-user container, not in the database or settings.
- `ApiKeyManager.masked_key()` returns only `••••••••` plus the last four characters.
- Keys are loaded only for the duration of a provider call/test and never logged.
- If secure storage is unavailable, key operations raise `CredentialStoreUnavailableError`; there is **no plaintext fallback**.
- Linux Secret Service and macOS Keychain adapters are declared but deliberately unimplemented; they report themselves unavailable.

## 6. Error mapping

| Condition | Exception |
| --- | --- |
| Missing key | `MissingApiKeyError` |
| 401/403 / rejected key | `ProviderAuthError` |
| 429 / quota | `ProviderRateLimitError` |
| Timeout | `ProviderTimeoutError` |
| Connection failure | `ProviderNetworkError` |
| 404 / unknown model | `UnsupportedModelError` |
| 5xx | `ProviderUnavailableError` |
| Empty or malformed response | `ProviderResponseError` |

Retries are handled by the orchestrator (bounded, honouring `retry_after`), never by providers.

## 7. Adding a provider

1. Implement `AIProvider` in `src/memory_agent/providers/<name>.py`.
2. Define a `ProviderInfo` with id, label, local flag, tool/streaming/audio capabilities.
3. Convert to/from neutral `ProviderRequest` / `ProviderResponse` only.
4. Map SDK errors to the types above.
5. Register the class in `providers/registry.py`.
6. Add offline tests with an injected fake client.
7. Add a live test under `tests/live/` guarded by an environment key.

## 8. Live verification

```powershell
$env:GEMINI_API_KEY="..."
python -m pytest tests/live -m live

$env:OPENAI_API_KEY="..."
python -m pytest tests/live -m live
```

Without those variables the live tests are skipped. They were skipped in the report included here because no keys were available.
