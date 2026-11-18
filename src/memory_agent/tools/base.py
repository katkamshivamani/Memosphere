"""Tool abstraction: schema, permission, timeout and safe execution."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, Optional, Sequence, Type, TypeVar

from pydantic import BaseModel, ValidationError

from memory_agent.config import AgentSettings
from memory_agent.core.exceptions import (
    AgentError,
    PermissionDeniedError,
    ToolExecutionError,
    ToolPermissionError,
    ToolValidationError,
)
from memory_agent.models.suggestion import Suggestion, SuggestionStatus, SuggestionType
from memory_agent.models.tool_result import ToolCall, ToolResult, ToolSpec
from memory_agent.security.permission_guard import PermissionGuard
from memory_agent.security.permissions import Permission

logger = logging.getLogger("memory_agent.tools")

ArgsT = TypeVar("ArgsT", bound=BaseModel)


@dataclass
class ToolContext:
    """Per-request execution context. Never contains credentials."""

    user_id: str
    guard: PermissionGuard
    settings: AgentSettings
    conversation_id: Optional[str] = None
    call_id: str = ""

    def suggestion(
        self,
        suggestion_type: SuggestionType,
        *,
        title: str,
        description: str,
        reason: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> Suggestion:
        return Suggestion(
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            type=suggestion_type,
            title=title,
            description=description,
            reason=reason,
            payload=payload or {},
            status=SuggestionStatus.PENDING_APPROVAL,
        )


class BaseTool(ABC, Generic[ArgsT]):
    """A single, narrowly-scoped capability exposed to the model.

    Subclasses define ``name``, ``description``, ``permission`` and
    ``args_model``.  ``_run`` receives validated arguments only.
    """

    name: str = ""
    description: str = ""
    permission: Permission
    args_model: Type[ArgsT]
    timeout_s: float = 10.0
    max_calls_per_turn: int = 4
    produces_suggestion: bool = False

    def __init__(self, *, timeout_s: Optional[float] = None) -> None:
        if not self.name:
            raise ValueError(f"{type(self).__name__} must define a tool name")
        if not self.description:
            raise ValueError(f"Tool {self.name!r} must have a description")
        if not issubclass(self.args_model, BaseModel):
            raise TypeError(f"Tool {self.name!r} must define a Pydantic args_model")
        if not isinstance(self.permission, Permission):
            raise TypeError(f"Tool {self.name!r} must declare a Permission")
        if timeout_s is not None:
            self.timeout_s = timeout_s

    # ------------------------------------------------------------------ #
    # Provider-facing description
    # ------------------------------------------------------------------ #
    def parameters_schema(self) -> dict[str, Any]:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        # Pydantic emits $defs for nested enums; JSON Schema is valid for both
        # Gemini (parameters_json_schema) and OpenAI (parameters).
        return schema

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=self.parameters_schema(),
            permission=self.permission.value,
        )

    def validate_args(self, raw: dict[str, Any]) -> ArgsT:
        if not isinstance(raw, dict):
            raise ToolValidationError(
                f"Arguments for {self.name!r} must be an object.",
                user_message="The assistant requested an action with invalid details.",
            )
        try:
            return self.args_model.model_validate(raw)
        except ValidationError as exc:
            # Report field-level validation failures without echoing record data.
            fields = ", ".join(
                ".".join(str(part) for part in error["loc"]) or "arguments"
                for error in exc.errors()[:5]
            )
            raise ToolValidationError(
                f"Invalid arguments for {self.name!r}: {fields}",
                user_message="The assistant requested an action with invalid details.",
                details={"fields": fields},
            ) from exc

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #
    def execute(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        """Validate permission + arguments, then run the tool.

        Exceptions are converted into failed :class:`ToolResult` objects so the
        model can recover, but they never escalate privileges.
        """
        started_permission = self.permission
        try:
            ctx.guard.require(ctx.user_id, started_permission, purpose=self.name)
        except PermissionDeniedError as exc:
            return ToolResult(
                call_id=call.id,
                tool=self.name,
                ok=False,
                error_code=ToolPermissionError.code,
                error_message="Permission for this information is not granted.",
            )
        except AgentError as exc:
            return ToolResult(
                call_id=call.id,
                tool=self.name,
                ok=False,
                error_code=exc.code,
                error_message=exc.user_message,
            )

        try:
            args = self.validate_args(call.arguments)
        except ToolValidationError as exc:
            return ToolResult(
                call_id=call.id,
                tool=self.name,
                ok=False,
                error_code=exc.code,
                error_message=exc.user_message,
            )

        ctx.call_id = call.id
        try:
            result = self._run(ctx, args)
        except AgentError as exc:
            logger.warning("Tool %s failed: %s", self.name, exc.code)
            return ToolResult(
                call_id=call.id,
                tool=self.name,
                ok=False,
                error_code=exc.code,
                error_message=exc.user_message,
            )
        except Exception as exc:
            # Log type only: messages may contain personal data.
            logger.error("Tool %s raised %s", self.name, type(exc).__name__)
            raise ToolExecutionError(
                f"Tool {self.name} failed with {type(exc).__name__}",
            ) from exc

        if result.call_id != call.id:
            result = result.model_copy(update={"call_id": call.id})
        return result

    @abstractmethod
    def _run(self, ctx: ToolContext, args: ArgsT) -> ToolResult:
        """Execute the tool with validated arguments."""


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def record_payload(record, max_chars: int = 2000) -> dict[str, Any]:
    """Serialize a record for the model, truncating oversized content."""
    content = record.content or ""
    if len(content) > max_chars:
        content = content[:max_chars].rstrip() + " …[truncated]"
    return {
        "id": record.id,
        "type": record.type.value,
        "title": record.title,
        "content": content,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        "source_module": record.source_module,
        "metadata": record.metadata,
    }


def records_result(
    call_id: str,
    tool: str,
    records: Sequence,
    *,
    note: str = "",
    extra: Optional[dict[str, Any]] = None,
    max_chars: int = 2000,
) -> ToolResult:
    payload_records = [record_payload(record, max_chars=max_chars) for record in records]
    data: dict[str, Any] = {
        "count": len(payload_records),
        "records": payload_records,
    }
    if note:
        data["note"] = note
    if extra:
        data.update(extra)
    return ToolResult(
        call_id=call_id,
        tool=tool,
        ok=True,
        data=data,
        records=list(records),
        sources=[record.source_ref() for record in records],
    )


def parse_iso_datetime(value: str, field_name: str) -> datetime:
    """Parse an ISO date/datetime or raise a validation error."""
    text = (value or "").strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise ToolValidationError(
            f"{field_name} must be an ISO-8601 date or datetime, got {value!r}",
            user_message=f"The assistant supplied an invalid {field_name}.",
        ) from exc

