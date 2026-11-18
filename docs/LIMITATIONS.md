# Limitations, gaps and hardware-dependent items

This file is intentionally blunt. Anything listed as unverified was not exercised in this environment and must not be presented as working.

## 1. Verified versus unverified

| Area | Status |
| --- | --- |
| Agent loop, grounding, tools, permissions, suggestions | Verified by offline tests and smoke scripts |
| Encrypted SQLCipher storage, Argon2id auth, DPAPI key round trip | Verified on this Windows user |
| PySide6 UI construction/navigation | Verified offscreen |
| Live Gemini API | **Not verified** — no key available |
| Live OpenAI API | **Not verified** |
| Real local LLM server | **Not verified** — mocked HTTP only |
| Microphone capture / transcription | **Not verified** — no hardware, optional deps absent |
| Speaker / SAPI speech | **Not verified** — optional deps absent |
| Cloud speech-to-text | **Not verified** — consent gate tested only |

## 2. Feature limitations

1. **Streaming answers.** The provider contract supports a `supports_streaming` flag, but this build does not stream. The chat shows a loading indicator and a Cancel button. Responses arrive as one block.
2. **No background monitoring loop.** Proactive suggestions are generated only when the host calls `ProactiveEngine.evaluate()` / `upcoming_reminder_events()`. The reference app does not run a scheduler.
3. **Context repeated each turn.** `ContextLedger` hashes previously sent records for reporting, but content is still included each turn because chat history does not store prior context blocks. The "delta context" optimization is not implemented.
4. **Full authorized mode is broad by design.** It browses authorized categories without keyword scoping, bounded by per-category and character limits. That is a product/privacy decision, not a bug.
5. **Heuristic redaction and injection detection.** Pattern-based, not a formal guarantee. A novel secret format or injection phrasing can be missed.
6. **No numeric confidence.** Grounding states are deterministic categories; probability-style confidence was deliberately not invented.
7. **Single-user desktop scope.** No multi-device sync, sharing, import/export UI, or server mode.
8. **No semantic search.** Search is keyword/SQL-LIKE based; no embeddings/vector index.
9. **No database migrations tool.** Schema creation is idempotent (`CREATE TABLE IF NOT EXISTS`), but there is no versioned migration system yet.
10. **No backup/restore UI.** Files are on disk; users must back up the data folder themselves.
11. **Reference host only.** `memory_companion` was built for this task because no existing host app was present. It is not the user's production application.
12. **Python 3.10.11 used.** The brief preferred 3.13; the only runnable interpreter here was 3.10. Code is 3.10-compatible and has not been run on 3.13.
13. **No localization.** UI text is English-only.
14. **No installer/packaging.** Run from source; wheel/EXE packaging and code signing are not provided.

## 3. Platform security limitations

- **Windows only for credentials.** `DpapiCredentialStore` is implemented and self-tested. `LinuxSecretServiceStore` and `MacKeychainStore` are explicit stubs that report unavailable; there is no plaintext fallback.
- **DPAPI scope.** Protects against other Windows users; does not protect against malware or processes running as the same user.
- **Database key handling.** The reference host derives/manages the SQLCipher key locally. Production deployments should integrate OS-backed secret storage and a recovery story.
- **No independent security audit.** Threat modelling exists in the docs; formal review/pen testing does not.

## 4. Voice-specific gaps

- Optional packages `sounddevice` and `pyttsx3` are not installed; recording and SAPI have never run on this machine.
- `LocalWhisperSTT` requires optional packages and a local model; it is implemented as an adapter path but not installed or tested.
- Cloud transcription consent exists, but no audio was sent to any provider.
- Echo cancellation, device selection, level metering, VAD and hotkeys are not implemented.

## 5. Testing gaps

- Live provider auth/quota/error behaviour is untested.
- Real-world tables (large databases, thousands of records) were not benchmarked.
- Accessibility (screen readers, keyboard-only traversal, high contrast) was not tested.
- Long-running stability, sleep/resume, multiple monitors and DPI changes were not tested.
- No load/performance tests for context building or tool execution.

## 6. What would be needed to close the gaps

1. Provide real API keys and run `pytest tests/live -m live`.
2. Install `requirements-voice.txt` on a machine with microphone/speakers and manually verify record → preview → send and read-aloud.
3. Run a local Ollama/LM Studio server and test Mode C end-to-end.
4. Add a packaging pipeline (PyInstaller/MSIX) and code signing.
5. Add DB migrations, backup/restore, and large-dataset performance tests.
6. Commission a security review of DPAPI use, SQLCipher key management, redaction and injection handling.
7. Implement streaming and, if desired, delta context.
