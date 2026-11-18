"""Composition root for the agent runtime.

The UI and tests both build the runtime here, so the wiring is reviewed in one
place.  All dependencies are injected: no global singletons, no hidden database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from memory_agent.config import SettingsStore
from memory_agent.core.agent import PersonalMemoryAgent
from memory_agent.core.context_builder import ContextBuilder, ContextLedger
from memory_agent.core.conversation import ConversationManager, ConversationStore
from memory_agent.core.orchestrator import Orchestrator
from memory_agent.integrations.contracts import AgentIntegrations
from memory_agent.integrations.memory_adapter import (
    ActivityAdapter,
    MemoryAdapter,
    PeopleAdapter,
    PlaceAdapter,
    ReminderAdapter,
    RoutineAdapter,
)
from memory_agent.security.api_key_manager import ApiKeyManager
from memory_agent.security.consent_manager import ConsentManager
from memory_agent.security.data_filter import PromptInjectionDetector
from memory_agent.security.permission_guard import PermissionGuard
from memory_agent.services.agent_service import AgentService
from memory_agent.services.reminder_service import ProactiveEngine
from memory_agent.services.suggestion_service import SuggestionService, SuggestionStore
from memory_agent.tools.activity_tools import build_activity_tools
from memory_agent.tools.memory_tools import build_memory_tools
from memory_agent.tools.people_tools import build_people_tools
from memory_agent.tools.places_tools import build_places_tools
from memory_agent.tools.registry import ToolRegistry
from memory_agent.tools.reminder_tools import build_reminder_tools
from memory_agent.tools.routine_tools import build_routine_tools


@dataclass
class AgentRuntime:
    """Fully wired agent components."""

    service: AgentService
    agent: PersonalMemoryAgent
    orchestrator: Orchestrator
    registry: ToolRegistry
    context_builder: ContextBuilder
    conversations: ConversationManager
    suggestions: SuggestionService
    proactive: ProactiveEngine
    guard: PermissionGuard
    key_manager: ApiKeyManager
    consent: ConsentManager
    settings_store: SettingsStore


def build_runtime(
    *,
    integrations: AgentIntegrations,
    guard: PermissionGuard,
    consent: ConsentManager,
    settings_store: SettingsStore,
    key_manager: ApiKeyManager,
    conversation_store: ConversationStore,
    suggestion_store: SuggestionStore,
    max_tool_calls: Optional[int] = None,
) -> AgentRuntime:
    """Wire adapters, tools, orchestration and services together."""
    integrations.validate()

    settings = settings_store.load()

    memories = MemoryAdapter(integrations.memories)
    people = PeopleAdapter(integrations.people)
    places = PlaceAdapter(integrations.places)
    activities = ActivityAdapter(integrations.activities)
    routines = RoutineAdapter(integrations.routines)
    reminders = ReminderAdapter(integrations.reminders)

    detector = PromptInjectionDetector()
    context_builder = ContextBuilder(
        memories=memories,
        people=people,
        places=places,
        activities=activities,
        routines=routines,
        reminders=reminders,
        guard=guard,
        consent=consent,
        detector=detector,
        ledger=ContextLedger(),
    )

    tools = []
    tools.extend(build_memory_tools(memories))
    tools.extend(build_people_tools(people))
    tools.extend(build_places_tools(places))
    tools.extend(build_activity_tools(activities))
    tools.extend(build_routine_tools(routines))
    tools.extend(build_reminder_tools(reminders))

    registry = ToolRegistry(
        tools,
        max_tool_calls_per_turn=max_tool_calls or settings.max_tool_calls_per_turn,
    )

    orchestrator = Orchestrator(
        registry=registry,
        context_builder=context_builder,
        guard=guard,
        classifier=None,
        assessor=None,
    )

    conversations = ConversationManager(conversation_store)
    agent = PersonalMemoryAgent(
        orchestrator=orchestrator,
        conversations=conversations,
        guard=guard,
    )

    suggestion_service = SuggestionService(
        store=suggestion_store,
        executor=integrations.suggestions,
        guard=guard,
    )

    service = AgentService(
        agent=agent,
        conversations=conversations,
        settings_store=settings_store,
        key_manager=key_manager,
        consent=consent,
        suggestions=suggestion_service,
        guard=guard,
    )

    proactive = ProactiveEngine(
        reminders=reminders,
        routines=routines,
        suggestions=suggestion_service,
        settings_store=settings_store,
        guard=guard,
    )

    return AgentRuntime(
        service=service,
        agent=agent,
        orchestrator=orchestrator,
        registry=registry,
        context_builder=context_builder,
        conversations=conversations,
        suggestions=suggestion_service,
        proactive=proactive,
        guard=guard,
        key_manager=key_manager,
        consent=consent,
        settings_store=settings_store,
    )
