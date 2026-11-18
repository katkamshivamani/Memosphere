"""
MEMOSPHERE Configuration Module
Loads environment variables safely without hardcoding or exposing API secrets.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=False)
else:
    load_dotenv(override=False)

INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)


class Config:
    """Application configuration backed by environment variables."""

    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "memosphere-dev-secret-key-2026")
    DEBUG = os.environ.get("FLASK_DEBUG", "False").lower() in ("true", "1", "yes")
    PORT = int(os.environ.get("PORT", 5000))

    DEFAULT_DB_PATH = INSTANCE_DIR / "memosphere.db"
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Provider registry. Each provider has its OWN key, model and (where applicable)
    # base URL so switching providers can never carry over another provider's model.
    PROVIDER_KEY_ENV = {
        "groq": "GROQ_API_KEY",
        "nvidia_nim": "NVIDIA_NIM_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "openai": "OPENAI_API_KEY",
    }
    PROVIDER_MODEL_ENV = {
        "groq": "GROQ_MODEL",
        "nvidia_nim": "NVIDIA_NIM_MODEL",
        "gemini": "GEMINI_MODEL",
        "openai": "OPENAI_MODEL",
    }
    PROVIDER_DISPLAY_NAMES = {
        "groq": "Groq Cloud API",
        "nvidia_nim": "NVIDIA NIM API",
        "gemini": "Google Gemini API",
        "openai": "OpenAI API",
    }
    DEFAULT_MODELS = {
        "groq": "llama-3.3-70b-versatile",
        "nvidia_nim": "meta/llama-3.1-70b-instruct",
        "gemini": "gemini-2.5-flash",
        "openai": "gpt-4o-mini",
    }
    BASE_URL_ENV = {
        "groq": "GROQ_BASE_URL",
        "nvidia_nim": "NVIDIA_NIM_BASE_URL",
        "openai": "OPENAI_BASE_URL",
    }
    DEFAULT_BASE_URLS = {
        "groq": "https://api.groq.com/openai/v1",
        "nvidia_nim": "https://integrate.api.nvidia.com/v1",
        "openai": "https://api.openai.com/v1",
    }

    # Runtime overrides set through /api/ai/settings, keyed by provider.
    _RUNTIME_MODELS: dict[str, str] = {}

    @classmethod
    def get_ai_provider(cls) -> str:
        return os.environ.get("AI_PROVIDER", "groq").strip().lower()

    @classmethod
    def get_ai_model(cls, provider: str | None = None) -> str:
        """Resolve the model for ONE provider. Per-provider settings always win."""
        prov = (provider or cls.get_ai_provider()).lower()

        runtime_model = cls._RUNTIME_MODELS.get(prov, "").strip()
        if runtime_model:
            return runtime_model

        model_env = cls.PROVIDER_MODEL_ENV.get(prov, "")
        per_provider_model = os.environ.get(model_env, "").strip() if model_env else ""
        if per_provider_model:
            return per_provider_model

        # Deprecated global override. Kept only for the historic default provider so
        # an old AI_MODEL value can never be sent to Gemini/NVIDIA/OpenAI.
        legacy_model = os.environ.get("AI_MODEL", "").strip()
        if legacy_model and prov == "groq":
            return legacy_model

        return cls.DEFAULT_MODELS.get(prov, cls.DEFAULT_MODELS["groq"])

    @classmethod
    def set_ai_model(cls, provider: str, model: str) -> str:
        """Set a runtime model override for a single provider (no cross-provider collision)."""
        prov = provider.strip().lower()
        clean_model = (model or "").strip() or cls.DEFAULT_MODELS.get(
            prov, cls.DEFAULT_MODELS["groq"]
        )
        cls._RUNTIME_MODELS[prov] = clean_model
        model_env = cls.PROVIDER_MODEL_ENV.get(prov)
        if model_env:
            os.environ[model_env] = clean_model
        return clean_model

    @classmethod
    def get_api_key(cls, provider: str | None = None) -> str:
        prov = (provider or cls.get_ai_provider()).lower()
        key_env = cls.PROVIDER_KEY_ENV.get(prov, "")
        return os.environ.get(key_env, "").strip() if key_env else ""

    @classmethod
    def set_api_key(cls, provider: str, key: str) -> None:
        """Store a runtime API key for one provider only (process memory, never browser)."""
        prov = provider.strip().lower()
        key_env = cls.PROVIDER_KEY_ENV.get(prov)
        if key_env and key:
            os.environ[key_env] = key.strip()

    @classmethod
    def get_base_url(cls, provider: str) -> str:
        """Base URL for OpenAI-compatible providers (Groq, NVIDIA NIM, OpenAI)."""
        prov = provider.strip().lower()
        url_env = cls.BASE_URL_ENV.get(prov, "")
        configured = os.environ.get(url_env, "").strip() if url_env else ""
        return configured or cls.DEFAULT_BASE_URLS.get(prov, "")

    @classmethod
    def get_timeout(cls) -> int:
        try:
            return max(3, int(os.environ.get("AI_TIMEOUT_SECONDS", "15")))
        except ValueError:
            return 15

    @classmethod
    def mask_api_key(cls, key: str) -> str:
        """Mask API key so secrets are never exposed to the frontend or logs."""
        if not key or len(key.strip()) == 0:
            return "Not configured"
        clean = key.strip()
        if len(clean) <= 8:
            return "****"
        return f"{clean[:4]}...{clean[-4:]}"
