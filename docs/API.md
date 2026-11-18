# API and tool reference

## 1. Tool set (15 tools)

Every tool is declared with a Pydantic argument model, one permission and a timeout. The registry rejects unknown tools, invalid arguments, duplicate calls within a turn and calls beyond the per-turn limit.

| Tool | Permission | Arguments (required in **bold**) | Returns |
| --- | --- | --- | --- |
| `search_memories` | `memory.read` | **query** (1–500), `limit` 1–20 (8), `category` | Memory records |
| `get_memory_details` | `memory.read` | **memory_id** | One memory record |
| `suggest_memory_save` | `memory.suggest_create` | **title**, **content**, `category` | Pending suggestion (no write) |
| `suggest_memory_update` | `memory.suggest_update` | **memory_id**, `title`, `content` (at least one change) | Pending suggestion (no write) |
| `search_people` | `people.read` | **query**, `limit` 1–20 | Person records |
| `get_person_details` | `people.read` | **person_id** | Person record |
| `get_relationships` | `people.read` | **person_id** | Person + relationship records |
| `search_places` | `places.read` | **query**, `limit` 1–20 | Place records |
| `get_place_details` | `places.read` | **place_id** | Place record |
| `get_activity_history` | `activities.read` | `date_from`, `date_to`, `limit` | Activity records, newest first |
| `search_activities` | `activities.read` | **query**, `date_from`, `date_to`, `limit` | Activity records |
| `get_routines` | `routines.read` | — | Routine records with schedule hints |
| `get_routine_history` | `routines.read` | **routine_id**, `limit` 1–50 | Routine-event records |
| `get_upcoming_events` | `reminders.read` | `horizon_days` 1–30 (7), `limit` 1–20 | Upcoming reminders |
| `suggest_reminder` | `reminders.suggest_create` | **title**, **due_at** (ISO-8601), `description` | Pending suggestion (no write) |

The four `suggest_*` tools never write. They return a `Suggestion` that the user must approve.

### Tool result shape

```json
{
  "tool": "search_memories",
  "ok": true,
  "data": { "records": [ ... ], "count": 1 }
}
```

Results sent to the model are wrapped:

```
<<<UNTRUSTED_TOOL_RESULT name=search_memories>>>
{ ...json... }
<<<END_UNTRUSTED_TOOL_RESULT>>>
```

## 2. Provider contract

```python
class AIProvider(ABC):
    info: ProviderInfo

    def is_configured(self) -> bool: ...
    @abstractmethod
    def generate(self, request: ProviderRequest) -> ProviderResponse: ...
    @abstractmethod
    def validate_api_key(self, api_key: str | None = None) -> ConnectionTestResult: ...
    @abstractmethod
    def get_available_models(self) -> list[ModelInfo]: ...
    def close(self) -> None: ...
```

`ProviderRequest` / `ProviderResponse` are neutral Pydantic models (`providers/schemas.py`). No vendor objects leave `providers/`.

- Registry: `create_provider(provider_id, api_key=None, model=None, base_url=None, timeout_s=45.0, client=None)`.
- Unknown provider ids raise `ConfigurationError`; they are never guessed.
- Providers map SDK errors into typed `ProviderError` subclasses (`ProviderAuthError`, `ProviderRateLimitError`, `ProviderTimeoutError`, `ProviderNetworkError`, `ProviderUnavailableError`, `UnsupportedModelError`, `ProviderResponseError`).

## 3. Agent core

### `PersonalMemoryAgent`

```python
conversation_id, turn = agent.ask(
    user_id="user_001",
    text="Where is my wallet?",
    settings=settings,
    provider=provider,
    conversation_id=None,
    token=None,
)
```

`AgentTurnResult` contains:

- `text` — grounded, screened answer.
- `evidence` — `grounding` (`recorded|inferred|missing|conflicting`), sources, conflicts, summary.
- `tool_trace` — tool name, ok/error code, record count, duplicate flag, duration.
- `suggestions` — pending suggestions produced by tool calls.
- `rounds`, `usage`, `provider_id`.

### `ContextBuilder.build(...)`

Returns a `ContextBundle` with rendered context, included records, sources, categories, skipped categories, truncation flag, character count and an `InjectionReport`.

## 4. Services

### `AgentService`

| Method | Purpose |
| --- | --- |
| `settings()` / `update_settings(settings)` | Read/validate agent configuration |
| `set_enabled(bool)` / `set_context_mode(mode)` | Toggle assistant and privacy mode |
| `send_message(user_id, text, conversation_id=None, token=None)` | One chat turn; raises typed errors |
| `list_conversations` / `conversation_messages` / `clear_conversation` | History |
| `list_pending_suggestions` / `approve_suggestion` / `reject_suggestion` / `edit_suggestion` | Approval UI |
| `save_api_key` / `delete_api_key` / `masked_api_key` / `credential_store_status` | Key lifecycle |
| `test_connection(...)` / `available_models(...)` / `provider_status()` | Provider settings |
| `grant_full_context_consent` / `withdraw_full_context_consent` / `has_full_context_consent` | Mode B consent |
| `grant_cloud_transcription_consent` / `withdraw_cloud_transcription_consent` | Voice consent |

`ChatOutcome` = `conversation_id`, `turn`, persisted `suggestions`, `provider_id`.

### `SuggestionService`

```python
pending = suggestions.create_from_agent(suggestion)   # status must be pending
suggestions.list_pending(user_id)
suggestions.edit(user_id, id, title=..., description=..., payload_updates={...})
suggestions.approve(user_id, id)   # re-checks write permission, then executor
suggestions.reject(user_id, id)
```

### `ProactiveEngine`

```python
outcome = engine.evaluate(ProactiveEvent(user_id=..., trigger=..., title=...))
```

Triggers: `upcoming_reminder`, `routine_due`, `expected_activity_missing`, `user_event`.
Outcome: `handled`, `suppressed`, `reason`, optional `suggestion`.
No cloud call is made; personal data stays local.

## 5. Models

### `Record`

`id`, `user_id`, `type` (`memory|person|relationship|place|activity|routine|routine_event|reminder`), `title`, `content`, `created_at`, `updated_at`, `source_module`, `metadata`, `flagged_untrusted`.

### `Suggestion`

`id`, `user_id`, `type`, `title`, `description`, `reason`, `payload`, `status`, `conversation_id`, timestamps, execution result.

Statuses: `pending_approval`, `approved`, `rejected`, `completed`, `failed`.

### `SourceRef`

`record_id`, `record_type`, `source_module`, `title`, `timestamp`.

## 6. Permission identifiers

```
memory.read              people.read       places.read
activities.read          routines.read     reminders.read
memory.suggest_create    memory.suggest_update
reminders.suggest_create
```

Host-specific write permissions reused by the executor include `memory.create`, `memory.update`, `reminder.create`, checked by the host's own security layer.

## 7. Errors

All errors inherit `AgentError` and carry a `code` plus `user_message` safe for display. Examples:

| Code | Meaning |
| --- | --- |
| `session_expired` / `authentication_required` | Host session invalid |
| `permission_denied` | Missing permission |
| `missing_api_key` | No key configured |
| `credential_store_unavailable` | DPAPI unavailable |
| `provider_rate_limited` / `provider_timeout` / `provider_unavailable` | Typed provider failures |
| `consent_required` | Mode B consent missing |
| `local_only_unavailable` | Mode C without a local provider |
| `tool_permission_denied` / `invalid_tool_arguments` / `tool_timeout` | Tool failures |
| `tool_rounds_exceeded` | Five-round cap reached |
| `cancelled` | User cancelled |
