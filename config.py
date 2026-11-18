import os
from dotenv import load_dotenv

load_dotenv()


class BackendConfig:
    """Backend-only configuration manager. API keys remain strictly on the server.
    
    Supported providers:
    - gemini: Google Gemini API
    - openai: OpenAI API (and compatible: Groq, NVIDIA NIM, Together, etc.)
    - anthropic: Anthropic Claude API
    - custom: Any OpenAI-compatible endpoint
    """

    # Known provider configurations
    PROVIDER_CONFIGS = {
        "gemini": {
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "default_model": "gemini-2.5-flash",
            "api_key_env": "GEMINI_API_KEY",
        },
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "default_model": "gpt-4o-mini",
            "api_key_env": "OPENAI_API_KEY",
        },
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "default_model": "llama-3.3-70b-versatile",
            "api_key_env": "GROQ_API_KEY",
        },
        "nvidia": {
            "base_url": "https://integrate.api.nvidia.com/v1",
            "default_model": "nvidia/nemotron-3-ultra",
            "api_key_env": "NVIDIA_API_KEY",
        },
        "nvidia_nim": {
            "base_url": "https://integrate.api.nvidia.com/v1",
            "default_model": "meta/llama-3.1-405b-instruct",
            "api_key_env": "NVIDIA_API_KEY",
        },
        "together": {
            "base_url": "https://api.together.xyz/v1",
            "default_model": "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
            "api_key_env": "TOGETHER_API_KEY",
        },
        "anthropic": {
            "base_url": "https://api.anthropic.com/v1",
            "default_model": "claude-3-5-sonnet-20241022",
            "api_key_env": "ANTHROPIC_API_KEY",
        },
        "custom": {
            "base_url": "",  # User must provide
            "default_model": "",
            "api_key_env": "CUSTOM_API_KEY",
        },
    }

    def __init__(self):
        self.port = int(os.environ.get("PORT", 8000))
        self.database_path = os.environ.get("DATABASE_PATH", "memosphere.db")
        self.secret_key = os.environ.get(
            "MEMOSPHERE_SECRET_KEY", "memosphere-local-first-secret-key-2026"
        )
        
        # Provider selection
        self.ai_provider = os.environ.get("AI_PROVIDER", "gemini").lower()
        
        # Model (can be overridden per provider)
        self.ai_model = os.environ.get("AI_MODEL", "").strip()
        
        # Load all API keys from environment
        self.api_keys = {}
        for provider_id, config in self.PROVIDER_CONFIGS.items():
            env_key = config.get("api_key_env")
            if env_key:
                self.api_keys[provider_id] = os.environ.get(env_key, "").strip()
        
        # Custom provider settings
        self.custom_base_url = os.environ.get("CUSTOM_BASE_URL", "").strip()
        self.custom_model = os.environ.get("CUSTOM_MODEL", "").strip()
        
        # Generation settings
        self.ai_temperature = float(os.environ.get("AI_TEMPERATURE", "0.2"))
        self.ai_max_tokens = int(os.environ.get("AI_MAX_TOKENS", "600"))

    def get_provider_config(self, provider: str = None) -> dict:
        """Get configuration for a specific provider."""
        provider = (provider or self.ai_provider).lower()
        config = self.PROVIDER_CONFIGS.get(provider, self.PROVIDER_CONFIGS["custom"]).copy()
        
        # Override with custom settings if using custom provider
        if provider == "custom":
            config["base_url"] = self.custom_base_url or config["base_url"]
            config["default_model"] = self.custom_model or config["default_model"]
        
        # Use provider-specific model if set, otherwise use global AI_MODEL or default
        if not self.ai_model:
            config["model"] = config["default_model"]
        else:
            config["model"] = self.ai_model
            
        config["api_key"] = self.api_keys.get(provider, "")
        config["provider_id"] = provider
        return config

    def has_active_api_key(self, provider: str = None) -> bool:
        """Check if the current (or specified) provider has an API key configured."""
        provider = (provider or self.ai_provider).lower()
        config = self.get_provider_config(provider)
        return bool(config.get("api_key"))

    def get_public_ai_config(self) -> dict:
        """Safe metadata returned to the frontend — NEVER includes raw API keys."""
        config = self.get_provider_config()
        return {
            "provider": self.ai_provider,
            "model": config.get("model", "unknown"),
            "temperature": self.ai_temperature,
            "maxTokens": self.ai_max_tokens,
            "hasApiKeyConfigured": self.has_active_api_key(),
            "availableProviders": list(self.PROVIDER_CONFIGS.keys()),
            "privacyNotice": (
                "Personal records remain in your local SQLite database. Only minimal retrieved "
                "context is sent to the configured external LLM provider when answering AI queries."
            ),
        }

    def update_settings(
        self,
        provider: str = None,
        model: str = None,
        temperature: float = None,
        max_tokens: int = None,
        api_key: str = None,
        base_url: str = None,
    ):
        """Update AI settings. API keys stored in backend memory only."""
        if provider and provider.lower() in self.PROVIDER_CONFIGS:
            self.ai_provider = provider.lower()
        
        if model:
            self.ai_model = model.strip()
        
        if temperature is not None:
            self.ai_temperature = max(0.0, min(1.0, float(temperature)))
        
        if max_tokens is not None:
            self.ai_max_tokens = max(64, min(4096, int(max_tokens)))
        
        if api_key is not None and api_key.strip():
            provider = (provider or self.ai_provider).lower()
            self.api_keys[provider] = api_key.strip()
            # Also update environment variable for persistence
            env_key = self.PROVIDER_CONFIGS.get(provider, {}).get("api_key_env")
            if env_key:
                os.environ[env_key] = api_key.strip()
        
        if base_url is not None:
            self.custom_base_url = base_url.strip()


settings = BackendConfig()