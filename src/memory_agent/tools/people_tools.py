"""People and relationship tools."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from memory_agent.models.tool_result import ToolResult
from memory_agent.security.permissions import Permission
from memory_agent.tools.base import BaseTool, ToolContext, records_result
from memory_agent.integrations.memory_adapter import PeopleAdapter


class SearchPeopleArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=200, description="A name, relationship or detail to search for.")
    limit: int = Field(default=8, ge=1, le=20)


class SearchPeopleTool(BaseTool[SearchPeopleArgs]):
    name = "search_people"
    description = (
        "Search the user's saved people (family, friends, carers, doctors). "
        "Returns names, relationships and notes with ids."
    )
    permission = Permission.PEOPLE_READ
    args_model = SearchPeopleArgs
    max_calls_per_turn = 3

    def __init__(self, adapter: PeopleAdapter) -> None:
        super().__init__()
        self._adapter = adapter

    def _run(self, ctx: ToolContext, args: SearchPeopleArgs) -> ToolResult:
        records = self._adapter.search(ctx.user_id, args.query)[: args.limit]
        return records_result(
            ctx.call_id,
            self.name,
            records,
            note="" if records else "No saved people matched this search.",
            max_chars=ctx.settings.max_record_chars,
        )


class GetPersonDetailsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person_id: str = Field(min_length=1, max_length=80)


class GetPersonDetailsTool(BaseTool[GetPersonDetailsArgs]):
    name = "get_person_details"
    description = "Fetch one saved person by their exact id, including relationship and notes."
    permission = Permission.PEOPLE_READ
    args_model = GetPersonDetailsArgs
    max_calls_per_turn = 3

    def __init__(self, adapter: PeopleAdapter) -> None:
        super().__init__()
        self._adapter = adapter

    def _run(self, ctx: ToolContext, args: GetPersonDetailsArgs) -> ToolResult:
        record = self._adapter.get(ctx.user_id, args.person_id)
        return records_result(
            ctx.call_id,
            self.name,
            [record] if record else [],
            note="" if record else "No person with that id exists for this user.",
            max_chars=ctx.settings.max_record_chars,
        )


class GetRelationshipsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person_id: str = Field(min_length=1, max_length=80)


class GetRelationshipsTool(BaseTool[GetRelationshipsArgs]):
    name = "get_relationships"
    description = (
        "Get the recorded relationships for a person (for example 'daughter', "
        "'doctor') together with the person's own record."
    )
    permission = Permission.PEOPLE_READ
    args_model = GetRelationshipsArgs
    max_calls_per_turn = 3

    def __init__(self, adapter: PeopleAdapter) -> None:
        super().__init__()
        self._adapter = adapter

    def _run(self, ctx: ToolContext, args: GetRelationshipsArgs) -> ToolResult:
        relationships, person = self._adapter.relationships(ctx.user_id, args.person_id)
        if person is None:
            return records_result(
                ctx.call_id,
                self.name,
                [],
                note="No person with that id exists for this user.",
            )
        records = ([person] if person else []) + relationships
        note = "" if relationships else "No relationship details are recorded for this person."
        return records_result(
            ctx.call_id,
            self.name,
            records,
            note=note,
            extra={"person_id": args.person_id, "relationship_count": len(relationships)},
            max_chars=ctx.settings.max_record_chars,
        )


def build_people_tools(adapter: PeopleAdapter) -> list[BaseTool]:
    return [SearchPeopleTool(adapter), GetPersonDetailsTool(adapter), GetRelationshipsTool(adapter)]
