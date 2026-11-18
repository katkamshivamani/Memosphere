"""Controlled tool registry.

Responsibilities:

* reject unknown tool names;
* enforce argument schemas and per-tool permissions (inside the tool);
* enforce per-turn call limits and duplicate-call protection;
* apply execution timeouts;
* never expose tracebacks or SQL to the model.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Iterable, Optional

from memory_agent.config import AgentSettings
from memory_agent.core.exceptions import (
    ToolExecutionError,
    ToolLimitError,
    ToolTimeoutError,
    UnknownToolError,
)
from memory_agent.models.tool_result import ToolCall, ToolResult, ToolSpec
from memory_agent.security.permission_guard import PermissionGuard
from memory_agent.tools.base import BaseTool, ToolContext

logger = logging.getLogger("memory_agent.tools.registry")


def _call_key(call: ToolCall) -> str:
    try:
        canonical = json.dumps(call.arguments, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        canonical = repr(call.arguments)
    return f"{call.name}:{canonical}"


class ToolRegistry:
    """Thread-safe registry with per-turn budgets."""

    def __init__(
        self,
        tools: Iterable[BaseTool],
        *,
        max_tool_calls_per_turn: int = 12,
        executor: Optional[ThreadPoolExecutor] = None,
    ) -> None:
        self._tools: dict[str, BaseTool] = {}
        for tool in tools:
            self.register(tool)
        self._max_calls = max_tool_calls_per_turn
        self._executor = executor or ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent-tool")
        self._owns_executor = executor is None
        self._lock = threading.Lock()
        self._reset_turn_state()

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #
    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool name: {tool.name!r}")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> BaseTool:
        tool = self._tools.get(name)
        if tool is None:
            raise UnknownToolError(
                f"Tool {name!r} is not registered.",
                user_message="The assistant requested an action that does not exist.",
            )
        return tool

    def has(self, name: str) -> bool:
        return name in self._tools

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[ToolSpec]:
        return [tool.spec() for tool in self._tools.values()]

    # ------------------------------------------------------------------ #
    # Turn accounting
    # ------------------------------------------------------------------ #
    def begin_turn(self, max_calls: Optional[int] = None) -> None:
        with self._lock:
            self._max_calls = max_calls or self._max_calls
            self._reset_turn_state()

    def _reset_turn_state(self) -> None:
        self._call_count = 0
        self._seen_calls: set[str] = set()
        self._per_tool_counts: dict[str, int] = {}

    @property
    def calls_used(self) -> int:
        return self._call_count

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #
    def execute(
        self,
        call: ToolCall,
        *,
        user_id: str,
        guard: PermissionGuard,
        settings: AgentSettings,
        conversation_id: Optional[str] = None,
    ) -> ToolResult:
        """Execute one validated tool call, converting every failure to a result."""
        started = time.monotonic()

        try:
            tool = self.get(call.name)
        except UnknownToolError as exc:
            return ToolResult(
                call_id=call.id,
                tool=call.name,
                ok=False,
                error_code=UnknownToolError.code,
                error_message=exc.user_message,
            )

        key = _call_key(call)
        with self._lock:
            if self._call_count >= self._max_calls:
                return ToolResult(
                    call_id=call.id,
                    tool=call.name,
                    ok=False,
                    error_code=ToolLimitError.code,
                    error_message="Too many lookups for this question.",
                )
            if key in self._seen_calls:
                # Duplicate protection: return a marker, do not re-run the query.
                return ToolResult(
                    call_id=call.id,
                    tool=call.name,
                    ok=False,
                    error_code="duplicate_tool_call",
                    error_message="This exact lookup was already performed for this question.",
                )
            per_tool = self._per_tool_counts.get(tool.name, 0)
            if per_tool >= tool.max_calls_per_turn:
                return ToolResult(
                    call_id=call.id,
                    tool=tool.name,
                    ok=False,
                    error_code="tool_call_limit",
                    error_message=f"Tool {tool.name} has reached its per-question limit.",
                )
            self._seen_calls.add(key)
            self._call_count += 1
            self._per_tool_counts[tool.name] = per_tool + 1

        ctx = ToolContext(
            user_id=user_id,
            guard=guard,
            settings=settings,
            conversation_id=conversation_id,
            call_id=call.id,
        )
        future: Future = self._executor.submit(tool.execute, call, ctx)
        timeout = min(tool.timeout_s, settings.tool_timeout_s or tool.timeout_s)
        try:
            result = future.result(timeout=timeout)
        except FutureTimeout:
            future.cancel()
            logger.warning("Tool %s timed out after %.1fs", tool.name, timeout)
            result = ToolResult(
                call_id=call.id,
                tool=tool.name,
                ok=False,
                error_code=ToolTimeoutError.code,
                error_message="The lookup took too long and was stopped.",
            )
        except Exception as exc:
            logger.error("Unhandled tool failure for %s: %s", tool.name, type(exc).__name__)
            result = ToolResult(
                call_id=call.id,
                tool=tool.name,
                ok=False,
                error_code=ToolExecutionError.code,
                error_message="The lookup could not be completed.",
            )

        # Attach neutral timing for audit/debugging; never content.
        duration_ms = int((time.monotonic() - started) * 1000)
        result = result.model_copy(update={"data": {**result.data, "_duration_ms": duration_ms}})
        return result

    def shutdown(self) -> None:
        if self._owns_executor:
            self._executor.shutdown(wait=False, cancel_futures=True)
