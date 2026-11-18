"""Neutral provider protocol schemas.

Every provider implementation converts to/from these models.  No Gemini- or
OpenAI-specific object ever leaves ``memory_agent.providers.*``.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProviderRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolResultPayload(BaseModel):
    """Tool output returned to the model as a tool-role message."""

    model_config = ConfigDict(extra="forbid")

    tool_call_id: str
    name: str
    content: str
    is_error: bool = False


class ProviderMessage(BaseModel):
    """A provider-neutral message.

    ``tool_calls`` only appears on assistant messages; ``tool_results`` only
    appears on tool messages.
    """

    model_config = ConfigDict(extra="forbid")

    role: ProviderRole
    text: Optional[str] = None
    tool_calls: list["ProviderToolRequest"] = Field(default_factory=list)
    tool_results: list[ToolResultPayload] = Field(default_factory=list)


class ProviderToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ProviderRequest(BaseModel):
    """One provider round-trip request."""

    model_config = ConfigDict(extra="forbid")

    system_instruction: Optional[str] = None
    messages: list[ProviderMessage] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    model: Optional[str] = None
    temperature: float = 0.2
    max_output_tokens: Optional[int] = 1024
    timeout_s: float = 45.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class Usage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class FinishReason(str, Enum):
    STOP = "stop"
    TOOL_CALLS = "tool_calls"
    MAX_TOKENS = "max_tokens"
    SAFETY = "safety"
    ERROR = "error"
    UNKNOWN = "unknown"


class ProviderResponse(BaseModel):
    """Normalized model response."""

    model_config = ConfigDict(extra="forbid")

    text: Optional[str] = None
    tool_calls: list[ProviderToolRequest] = Field(default_factory=list)
    usage: Optional[Usage] = None
    finish_reason: FinishReason = FinishReason.STOP
    model: Optional[str] = None
    provider_id: str = ""
    raw_finish_reason: Optional[str] = None

    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class ProviderInfo(BaseModel):
    """Static capability description used by settings UI and the registry."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    is_local: bool = False
    requires_api_key: bool = True
    supports_tools: bool = True
    supports_streaming: bool = False
    supports_audio_transcription: bool = False
    default_model: Optional[str] = None
    documentation_url: Optional[str] = None
    notes: str = ""


class ConnectionTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    provider_id: str
    model: Optional[str] = None
    message: str = ""
    available_models: list[str] = Field(default_factory=list)


class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str = ""
    supports_tools: bool = True


ProviderKind = Literal["gemini", "openai", "local"]

# Rebuild forward reference (ProviderMessage references ProviderToolRequest).
ProviderMessage.model_rebuild()
