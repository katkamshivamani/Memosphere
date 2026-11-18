"""
MEMOSPHERE AI Settings & Status Routes
Endpoints:
- GET  /api/ai/status
- POST /api/ai/settings
- POST /api/ai/test
Security Rules:
- Never expose full API keys in responses.
- Never store API secrets in browser localStorage.
- Allow switching AI_PROVIDER (groq, nvidia_nim, gemini, openai) with a per-provider model.
- Invalid keys/models produce understandable messages instead of HTTP 500 crashes.
"""
import os

from flask import Blueprint, jsonify, request
from config import Config
from backend.services.ai.ai_client import AIClient, AIProviderError
from backend.services.ai.provider_factory import ProviderFactory

ai_settings_bp = Blueprint("ai_settings", __name__)


@ai_settings_bp.route("/api/ai/status", methods=["GET"])
def ai_status():
    verify = request.args.get("verify", "false").lower() in ("true", "1", "yes")
    client = AIClient()
    status = client.get_status(verify_live=verify)
    return jsonify(status), 200


@ai_settings_bp.route("/api/ai/settings", methods=["POST", "PUT"])
def update_ai_settings():
    data = request.get_json(silent=True) or {}
    provider = (data.get("provider") or Config.get_ai_provider()).strip().lower()
    model = (data.get("model") or "").strip()
    api_key = (data.get("api_key") or "").strip()

    if provider not in ProviderFactory.PROVIDERS:
        return jsonify({
            "error": "Unsupported provider '{}'. Supported: {}.".format(
                provider, ", ".join(ProviderFactory.supported_providers())
            )
        }), 400

    # Runtime (in-memory) provider switch. API keys stay in backend environment only.
    os.environ["AI_PROVIDER"] = provider

    # Per-provider model: switching providers never inherits the previous model.
    Config.set_ai_model(provider, model)

    # Only update the environment key if a new non-masked key was explicitly submitted.
    if api_key and "..." not in api_key and api_key != "****":
        Config.set_api_key(provider, api_key)

    client = AIClient()
    return jsonify({
        "message": f"AI configuration updated to {Config.PROVIDER_DISPLAY_NAMES.get(provider, provider.upper())}.",
        "status": client.get_status(verify_live=False),
    }), 200


@ai_settings_bp.route("/api/ai/test", methods=["POST"])
def test_ai_connection():
    data = request.get_json(silent=True) or {}
    provider_name = (data.get("provider") or Config.get_ai_provider()).strip().lower()
    model_name = (data.get("model") or Config.get_ai_model(provider_name)).strip()

    try:
        provider = ProviderFactory.create_provider(
            provider_name=provider_name, model=model_name
        )
        result = provider.test_connection()
    except AIProviderError as exc:
        # Unsupported provider / invalid configuration must not crash the app.
        result = {
            "connected": False,
            "provider": provider_name,
            "model": model_name,
            "mode": "rule_based_fallback",
            "error_code": exc.error_code,
            "message": exc.message,
        }

    return jsonify(result), 200
