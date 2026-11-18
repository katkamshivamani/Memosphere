"""Tool registry and tool permission behaviour."""

from __future__ import annotations

import time

from pydantic import BaseModel

from memory_agent.models.tool_result import ToolCall, ToolResult
from memory_agent.security.permissions import Permission
from memory_agent.tools.base import BaseTool, ToolContext
from memory_agent.tools.registry import ToolRegistry

from tests.helpers import make_harness


class SleepArgs(BaseModel):
    seconds: float = 0.0


class SleepTool(BaseTool):
    name = "sleep_tool"
    description = "Test-only tool that sleeps."
    permission = Permission.MEMORY_READ
    args_model = SleepArgs
    timeout_s = 0.05

    def _run(self, ctx: ToolContext, args: SleepArgs) -> ToolResult:
        time.sleep(args.seconds)
        return ToolResult(call_id=ctx.call_id, tool=self.name, data={"slept": args.seconds})


class EchoArgs(BaseModel):
    value: str = ""


class EchoTool(BaseTool):
    name = "echo_tool"
    description = "Test-only echo tool."
    permission = Permission.MEMORY_READ
    args_model = EchoArgs
    max_calls_per_turn = 2

    def _run(self, ctx: ToolContext, args: EchoArgs) -> ToolResult:
        return ToolResult(call_id=ctx.call_id, tool=self.name, data={"value": args.value})


def _context(harness):
    return ToolContext(user_id="user_001", guard=harness.guard, settings=harness.settings)


def test_unknown_tool_is_reported_not_executed(tmp_path):
    harness = make_harness(tmp_path)
    result = harness.runtime.registry.execute(
        ToolCall(name="drop_database", arguments={}),
        user_id="user_001",
        guard=harness.guard,
        settings=harness.settings,
    )
    assert result.ok is False
    assert result.error_code == "unknown_tool"


def test_argument_validation_rejects_wrong_types(tmp_path):
    harness = make_harness(tmp_path)
    result = harness.runtime.registry.execute(
        ToolCall(name="search_memories", arguments={"limit": "many"}),
        user_id="user_001",
        guard=harness.guard,
        settings=harness.settings,
    )
    assert result.ok is False
    assert result.error_code == "invalid_tool_arguments"


def test_permission_denied_blocks_tool(tmp_path):
    harness = make_harness(tmp_path, denied={"memory.read"})
    result = harness.runtime.registry.execute(
        ToolCall(name="search_memories", arguments={"query": "wallet"}),
        user_id="user_001",
        guard=harness.guard,
        settings=harness.settings,
    )
    assert result.ok is False
    assert result.error_code == "tool_permission_denied"


def test_turn_call_limit(tmp_path):
    harness = make_harness(tmp_path)
    harness.runtime.registry.begin_turn(max_calls=1)
    first = harness.runtime.registry.execute(
        ToolCall(name="search_memories", arguments={"query": "wallet"}),
        user_id="user_001",
        guard=harness.guard,
        settings=harness.settings,
    )
    second = harness.runtime.registry.execute(
        ToolCall(name="search_memories", arguments={"query": "keys"}),
        user_id="user_001",
        guard=harness.guard,
        settings=harness.settings,
    )
    assert first.ok is True
    assert second.ok is False
    assert second.error_code == "tool_limit_exceeded"


def test_duplicate_arguments_are_rejected(tmp_path):
    harness = make_harness(tmp_path)
    harness.runtime.registry.begin_turn()
    call = ToolCall(name="search_memories", arguments={"query": "wallet"})
    first = harness.runtime.registry.execute(
        call, user_id="user_001", guard=harness.guard, settings=harness.settings
    )
    second = harness.runtime.registry.execute(
        call, user_id="user_001", guard=harness.guard, settings=harness.settings
    )
    assert first.ok is True
    assert second.error_code == "duplicate_tool_call"


def test_tool_timeout_is_enforced(tmp_path):
    harness = make_harness(tmp_path)
    registry = ToolRegistry([SleepTool()], max_tool_calls_per_turn=3)
    try:
        result = registry.execute(
            ToolCall(name="sleep_tool", arguments={"seconds": 1.0}),
            user_id="user_001",
            guard=harness.guard,
            settings=harness.settings,
        )
    finally:
        registry.shutdown()
    assert result.ok is False
    assert result.error_code == "tool_timeout"


def test_per_tool_call_limit(tmp_path):
    harness = make_harness(tmp_path)
    registry = ToolRegistry([EchoTool()], max_tool_calls_per_turn=10)
    try:
        results = [
            registry.execute(
                ToolCall(name="echo_tool", arguments={"value": str(index)}),
                user_id="user_001",
                guard=harness.guard,
                settings=harness.settings,
            )
            for index in range(3)
        ]
    finally:
        registry.shutdown()
    assert [result.ok for result in results] == [True, True, False]
    assert results[2].error_code == "tool_call_limit"


def test_all_fifteen_required_tools_are_registered(tmp_path):
    harness = make_harness(tmp_path)
    expected = {
        "search_memories",
        "get_memory_details",
        "suggest_memory_save",
        "suggest_memory_update",
        "search_people",
        "get_person_details",
        "get_relationships",
        "search_places",
        "get_place_details",
        "get_activity_history",
        "search_activities",
        "get_routines",
        "get_routine_history",
        "get_upcoming_events",
        "suggest_reminder",
    }
    assert set(harness.runtime.registry.tool_names) == expected
