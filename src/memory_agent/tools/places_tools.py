"""Place and object-location tools."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from memory_agent.models.tool_result import ToolResult
from memory_agent.security.permissions import Permission
from memory_agent.tools.base import BaseTool, ToolContext, records_result
from memory_agent.integrations.memory_adapter import PlaceAdapter


class SearchPlacesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=8, ge=1, le=20)


class SearchPlacesTool(BaseTool[SearchPlacesArgs]):
    name = "search_places"
    description = (
        "Search saved places (rooms, buildings, clinics, shops). Use for questions "
        "about where something is or where an event happened."
    )
    permission = Permission.PLACES_READ
    args_model = SearchPlacesArgs
    max_calls_per_turn = 3

    def __init__(self, adapter: PlaceAdapter) -> None:
        super().__init__()
        self._adapter = adapter

    def _run(self, ctx: ToolContext, args: SearchPlacesArgs) -> ToolResult:
        records = self._adapter.search(ctx.user_id, args.query)[: args.limit]
        return records_result(
            ctx.call_id,
            self.name,
            records,
            note="" if records else "No saved places matched this search.",
            max_chars=ctx.settings.max_record_chars,
        )


class GetPlaceDetailsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    place_id: str = Field(min_length=1, max_length=80)


class GetPlaceDetailsTool(BaseTool[GetPlaceDetailsArgs]):
    name = "get_place_details"
    description = "Fetch one saved place by its exact id."
    permission = Permission.PLACES_READ
    args_model = GetPlaceDetailsArgs
    max_calls_per_turn = 3

    def __init__(self, adapter: PlaceAdapter) -> None:
        super().__init__()
        self._adapter = adapter

    def _run(self, ctx: ToolContext, args: GetPlaceDetailsArgs) -> ToolResult:
        record = self._adapter.get(ctx.user_id, args.place_id)
        return records_result(
            ctx.call_id,
            self.name,
            [record] if record else [],
            note="" if record else "No place with that id exists for this user.",
            max_chars=ctx.settings.max_record_chars,
        )


def build_places_tools(adapter: PlaceAdapter) -> list[BaseTool]:
    return [SearchPlacesTool(adapter), GetPlaceDetailsTool(adapter)]
