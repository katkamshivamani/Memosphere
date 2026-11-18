# Privacy, consent and data handling

## 1. Context modes

| Mode | What is sent | Enforcement |
| --- | --- | --- |
| **Minimal** (`minimal`) | Records from categories chosen by local intent rules for this question, keyword-scoped | `ContextBuilder`; only authorized categories |
| **Full authorized** (`full_authorized`) | Broader records from all authorized categories (memory, people, places, activities, routines, reminders), within character/record budgets | Requires active `FULL_CONTEXT` consent; refuses without it |
| **Local only** (`local_only`) | Same authorized context, but only to a provider whose `is_local` is true | Refuses cloud providers at the service and builder layers |

Category → permission mapping:

| Category | Permission |
| --- | --- |
| memory | `memory.read` |
| people | `people.read` |
| places | `places.read` |
| activities | `activities.read` |
| routines | `routines.read` |
| reminders | `reminders.read` |

Unavailable or unauthorized categories are listed in `skipped_categories`; the model is told that no records were included rather than being allowed to guess.

## 2. Consent

`ConsentManager` persists append-only consent records with timestamps and audit hooks.

Scopes:

- `FULL_CONTEXT` — required for Mode B. Categories are recorded at grant time.
- `CLOUD_TRANSCRIPTION` — required for cloud speech-to-text, independent of the chat provider.

Withdrawing a scope takes effect on the next request. The settings UI exposes both grant and withdraw actions. Consent records contain no personal content.

## 3. What the model can see

A provider request contains:

1. The fixed system prompt (identity, policy, mode note, grounding rules).
2. Recent conversation messages (user + final assistant answers).
3. The current question.
4. Authorized context records, rendered as:

```
AUTHORIZED_PERSONAL_CONTEXT
mode=minimal
...instructions that the records are data...
[type=memory | source=memories | title="Wallet location" | date=2026-11-17]
<untrusted_record id="mem_001">
Wallet was placed in the top drawer ...
</untrusted_record>
```

5. Tool results wrapped in `<<<UNTRUSTED_TOOL_RESULT>>>` markers.

Nothing else is sent: no keys, no other users' rows, no database schema, no file paths.

## 4. Secret handling

- `data_filter.find_secrets()`/`redact_text()` detect common credential shapes (Google, OpenAI, Anthropic, GitHub, AWS, bearer tokens, password assignments, private-key blocks).
- Redaction is applied to context records, tool payloads, final answers and user-facing error messages.
- Settings saving calls `assert_secret_free()` and refuses a value that looks like a credential.
- Logs never include keys or memory content; the credential manager logs only provider ids and event types.

Redaction is pattern-based. It reduces accidental disclosure but is not a guarantee that every possible secret format is caught. Users should still avoid storing credentials as memories.

## 5. Prompt injection

Memory text is untrusted. Two independent controls apply:

1. **Structural:** record content is wrapped in explicit untrusted delimiters; the system prompt says it is data, never instructions.
2. **Capability:** even if the model follows injected text, it cannot do anything the tools do not allow. There are no SQL/filesystem/OS tools; writes require approval. Permissions are checked in code after the model requests a tool.

`PromptInjectionDetector` adds a heuristic report (`InjectionReport.flagged_record_ids`, categories) and the orchestrator logs a warning count. Detection is advisory and auditable; enforcement does not depend on it.

## 6. Grounding and honesty

`EvidenceAssessor` maps results to:

- **RECORDED** — at least one retrieved record directly matches the question.
- **INFERRED** — related records exist but do not directly match; the answer is prefixed as an inference.
- **MISSING** — no records. Unsupported personal claims are replaced with an honest "not recorded" answer. The text explicitly notes that a missing record does not prove an event did not happen.
- **CONFLICTING** — records disagree; the answer is prefixed with a conflict notice.

There are no invented confidence percentages. Suggestion-only tool results never count as evidence of a stored fact.

Write claims (`"I have saved..."`, `"your memory was created"`) are rewritten when no suggestion exists, and users are told nothing was changed.

## 7. Suggestions and writes

- Agent-created suggestions must have status `pending_approval`.
- Approval re-checks the session and the host write permission.
- The host executor re-checks approval status and permissions again.
- Rejection leaves records untouched. An approved suggestion that fails becomes `failed`; it is not silently retried.
- The user can edit title, description and payload before approving; the edited content is what the executor writes.

## 8. Storage and authentication (reference host)

- SQLCipher encryption with a startup `PRAGMA cipher_version` check.
- A plaintext SQLite database is refused; no unencrypted fallback exists.
- Passwords use Argon2id; sessions expire and can be invalidated.
- Per-user permission rows gate both UI and agent tool calls.
- Audit log stores action names and metadata only, never memory content or secrets.
- API keys live in a separate DPAPI container, bound to the current Windows user.

## 9. Proactive suggestions

Proactive evaluation is local and deterministic:

- disabled assistant or disabled proactive setting → suppressed;
- quiet hours → suppressed;
- similar existing reminder/pending suggestion → suppressed;
- missing-activity wording never asserts that the user missed something.

No personal data leaves the machine to generate a proactive suggestion.

## 10. Residual risks and limits

- Cloud providers necessarily see the authorized context that is sent; Mode B is broad by design.
- Redaction and injection detection are heuristic, not formal guarantees.
- The host application is responsible for full-disk encryption, OS account security, backups and secure key recovery.
- DPAPI protects keys against other Windows users, not against malware running as the same user.
- The agent has not been audited by an external security team.
