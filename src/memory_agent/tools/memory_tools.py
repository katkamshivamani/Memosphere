"""Memory tools: search, details, and *suggestion-only* save/update."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memory_agent.models.suggestion import SuggestionType
from memory_agent.models.tool_result import ToolResult
from memory_agent.security.permissions import Permission
from memory_agent.tools.base import BaseTool, ToolContext, records_result
from memory_agent.integrations.memory_adapter import MemoryAdapter


class SearchMemoriesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500, description="What to look for, in the user's words.")
    limit: int = Field(default=8, ge=1, le=20, description="Maximum number of memories to return.")
    category: Optional[str] = Field(
        default=None, max_length=60, description="Optional category filter, e.g. 'objects' or 'documents'."
    )


class SearchMemoriesTool(BaseTool[SearchMemoriesArgs]):
    name = "search_memories"
    description = (
        "Search the user's own saved memories by keywords. Use this for questions "
        "about where something is, what was written down, or past personal notes. "
        "Returns matching records with ids and timestamps."
    )
    permission = Permission.MEMORY_READ
    args_model = SearchMemoriesArgs
    max_calls_per_turn = 3

    def __init__(self, adapter: MemoryAdapter) -> None:
        super().__init__()
        self._adapter = adapter

    def _run(self, ctx: ToolContext, args: SearchMemoriesArgs) -> ToolResult:
        filters = {"category": args.category} if args.category else None
        records = self._adapter.search(ctx.user_id, args.query, filters)[: args.limit]
        note = "" if records else "No saved memories matched this search."
        return records_result(
            ctx.call_id,
            self.name,
            records,
            note=note,
            max_chars=ctx.settings.max_record_chars,
        )


class GetMemoryDetailsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(min_length=1, max_length=80, description="Exact memory id from a search result.")


class GetMemoryDetailsTool(BaseTool[GetMemoryDetailsArgs]):
    name = "get_memory_details"
    description = (
        "Fetch one saved memory by its exact id. Use after search_memories when the "
        "user needs the full text or details of a specific record."
    )
    permission = Permission.MEMORY_READ
    args_model = GetMemoryDetailsArgs
    max_calls_per_turn = 4

    def __init__(self, adapter: MemoryAdapter) -> None:
        super().__init__()
        self._adapter = adapter

    def _run(self, ctx: ToolContext, args: GetMemoryDetailsArgs) -> ToolResult:
        record = self._adapter.get(ctx.user_id, args.memory_id)
        if record is None:
            return records_result(
                ctx.call_id,
                self.name,
                [],
                note="No memory with that id exists for this user.",
            )
        return records_result(
            ctx.call_id,
            self.name,
            [record],
            max_chars=ctx.settings.max_record_chars * 2,
        )


class SuggestMemorySaveArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=4000)
    category: Optional[str] = Field(default=None, max_length=60)
    reason: str = Field(default="", max_length=500, description="Why this memory would be useful.")

    @model_validator(mode="after")
    def _no_secret_like_content(self) -> "SuggestMemorySaveArgs":
        from memory_agent.security.data_filter import contains_secret

        if contains_secret(self.content) or contains_secret(self.title):
            raise ValueError("Suggested memory contains credential-like text")
        return self


class SuggestMemorySaveTool(BaseTool[SuggestMemorySaveArgs]):
    name = "suggest_memory_save"
    description = (
        "Prepare a suggestion to SAVE a new memory. This never writes data: it "
        "returns a suggestion the user must review and approve. Use it only when "
        "the user asks to remember something or agrees that it is worth saving."
    )
    permission = Permission.MEMORY_SUGGEST_CREATE
    args_model = SuggestMemorySaveArgs
    produces_suggestion = True
    max_calls_per_turn = 2

    def _run(self, ctx: ToolContext, args: SuggestMemorySaveArgs) -> ToolResult:
        suggestion = ctx.suggestion(
            SuggestionType.SAVE_MEMORY,
            title=args.title,
            description=args.content,
            reason=args.reason or "You asked to remember this.",
            payload={
                "title": args.title,
                "content": args.content,
                "category": args.category or "general",
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
                "note": "Nothing was saved. The user must approve this suggestion in the app first.",
            },
            suggestion=suggestion,
        )


class SuggestMemoryUpdateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(min_length=1, max_length=80)
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    content: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    reason: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _at_least_one_change(self) -> "SuggestMemoryUpdateArgs":
        if not self.title and not self.content:
            raise ValueError("Provide a new title and/or new content")
        return self


class SuggestMemoryUpdateTool(BaseTool[SuggestMemoryUpdateArgs]):
    name = "suggest_memory_update"
    description = (
        "Prepare a suggestion to UPDATE an existing memory. This never writes data: "
        "the user must review and approve it. Requires the exact memory id."
    )
    permission = Permission.MEMORY_SUGGEST_UPDATE
    args_model = SuggestMemoryUpdateArgs
    produces_suggestion = True
    max_calls_per_turn = 2

    def _run(self, ctx: ToolContext, args: SuggestMemoryUpdateArgs) -> ToolResult:
        updates: dict[str, Any] = {"memory_id": args.memory_id}
        if args.title:
            updates["title"] = args.title
        if args.content:
            updates["content"] = args.content
        suggestion = ctx.suggestion(
            SuggestionType.UPDATE_MEMORY,
            title=f"Update memory: {args.title or args.memory_id}",
            description=args.content or "",
            reason=args.reason or "The recorded information appears out of date.",
            payload=updates,
        )
        return ToolResult(
            call_id=ctx.call_id,
            tool=self.name,
            ok=True,
            data={
                "suggestion_prepared": True,
                "suggestion_id": suggestion.id,
                "status": suggestion.status.value,
                "note": "Nothing was changed. The user must approve this suggestion in the app first.",
            },
            suggestion=suggestion,
        )


def build_memory_tools(adapter: MemoryAdapter) -> list[BaseTool]:
    return [
        SearchMemoriesTool(adapter),
        GetMemoryDetailsTool(adapter),
        SuggestMemorySaveTool(),
        SuggestMemoryUpdateTool(),
    ]
