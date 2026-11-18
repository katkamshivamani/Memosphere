"""Tool call/result models shared by the registry, providers and orchestrator."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from memory_agent.models.memory import Record, SourceRef
from memory_agent.models.message import utc_now
from memory_agent.models.suggestion import Suggestion


class ToolSpec(BaseModel):
    """Provider-facing description of one allowed tool."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    parameters: dict[str, Any]
    permission: str


class ToolCall(BaseModel):
    """A tool request produced by an AI model.

    ``arguments`` is only ever the output of JSON parsing; it is validated
    against the tool's Pydantic schema before execution.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:12]}")
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolTraceEntry(BaseModel):
    """Audit-friendly record of one tool execution."""

    model_config = ConfigDict(extra="forbid")

    call_id: str
    tool: str
    ok: bool
    error_code: Optional[str] = None
    record_count: int = 0
    duration_ms: int = 0
    duplicate: bool = False


class ToolResult(BaseModel):
    """Normalized output of a tool execution.

    The ``data`` payload is returned to the model (and rendered in the UI as
    evidence), so it must only contain authorized records.
    """

    model_config = ConfigDict(extra="forbid")

    call_id: str
    tool: str
    ok: bool = True
    data: dict[str, Any] = Field(default_factory=dict)
    records: list[Record] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    suggestion: Optional[Suggestion] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)

    def model_content(self, max_chars: int = 12000) -> str:
        """Serialize the result for the model inside explicit untrusted markers.

        Record text returned by tools is data, never instructions.  Wrapping it
        in delimiters (matching the context builder) gives the model a clear
        boundary even when a stored record contains instruction-like text.
        """
        payload: dict[str, Any] = {
            "tool": self.tool,
            "ok": self.ok,
        }
        if self.ok:
            payload["data"] = self.data
        else:
            payload["error"] = {
                "code": self.error_code,
                "message": self.error_message or "The action failed.",
            }
        begin = f"<<<UNTRUSTED_TOOL_RESULT name={self.tool}>>>"
        end = "<<<END_UNTRUSTED_TOOL_RESULT>>>"
        budget = max(200, max_chars) - len(begin) - len(end) - 2
        text = json.dumps(payload, ensure_ascii=False, default=str)
        if len(text) > budget:
            text = text[:budget] + '... [truncated]"}'
        return f"{begin}\n{text}\n{end}"
