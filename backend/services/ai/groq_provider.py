"""
MEMOSPHERE Groq API Provider
Connects to Groq's OpenAI-compatible Chat Completions REST endpoint with timeout,
rate-limit, invalid key/model, and network error handling.

Official endpoint: POST https://api.groq.com/openai/v1/chat/completions
Authentication:   Authorization: Bearer <GROQ_API_KEY>
"""
import requests

from config import Config
from backend.services.ai.ai_client import BaseAIProvider, AIProviderError


class GroqProvider(BaseAIProvider):
    provider_name = "groq"
    DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
    DEFAULT_MODEL = "llama-3.3-70b-versatile"

    def __init__(self, api_key: str, model: str, timeout: int = 15, base_url: str | None = None):
        super().__init__(api_key=api_key, model=model, timeout=timeout)
        configured_url = (base_url or Config.get_base_url("groq") or self.DEFAULT_BASE_URL).strip().rstrip("/")
        self.base_url = configured_url
        self.api_url = f"{configured_url}/chat/completions"

    def generate_completion(self, messages: list[dict], json_mode: bool = False) -> str:
        if not self.is_configured():
            raise AIProviderError(
                "GROQ_API_KEY is not configured in environment variables.",
                error_code="missing_api_key",
                status_code=401,
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": self.model or self.DEFAULT_MODEL,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 600,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = requests.post(
                self.api_url, headers=headers, json=payload, timeout=self.timeout
            )
        except requests.exceptions.Timeout as exc:
            raise AIProviderError(
                f"Groq API request timed out after {self.timeout}s.",
                error_code="timeout",
                status_code=504,
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise AIProviderError(
                "Network error while reaching Groq API. Please check your internet connection.",
                error_code="network_error",
                status_code=503,
            ) from exc

        if response.status_code in (401, 403):
            raise AIProviderError(
                "Invalid or unauthorized Groq API key. Please check GROQ_API_KEY in your .env file.",
                error_code="invalid_api_key",
                status_code=401,
            )
        if response.status_code == 404:
            raise AIProviderError(
                "Groq model not found. Check GROQ_MODEL (or the provider's model setting) in your .env file.",
                error_code="invalid_model",
                status_code=404,
            )
        if response.status_code == 429:
            raise AIProviderError(
                "Groq API rate limit reached. Please wait a moment or switch providers.",
                error_code="rate_limit",
                status_code=429,
            )
        if response.status_code >= 400:
            raise AIProviderError(
                f"Groq API returned HTTP {response.status_code}.",
                error_code="provider_http_error",
                status_code=response.status_code,
            )

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if not content:
                raise KeyError("Empty content")
            return str(content)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(
                "Unexpected response structure from Groq API.",
                error_code="malformed_response",
                status_code=502,
            ) from exc
