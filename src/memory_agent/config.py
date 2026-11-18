"""Agent configuration and non-sensitive settings persistence.

Settings never contain API keys.  :meth:`AgentSettings.assert_secret_free` is
called on save so an accidental key write fails loudly instead of leaking.
"""

from __future__ import annotations

import json
import os
import tempfile
from enum import Enum
from pathlib import Path
from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from memory_agent.core.exceptions import ConfigurationError


class ContextMode(str, Enum):
    """Privacy modes enforced by the ContextBuilder before every request."""

    MINIMAL = "minimal"              # Mode A: only records relevant to the question
    FULL_AUTHORIZED = "full_authorized"  # Mode B: consent-gated, broad categories
    LOCAL_ONLY = "local_only"        # Mode C: never send personal data to cloud

    @property
    def label(self) -> str:
        return {
            ContextMode.MINIMAL: "Minimal context (recommended)",
            ContextMode.FULL_AUTHORIZED: "Full authorized context (requires consent)",
            ContextMode.LOCAL_ONLY: "Local only (no cloud AI)",
        }[self]


class VoiceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    speak_responses: bool = False
    cloud_transcription_allowed: bool = False
    stt_backend: str = "auto"   # auto | local | gemini | disabled
    tts_backend: str = "auto"   # auto | sapi | disabled
    max_recording_seconds: int = 60


class QuietHours(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    start_hour: int = 22
    end_hour: int = 7

    def contains_hour(self, hour: int) -> bool:
        if not self.enabled:
            return False
        if self.start_hour == self.end_hour:
            return False
        if self.start_hour < self.end_hour:
            return self.start_hour <= hour < self.end_hour
        return hour >= self.start_hour or hour < self.end_hour


class AgentSettings(BaseModel):
    """User-configurable agent behaviour. No secrets, ever."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    provider_id: str = "gemini"
    models: dict[str, str] = Field(default_factory=dict)
    base_urls: dict[str, str] = Field(default_factory=dict)
    context_mode: ContextMode = ContextMode.MINIMAL
    temperature: float = 0.2
    max_tool_rounds: int = 5
    max_tool_calls_per_turn: int = 12
    provider_timeout_s: float = 45.0
    tool_timeout_s: float = 10.0
    max_context_chars: int = 8000
    max_record_chars: int = 1200
    max_response_chars: int = 6000
    max_tool_result_chars: int = 12000
    proactive_enabled: bool = False
    quiet_hours: QuietHours = Field(default_factory=QuietHours)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)

    @field_validator("max_tool_rounds")
    @classmethod
    def _bounded_rounds(cls, value: int) -> int:
        if not 1 <= value <= 5:
            raise ValueError("max_tool_rounds must be between 1 and 5")
        return value

    @field_validator("max_tool_calls_per_turn")
    @classmethod
    def _bounded_calls(cls, value: int) -> int:
        if not 1 <= value <= 40:
            raise ValueError("max_tool_calls_per_turn must be between 1 and 40")
        return value

    @field_validator("temperature")
    @classmethod
    def _bounded_temperature(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("temperature must be between 0 and 1")
        return value

    def model_for(self, provider_id: Optional[str] = None) -> Optional[str]:
        return self.models.get(provider_id or self.provider_id) or None

    def set_model(self, provider_id: str, model: str) -> "AgentSettings":
        data = self.model_dump()
        data["models"] = {**self.models, provider_id: model}
        return AgentSettings.model_validate(data)

    def assert_secret_free(self) -> None:
        """Refuse to persist anything that looks like a credential."""
        from memory_agent.security.data_filter import find_secrets

        text = json.dumps(self.model_dump(mode="json"), ensure_ascii=False)
        findings = find_secrets(text)
        if findings:
            raise ConfigurationError(
                "Refusing to save settings containing what looks like a credential "
                f"({', '.join(sorted({f.kind for f in findings}))}).",
                user_message="Settings were not saved because they contained a secret value.",
            )


class SettingsStore(Protocol):
    def load(self) -> AgentSettings: ...
    def save(self, settings: AgentSettings) -> None: ...


class InMemorySettingsStore:
    """Settings store for tests and short-lived processes."""

    def __init__(self, settings: Optional[AgentSettings] = None) -> None:
        self._settings = settings or AgentSettings()

    def load(self) -> AgentSettings:
        return self._settings.model_copy(deep=True)

    def save(self, settings: AgentSettings) -> None:
        settings.assert_secret_free()
        self._settings = settings.model_copy(deep=True)


class JsonSettingsStore:
    """Atomic JSON settings store (non-sensitive configuration only)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._cached: Optional[AgentSettings] = None

    def load(self) -> AgentSettings:
        if not self.path.exists():
            return AgentSettings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return AgentSettings.model_validate(raw)
        except (OSError, ValueError, ConfigurationError):
            # Corrupt settings never block the app: fall back to safe defaults.
            return AgentSettings()

    def save(self, settings: AgentSettings) -> None:
        settings.assert_secret_free()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(settings.model_dump(mode="json"), indent=2)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass


def default_agent_settings() -> AgentSettings:
    return AgentSettings()
