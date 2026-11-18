"""Routine understanding tools."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from memory_agent.models.tool_result import ToolResult
from memory_agent.security.permissions import Permission
from memory_agent.tools.base import BaseTool, ToolContext, records_result
from memory_agent.integrations.memory_adapter import RoutineAdapter


class GetRoutinesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GetRoutinesTool(BaseTool[GetRoutinesArgs]):
    name = "get_routines"
    description = (
        "List the user's saved daily or weekly routines (for example morning "
        "medication or an evening walk), including schedule hints."
    )
    permission = Permission.ROUTINES_READ
    args_model = GetRoutinesArgs
    max_calls_per_turn = 2

    def __init__(self, adapter: RoutineAdapter) -> None:
        super().__init__()
        self._adapter = adapter

    def _run(self, ctx: ToolContext, args: GetRoutinesArgs) -> ToolResult:
        records = self._adapter.routines(ctx.user_id)
        return records_result(
            ctx.call_id,
            self.name,
            records,
            note="" if records else "No routines are saved.",
            max_chars=ctx.settings.max_record_chars,
        )


class GetRoutineHistoryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    routine_id: str = Field(min_length=1, max_length=80)
    limit: int = Field(default=20, ge=1, le=50)


class GetRoutineHistoryTool(BaseTool[GetRoutineHistoryArgs]):
    name = "get_routine_history"
    description = (
        "List recorded completions/history for one routine. Use this to answer "
        "'did I do my routine today' only from actual records."
    )
    permission = Permission.ROUTINES_READ
    args_model = GetRoutineHistoryArgs
    max_calls_per_turn = 3

    def __init__(self, adapter: RoutineAdapter) -> None:
        super().__init__()
        self._adapter = adapter

    def _run(self, ctx: ToolContext, args: GetRoutineHistoryArgs) -> ToolResult:
        records = self._adapter.history(ctx.user_id, args.routine_id)[: args.limit]
        note = "" if records else (
            "No routine history is recorded. This does not prove the routine was missed."
        )
        return records_result(
            ctx.call_id,
            self.name,
            records,
            note=note,
            max_chars=ctx.settings.max_record_chars,
        )


def build_routine_tools(adapter: RoutineAdapter) -> list[BaseTool]:
    return [GetRoutinesTool(adapter), GetRoutineHistoryTool(adapter)]
