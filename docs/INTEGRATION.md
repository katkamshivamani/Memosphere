# Host/team integration guide

`memory_agent` is a library plus a PySide6 UI package. It does not own a database, accounts, permissions or record storage. To integrate it into an existing application, implement the interfaces below and call the composition root.

## 1. What the host must provide

### 1.1 Read services

All methods are **user-scoped**, synchronous, and return plain mappings. Rows must include `id` and `user_id`; timestamps should be ISO-8601 strings. The agent never writes through these services.

| Integration slot | Required methods | Expected rows |
| --- | --- | --- |
| `memories` | `search_memories(user_id, query, filters=None)`, `get_memory(user_id, memory_id)` | `id`, `title`, `content`, `category`, timestamps |
| `people` | `search_people(user_id, query)`, `get_person(user_id, person_id)`, `get_relationships(user_id, person_id)` | `id`, `name`, `relationship`, `notes` |
| `places` | `search_places(user_id, query)`, `get_place_details(user_id, place_id)` | `id`, `name`, `category`, `description` |
| `activities` | `get_activity_history(user_id, date_from=None, date_to=None)`, `search_activities(user_id, query, date_from=None, date_to=None)` | `id`, `name`, `description`, `occurred_at` |
| `routines` | `get_routines(user_id)`, `get_routine_history(user_id, routine_id)` | `id`, `name`, `schedule_hint`, event `status`, `occurred_at` |
| `reminders` | `get_upcoming_reminders(user_id, horizon_days=7)` | `id`, `title`, `description`, `due_at`, `status` |

Only records belonging to `user_id` may be returned. The adapters will accept extra fields but never invent missing ones.

### 1.2 Write path: `SuggestionExecutor`

```python
class SuggestionExecutor(Protocol):
    def execute_suggestion(
        self, user_id: str, suggestion: Suggestion
    ) -> SuggestionExecutionResult: ...
```

The executor **must**:

1. Validate the user's session again.
2. Confirm `suggestion.status in {approved, ...}` (the service only calls it after approval).
3. Re-check the host write permission (`memory.create`, `memory.update`, `reminder.create`, …).
4. Perform the write through the existing service/repository.
5. Return `SuggestionExecutionResult(ok=True, record_id=...)` or `ok=False, message=...`; raise only for exceptional cases.

Never accept model-provided ids or payloads without validation. The payload is user-editable, so validate it like any other form input.

### 1.3 Security services

Implement this protocol and pass it to `PermissionGuard`:

```python
class PermissionChecker(Protocol):
    def validate_session(self, user_id: str) -> bool: ...
    def has_permission(self, user_id: str, permission: str) -> bool: ...
```

`memory_companion.security.auth.AuthService` is a complete reference implementation (Argon2id, expiring in-memory sessions, per-user permissions).

### 1.4 Stores

| Store | Interface | Reference implementation |
| --- | --- | --- |
| Conversations | `ConversationStore` (`create_conversation`, `list_conversations`, `get_conversation`, `list_messages`, `append_message`, `clear`) | `memory_companion.modules.conversation_store` |
| Suggestions | `SuggestionStore` (`save`, `get`, `list`) | `memory_companion.modules.suggestion_store` |
| Settings | `SettingsStore` (`load`, `save`) | `memory_agent.config.JsonSettingsStore` |
| Credentials | `CredentialStore` (`is_available`, `set_secret`, `get_secret`, `delete_secret`) | `DpapiCredentialStore` (Windows) |

## 2. Wiring

```python
from memory_agent.config import JsonSettingsStore
from memory_agent.factory import build_runtime
from memory_agent.integrations.contracts import AgentIntegrations
from memory_agent.security.api_key_manager import ApiKeyManager, create_default_credential_store
from memory_agent.security.consent_manager import ConsentManager
from memory_agent.security.permission_guard import PermissionGuard

integrations = AgentIntegrations(
    memories=memory_service,
    people=people_service,
    places=place_service,
    activities=activity_service,
    routines=routine_service,
    reminders=reminder_service,
    suggestions=suggestion_executor,
)

runtime = build_runtime(
    integrations=integrations,
    guard=PermissionGuard(auth_service),
    consent=ConsentManager(data_dir / "consent.json"),
    settings_store=JsonSettingsStore(data_dir / "agent_settings.json"),
    key_manager=ApiKeyManager(create_default_credential_store(data_dir)),
    conversation_store=conversation_store,
    suggestion_store=suggestion_store,
)
```

`build_runtime()` validates that all required read methods exist and fails fast with `TypeError` otherwise.

The complete reference wiring is `src/memory_companion/composition.py`.

## 3. UI integration

The agent UI is reusable as widgets:

- `memory_agent.ui.chat_window.ChatWindow` — conversation, evidence, suggestions.
- `memory_agent.ui.agent_settings.AgentSettingsWidget` — provider/model/key/mode/consent/voice settings.
- `memory_agent.ui.suggestion_card.SuggestionCard` — approve/reject/edit.
- `memory_agent.ui.voice_controls.VoiceControls` — record, transcribe preview, edit, send.

`ChatController` requires a `FunctionRunner`-style factory; the default runs work on `QThreadPool`. Never call `send_message()` directly on the GUI thread.

`memory_companion.ui.main_window.MainWindow` shows one possible layout with ten pages.

## 4. Database/storage integration

The agent itself never opens a database. If you adapt `memory_companion` as-is:

- Keep SQLCipher, or use an equivalent encrypted store. Never point the app at a plaintext SQLite file; `db/database.py` refuses one.
- Keep API keys out of the database. The reference app stores them in a separate DPAPI container.
- Keep audit events metadata-only (no memory content, no secrets).

## 5. Migration checklist for an existing app

1. Map your existing services to the seven read protocols (thin wrappers are fine).
2. Implement `SuggestionExecutor` against your existing write services.
3. Implement `PermissionChecker` against your existing auth.
4. Ensure every returned row is scoped to the authenticated `user_id`.
5. Add conversation, suggestion, settings and credential stores.
6. Add the nine agent permission categories to your permission model.
7. Place the chat/settings widgets in your UI; route work through `QThreadPool`.
8. Run the offline suite with adapters that wrap your services, then add live provider tests with your own key.

## 6. Things the agent deliberately does not do

- No direct SQL, ORM, filesystem or OS access.
- No writes through read services.
- No background monitoring loop; the host schedules proactive events.
- No knowledge of your user table or session format beyond `PermissionChecker`.
- No vendor SDK usage outside `providers/`.
