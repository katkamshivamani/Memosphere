# Architecture

## 1. Goals that shaped the design

1. **The model reasons; the application acts.** The model can only request allow-listed tools and propose suggestions. Code validates every request and performs every read/write.
2. **No separate memory database.** The agent reuses the host application's user-scoped services. `memory_companion` is the reference host.
3. **Evidence before answers.** Retrieved records drive the final answer and are shown as sources. Missing evidence produces an honest "not recorded" answer.
4. **Privacy is enforced below the UI.** Context mode, consent, permission checks, redaction and untrusted-data wrapping happen in code, not only in the prompt.
5. **Provider independence.** Agent core imports only `AIProvider` and neutral Pydantic schemas.

## 2. Layers

```
┌────────────────────────────────────────────────────────────────────┐
│ UI (PySide6)                                                       │
│  memory_companion.ui: login, 10 pages, approval cards, privacy page│
│  memory_agent.ui: chat window, settings, voice controls, workers   │
└───────────────▲────────────────────────────────────────────────────┘
                │ Qt signals / queued workers (no network on GUI thread)
┌───────────────┴────────────────────────────────────────────────────┐
│ Services                                                           │
│  AgentService       chat turns, settings, consent, credentials      │
│  SuggestionService  pending → approved → completed/failed           │
│  ProactiveEngine    local, deterministic proactive suggestions      │
└───────────────▲────────────────────────────────────────────────────┘
                │
┌───────────────┴────────────────────────────────────────────────────┐
│ Agent core                                                         │
│  PersonalMemoryAgent → Orchestrator → ToolRegistry → 15 tools       │
│  IntentClassifier (local)  ContextBuilder  EvidenceAssessor         │
│  ConversationManager (history, persistence via host store)          │
└───────────────▲────────────────────────────────────────────────────┘
                │ neutral ProviderRequest / ProviderResponse
┌───────────────┴────────────────────────────────────────────────────┐
│ Providers                                                          │
│  GeminiProvider   OpenAIProvider   LocalProvider                   │
│  registry.py (the only place that knows concrete classes)          │
└───────────────▲────────────────────────────────────────────────────┘
                │ read-only protocols; no write methods
┌───────────────┴────────────────────────────────────────────────────┐
│ Host integration                                                   │
│  AgentIntegrations (7 services) + SuggestionExecutor               │
│  Adapters → normalized Record objects (no invented data)           │
└───────────────▲────────────────────────────────────────────────────┘
                │
┌───────────────┴────────────────────────────────────────────────────┐
│ Reference host application (memory_companion)                      │
│  SQLCipher database, Argon2id auth, permissions, audit, all modules │
└────────────────────────────────────────────────────────────────────┘
```

## 3. One chat turn

1. `AgentService.send_message()` checks session, enabled state, consent for Mode B, and local-provider presence for Mode C.
2. The provider is built from settings and the DPAPI-backed key. It is always closed in `finally`.
3. `PersonalMemoryAgent.ask()` loads/creates a conversation, appends the user message, and calls the orchestrator.
4. `IntentClassifier` (rules only) chooses the categories that may be retrieved.
5. `ContextBuilder` checks permissions per category, applies the context mode, redacts secrets, wraps records as untrusted data, enforces character/record limits, and records injection findings.
6. The orchestrator builds a system prompt (policy + mode note + grounding rules) and a user message containing the question and authorized context.
7. Each round: provider response → tool calls → registry validation → permission check → adapter read → normalized `ToolResult`. Tool payloads are wrapped in `<<<UNTRUSTED_TOOL_RESULT>>>` markers for the model.
8. After at most five rounds, a final answer is requested with tools disabled if the budget is exhausted.
9. `EvidenceAssessor` computes grounding from tool results and enforces it: replaces unsupported personal claims, labels inferences/conflicts, adds medical disclaimers, and rewrites false write claims.
10. Output is redacted, length-limited, and returned with sources, grounding, tool trace and suggestions. History is persisted; suggestions are persisted as pending.

### Tool loop state machine

```
START ──cancel──► CANCELLED
  │
  ├─ len(history) > limit ─► refuse (no provider call)
  │
  ▼
ROUND 1..5 ──provider error──► ERROR (typed, user-safe message)
  │        └─rate limit/timeout──► bounded retry (max attempts)
  │
  ├─ no tool calls ─► ASSESS ─► ENFORCE ─► SCREEN ─► DONE
  └─ tool calls ─► execute (validate → permission → timeout → result)
                     │
                     └─ last round ─► tools-off request ─► ASSESS … DONE
```

## 4. Key components

| Component | Responsibility | Notable guarantees |
| --- | --- | --- |
| `core/orchestrator.py` | Bounded tool loop, retries, cancellation, grounding | Hard cap 5 rounds; tool payload wrapping; response screening |
| `core/context_builder.py` | Category selection, consent, redaction, budgets | Mode A/B/C enforcement; injection report; deterministic |
| `core/confidence.py` | Grounding assessment and answer enforcement | Four documented states; no numeric confidence |
| `core/intent.py` | Rule-based intent/category selection | Local and deterministic; no cloud call |
| `tools/registry.py` | Tool lookup, limits, duplicate protection, timeouts | Unknown tools rejected; per-turn caps |
| `tools/base.py` | Schema validation, permission gate, result helpers | Every tool declares one permission |
| `security/permission_guard.py` | Session and permission adapter | Fails closed; never owns auth |
| `security/api_key_manager.py` | DPAPI key lifecycle | No plaintext fallback; masked display only |
| `security/consent_manager.py` | Append-only consent records | Separate scope for full context and cloud audio |
| `security/data_filter.py` | Secret detection/redaction, injection screening | Applied to context, tool payloads, answers, errors |
| `providers/*` | Vendor SDK isolation | Only neutral models cross the boundary |
| `services/suggestion_service.py` | Approval lifecycle | Agent-created suggestions must be pending |
| `services/reminder_service.py` | Proactive event evaluation | Local only; quiet hours; dedupe; careful wording |
| `voice/*` | Optional STT/TTS | In-memory audio; consent for cloud STT |

## 5. Suggestion lifecycle

```
agent tool call suggest_*        ← only creates data
        │
        ▼
pending_approval ──reject──► rejected
        │
        ├──edit (still pending_approval)
        │
        └──approve (user action)
                │ re-checks session + write permission
                ▼
          host SuggestionExecutor
                │  re-checks approval status + permissions
                ├─ success ─► completed
                └─ failure ─► failed
```

The agent never imports a host write service. `SuggestionExecutor` is the only write interface, and only `SuggestionService` calls it.

## 6. Storage model (reference host)

- **Database:** SQLCipher 4.x via `sqlcipher3`. The startup path verifies `PRAGMA cipher_version`, applies a per-database key, and refuses to open a plain SQLite file.
- **Accounts:** Argon2id password hashes; short-lived in-memory sessions; per-user permission rows.
- **Tables:** users, permissions, memories, people, relationships, places, activities, routines, routine_events, reminders, conversations, messages, suggestions, audit_log.
- **API keys:** separate DPAPI container (`credentials/agent_keys.json`), bound to the Windows user.
- **Logs/settings:** no personal content, no secrets.

## 7. Voice architecture

`AudioManager` gates recording/transcription, keeps audio in memory, and exposes backends:

- STT: `DisabledSTT`, `MockSTT`, `GeminiSTT`, `LocalWhisperSTT` (optional dependency; not installed).
- TTS: `NullTTS`, `MockTTS`, `WindowsSapiTTS` (optional `pyttsx3`; not installed).
- Recording: `SoundDeviceRecorder` (optional `sounddevice`), unavailable on this machine.

Cloud transcription requires a separate consent scope, even when the chat provider is already authorized.

## 8. Threading

- Qt work uses `QThreadPool`/`QRunnable` (`memory_agent/ui/workers.py`).
- `ChatController` never calls a provider from the GUI thread.
- `CancellationToken` is cooperative and checked between rounds, before tool calls, during retry waits and after provider returns.
- SQLCipher connections are per-thread in the host layer.

## 9. Extension points

- Add a provider: implement `AIProvider`, register it in `providers/registry.py`.
- Add a tool: subclass `BaseTool`, declare permission + args schema, register in `factory.py`.
- Add a host: implement the seven read protocols plus `SuggestionExecutor`, then call `build_runtime()`.
- Add context categories: extend `CATEGORY_PERMISSIONS` and permission identifiers deliberately.

## 10. Testability

All external edges are injectable: providers, integrations, credential store, conversation store, suggestion store, clock (proactive engine) and audio backends. The default test suite uses mocks only.
