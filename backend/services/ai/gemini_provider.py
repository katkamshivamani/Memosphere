"""
MEMOSPHERE Google Gemini API Provider
Connects to Google's Generative Language REST API with timeout, rate-limit,
invalid key/model, and network error handling.

Official endpoint: POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
Authentication:   x-goog-api-key: <GEMINI_API_KEY>
"""
import requests

from backend.services.ai.ai_client import BaseAIProvider, AIProviderError


class GeminiProvider(BaseAIProvider):
    provider_name = "gemini"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    DEFAULT_MODEL = "gemini-2.5-flash"

    @staticmethod
    def _error_indicates_bad_key(response) -> bool:
        """Classify a Gemini error body WITHOUT logging or returning its raw contents."""
        try:
            payload = response.json()
        except (ValueError, TypeError):
            return False
        if not isinstance(payload, dict):
            return False
        error = payload.get("error", {})
        if not isinstance(error, dict):
            return False
        status = str(error.get("status", "")).upper()
        message = str(error.get("message", "")).lower()
        key_markers = (
            "api key", "api_key", "apikey", "credential",
            "unauthorized", "permission denied", "authentication", "invalid key",
        )
        return status in {"UNAUTHENTICATED", "PERMISSION_DENIED"} or any(
            marker in message for marker in key_markers
        )

    def generate_completion(self, messages: list[dict], json_mode: bool = False) -> str:
        if not self.is_configured():
            raise AIProviderError(
                "GEMINI_API_KEY is not configured in environment variables.",
                error_code="missing_api_key",
                status_code=401,
            )

        model_name = self.model or self.DEFAULT_MODEL
        url = f"{self.BASE_URL}/{model_name}:generateContent"

        system_parts = []
        user_parts = []
        for msg in messages:
            if msg.get("role") == "system":
                system_parts.append({"text": msg.get("content", "")})
            else:
                user_parts.append({"text": msg.get("content", "")})

        payload: dict = {
            "contents": [{"role": "user", "parts": user_parts or [{"text": "Hello"}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 600,
            },
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        except requests.exceptions.Timeout as exc:
            raise AIProviderError(
                f"Gemini API request timed out after {self.timeout}s.",
                error_code="timeout",
                status_code=504,
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise AIProviderError(
                "Network error while reaching Google Gemini API.",
                error_code="network_error",
                status_code=503,
            ) from exc

        if response.status_code in (401, 403):
            raise AIProviderError(
                "Invalid or unauthorized Gemini API key. Please check GEMINI_API_KEY in your .env file.",
                error_code="invalid_api_key",
                status_code=401,
            )
        if response.status_code == 400:
            # Gemini uses 400 for BOTH bad keys and malformed requests/models.
            # Distinguish them from the error body instead of assuming a bad key.
            if self._error_indicates_bad_key(response):
                raise AIProviderError(
                    "Invalid or unauthorized Gemini API key. Please check GEMINI_API_KEY in your .env file.",
                    error_code="invalid_api_key",
                    status_code=401,
                )
            raise AIProviderError(
                "Gemini rejected the request (HTTP 400). Check GEMINI_MODEL and the request format.",
                error_code="invalid_request",
                status_code=400,
            )
        if response.status_code == 404:
            raise AIProviderError(
                "Gemini model not found. Check GEMINI_MODEL in your .env file.",
                error_code="invalid_model",
                status_code=404,
            )
        if response.status_code == 429:
            raise AIProviderError(
                "Gemini API rate limit reached. Please wait a moment or switch providers.",
                error_code="rate_limit",
                status_code=429,
            )
        if response.status_code >= 400:
            raise AIProviderError(
                f"Gemini API returned HTTP {response.status_code}.",
                error_code="provider_http_error",
                status_code=response.status_code,
            )

        try:
            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise KeyError("No candidates")
            text = candidates[0]["content"]["parts"][0]["text"]
            if not text:
                raise KeyError("Empty Gemini candidate text")
            return str(text)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(
                "Unexpected response structure from Google Gemini API.",
                error_code="malformed_response",
                status_code=502,
            ) from exc
