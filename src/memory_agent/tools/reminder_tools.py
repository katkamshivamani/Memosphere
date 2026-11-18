"""Reminder visibility and reminder *suggestion* tools."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from memory_agent.models.suggestion import SuggestionType
from memory_agent.models.tool_result import ToolResult
from memory_agent.security.permissions import Permission
from memory_agent.tools.base import BaseTool, ToolContext, records_result
from memory_agent.integrations.memory_adapter import ReminderAdapter


class GetUpcomingEventsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    horizon_days: int = Field(default=7, ge=1, le=30, description="How many days ahead to look.")
    limit: int = Field(default=10, ge=1, le=20)


class GetUpcomingEventsTool(BaseTool[GetUpcomingEventsArgs]):
    name = "get_upcoming_events"
    description = (
        "List upcoming reminders and scheduled events for the user. Use before "
        "suggesting a reminder so the same reminder is not duplicated."
    )
    permission = Permission.REMINDERS_READ
    args_model = GetUpcomingEventsArgs
    max_calls_per_turn = 3

    def __init__(self, adapter: ReminderAdapter) -> None:
        super().__init__()
        self._adapter = adapter

    def _run(self, ctx: ToolContext, args: GetUpcomingEventsArgs) -> ToolResult:
        records = self._adapter.upcoming(ctx.user_id, args.horizon_days)[: args.limit]
        return records_result(
            ctx.call_id,
            self.name,
            records,
            note="" if records else "No upcoming reminders are scheduled in that window.",
            extra={"horizon_days": args.horizon_days},
            max_chars=ctx.settings.max_record_chars,
        )


class SuggestReminderArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    due_at: str = Field(
        min_length=10,
        max_length=40,
        description="ISO-8601 date/time with timezone, for example 2026-11-21T10:30:00+05:30.",
    )
    reason: str = Field(default="", max_length=500)


class SuggestReminderTool(BaseTool[SuggestReminderArgs]):
    name = "suggest_reminder"
    description = (
        "Prepare a suggestion to create a reminder. This never creates anything: "
        "the user must review and approve it. Check get_upcoming_events first to "
        "avoid suggesting a duplicate reminder."
    )
    permission = Permission.REMINDERS_SUGGEST_CREATE
    args_model = SuggestReminderArgs
    produces_suggestion = True
    max_calls_per_turn = 2

    def _run(self, ctx: ToolContext, args: SuggestReminderArgs) -> ToolResult:
        suggestion = ctx.suggestion(
            SuggestionType.CREATE_REMINDER,
            title=args.title,
            description=args.description,
            reason=args.reason or "This may help you remember an upcoming event.",
            payload={
                "title": args.title,
                "description": args.description,
                "due_at": args.due_at,
                "source": "agent_suggestion",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return ToolResult(
            call_id=ctx.call_id,
            tool=self.name,
            ok=True,
            data={
                "suggestion_prepared": True,
                "suggestion_id": suggestion.id,
                "status": suggestion.status.value,
                "note": "No reminder was created. The user must approve this suggestion first.",
            },
            suggestion=suggestion,
        )


def build_reminder_tools(adapter: ReminderAdapter) -> list[BaseTool]:
    return [GetUpcomingEventsTool(adapter), SuggestReminderTool()]
