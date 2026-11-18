"""Composition root for the host application.

Builds the encrypted database, authentication, application services and the
Personal Memory Agent runtime.  Nothing here depends on PySide6, so tests and
headless tools can reuse the exact same wiring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Optional

from memory_agent.config import JsonSettingsStore
from memory_agent.factory import build_runtime
from memory_agent.integrations.contracts import AgentIntegrations
from memory_agent.security.api_key_manager import (
    ApiKeyManager,
    CredentialStore,
    create_default_credential_store,
)
from memory_agent.security.consent_manager import ConsentManager
from memory_agent.security.permission_guard import PermissionGuard
from memory_agent.services.suggestion_service import SuggestionService

from memory_companion.config import AppPaths, AppSettings
from memory_companion.db.database import Database, EncryptionStatus
from memory_companion.modules.activity_service import ActivityService
from memory_companion.modules.audit import AuditService
from memory_companion.modules.conversation_store import SqlConversationStore
from memory_companion.modules.memory_service import MemoryService
from memory_companion.modules.people_service import PeopleService
from memory_companion.modules.place_service import PlaceService
from memory_companion.modules.reminder_service import ReminderService
from memory_companion.modules.routine_service import RoutineService
from memory_companion.modules.suggestion_executor import SuggestionExecutorImpl
from memory_companion.modules.suggestion_store import SqlSuggestionStore
from memory_companion.security.auth import AuthService

logger = logging.getLogger("memory_companion.composition")


@dataclass
class AppContext:
    paths: AppPaths
    app_settings: AppSettings
    db: Database
    encryption: EncryptionStatus
    auth: AuthService
    audit: AuditService
    memories: MemoryService
    people: PeopleService
    places: PlaceService
    activities: ActivityService
    routines: RoutineService
    reminders: ReminderService
    credential_store: CredentialStore
    key_manager: ApiKeyManager
    consent: ConsentManager
    suggestion_service: SuggestionService
    agent_runtime: object  # AgentRuntime (avoid a heavy import cycle in type hints)

    def close(self) -> None:
        try:
            getattr(self.agent_runtime, "registry").shutdown()
        except Exception:
            pass
        self.db.close()


def setup_logging(paths: AppPaths, level: int = logging.INFO) -> None:
    """Structured-ish console + rotating file logging with no content logging."""
    from logging.handlers import RotatingFileHandler

    paths.ensure()
    root = logging.getLogger()
    root.setLevel(level)
    if any(getattr(handler, "_memory_companion", False) for handler in root.handlers):
        return
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
    )
    file_handler = RotatingFileHandler(
        paths.logs_dir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler._memory_companion = True  # type: ignore[attr-defined]
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console._memory_companion = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)
    root.addHandler(console)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def build_context(
    *,
    paths: Optional[AppPaths] = None,
    credential_store: Optional[CredentialStore] = None,
    session_ttl: timedelta = timedelta(minutes=45),
    clock=None,
) -> AppContext:
    paths = paths or AppPaths.default()
    paths.ensure()

    credential_store = credential_store or create_default_credential_store(paths.data_dir)
    db = Database(paths.database_path, credential_store)
    encryption = db.initialize()

    audit = AuditService(db)
    auth_kwargs = {"session_ttl": session_ttl}
    if clock is not None:
        auth_kwargs["clock"] = clock
    auth = AuthService(db, **auth_kwargs)

    memories = MemoryService(db, audit)
    people = PeopleService(db, audit)
    places = PlaceService(db, audit)
    activities = ActivityService(db, audit)
    routines = RoutineService(db, audit)
    reminders = ReminderService(db, audit)

    executor = SuggestionExecutorImpl(
        auth=auth,
        memories=memories,
        reminders=reminders,
        activities=activities,
        routines=routines,
        audit=audit,
    )
    conversation_store = SqlConversationStore(db)
    suggestion_store = SqlSuggestionStore(db)

    key_manager = ApiKeyManager(credential_store)
    consent = ConsentManager(
        paths.consent_path,
        audit_hook=lambda action, meta: audit.log(
            action=action, user_id=None, actor="consent", target_type="consent", metadata=meta
        ),
    )
    settings_store = JsonSettingsStore(paths.agent_settings_path)
    guard = PermissionGuard(auth)

    runtime = build_runtime(
        integrations=AgentIntegrations(
            memories=memories,
            people=people,
            places=places,
            activities=activities,
            routines=routines,
            reminders=reminders,
            suggestions=executor,
        ),
        guard=guard,
        consent=consent,
        settings_store=settings_store,
        key_manager=key_manager,
        conversation_store=conversation_store,
        suggestion_store=suggestion_store,
    )

    app_settings = AppSettings(paths.app_settings_path)
    logger.info("Application context ready. %s", encryption.describe())

    return AppContext(
        paths=paths,
        app_settings=app_settings,
        db=db,
        encryption=encryption,
        auth=auth,
        audit=audit,
        memories=memories,
        people=people,
        places=places,
        activities=activities,
        routines=routines,
        reminders=reminders,
        credential_store=credential_store,
        key_manager=key_manager,
        consent=consent,
        suggestion_service=runtime.suggestions,
        agent_runtime=runtime,
    )


def build_test_context(tmp_dir: Path):
    """Helper for integration tests: isolated data dir + in-memory credentials."""
    from memory_agent.security.api_key_manager import InMemoryCredentialStore

    paths = AppPaths(data_dir=Path(tmp_dir))
    return build_context(paths=paths, credential_store=InMemoryCredentialStore())
