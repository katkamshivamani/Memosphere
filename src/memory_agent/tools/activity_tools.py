"""Activity history tools."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memory_agent.models.tool_result import ToolResult
from memory_agent.security.permissions import Permission
from memory_agent.tools.base import BaseTool, ToolContext, parse_iso_datetime, records_result
from memory_agent.integrations.memory_adapter import ActivityAdapter


class GetActivityHistoryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: Optional[str] = Field(
        default=None, description="Inclusive ISO date/datetime lower bound, e.g. 2026-11-17."
    )
    date_to: Optional[str] = Field(
        default=None, description="Inclusive ISO date/datetime upper bound."
    )
    limit: int = Field(default=15, ge=1, le=30)

    @model_validator(mode="after")
    def _check_range(self) -> "GetActivityHistoryArgs":
        if self.date_from and self.date_to:
            if parse_iso_datetime(self.date_from, "date_from") > parse_iso_datetime(self.date_to, "date_to"):
                raise ValueError("date_from must be before date_to")
        return self


class GetActivityHistoryTool(BaseTool[GetActivityHistoryArgs]):
    name = "get_activity_history"
    description = (
        "List the user's recorded activities in a date range, newest first. Use "
        "for 'what did I do today/yesterday' questions. Absence of a record does "
        "not prove an activity did not happen."
    )
    permission = Permission.ACTIVITIES_READ
    args_model = GetActivityHistoryArgs
    max_calls_per_turn = 3

    def __init__(self, adapter: ActivityAdapter) -> None:
        super().__init__()
        self._adapter = adapter

    def _run(self, ctx: ToolContext, args: GetActivityHistoryArgs) -> ToolResult:
        date_from = parse_iso_datetime(args.date_from, "date_from") if args.date_from else None
        date_to = parse_iso_datetime(args.date_to, "date_to") if args.date_to else None
        records = self._adapter.history(ctx.user_id, date_from, date_to)[: args.limit]
        note = "" if records else (
            "No activities are recorded for that period. This means nothing is recorded, "
            "not that nothing happened."
        )
        return records_result(
            ctx.call_id,
            self.name,
            records,
            note=note,
            max_chars=ctx.settings.max_record_chars,
        )


class SearchActivitiesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=300)
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = Field(default=15, ge=1, le=30)


class SearchActivitiesTool(BaseTool[SearchActivitiesArgs]):
    name = "search_activities"
    description = (
        "Search the user's recorded activities by keyword (for example 'walk', "
        "'dentist', 'medication'), optionally limited to a date range."
    )
    permission = Permission.ACTIVITIES_READ
    args_model = SearchActivitiesArgs
    max_calls_per_turn = 3

    def __init__(self, adapter: ActivityAdapter) -> None:
        super().__init__()
        self._adapter = adapter

    def _run(self, ctx: ToolContext, args: SearchActivitiesArgs) -> ToolResult:
        date_from = parse_iso_datetime(args.date_from, "date_from") if args.date_from else None
        date_to = parse_iso_datetime(args.date_to, "date_to") if args.date_to else None
        records = self._adapter.search(ctx.user_id, args.query, date_from, date_to)[: args.limit]
        note = "" if records else (
            "No recorded activities matched. Missing records do not confirm that "
            "something did not happen."
        )
        return records_result(
            ctx.call_id,
            self.name,
            records,
            note=note,
            max_chars=ctx.settings.max_record_chars,
        )


def build_activity_tools(adapter: ActivityAdapter) -> list[BaseTool]:
    return [GetActivityHistoryTool(adapter), SearchActivitiesTool(adapter)]
