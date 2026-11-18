"""
MEMOSPHERE AI Integration Layer (init.py)
Exports the common AI provider interface, all provider adapters, and the factory.
"""
from backend.services.ai.ai_client import AIClient, BaseAIProvider, AIProviderError
from backend.services.ai.provider_factory import ProviderFactory
from backend.services.ai.groq_provider import GroqProvider
from backend.services.ai.nvidia_nim_provider import NvidiaNimProvider
from backend.services.ai.gemini_provider import GeminiProvider
from backend.services.ai.openai_provider import OpenAIProvider

__all__ = [
    "AIClient",
    "BaseAIProvider",
    "AIProviderError",
    "ProviderFactory",
    "GroqProvider",
    "NvidiaNimProvider",
    "GeminiProvider",
    "OpenAIProvider",
]
