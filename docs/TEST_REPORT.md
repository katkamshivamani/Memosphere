# Test report

**Date:** 2026-11-18
**Build:** `personal-memory-companion` 0.1.0 (working tree, not committed)

## 1. Environment actually used

| Item | Value |
| --- | --- |
| OS | Windows (win32) |
| Python | 3.10.11 (`python`; the `py` launcher and the Python 3.13 folder were unusable) |
| PySide6 | 6.12.0 (offscreen platform) |
| SQLCipher | 4.20.0 community via `sqlcipher3` |
| pydantic | 2.14.1 |
| google-genai | 2.33.0 (installed, not called live) |
| openai | 3.55.0 (installed, not called live) |
| pytest | 9.2.0 |

The brief preferred Python 3.13. Code targets 3.10-compatible syntax and was executed on 3.10.11; this is a documented deviation, not an untested claim.

## 2. Commands

```powershell
$env:PYTHONPATH="E:\AGENT\src"
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest
```

Offline suite only. No network, no API key, no microphone, no speaker.

## 3. Result

```
144 passed, 3 skipped in 13.76s
exit code 0
```

The three skips are the live provider tests (Gemini, OpenAI, local server) in `tests/live/test_live_providers.py`. They skip when `GEMINI_API_KEY` / `OPENAI_API_KEY` is absent and when no local server responds.

Repeated full-suite runs were used to check Qt shutdown stability; the final suite exits 0 consistently.

## 4. Coverage by area

| File | Tests | What it proves |
| --- | ---: | --- |
| `test_providers.py` | 28 | Registry, neutral schemas, OpenAI/Gemini conversion and normalization, local HTTP provider, typed error mapping, request shapes, no secrets in `repr` |
| `test_confidence.py` | 19 | Recorded/inferred/missing/conflicting rules, conflict detection, suggestion-only results are not evidence, inference/conflict labelling, write-claim guard, medical disclaimer, source cap, intent classification |
| `test_key_management.py` | 13 | In-memory lifecycle, masking, validation, DPAPI round trip, ciphertext-only file, unavailable-store refusal (no plaintext fallback), settings secret-free assertion |
| `test_scenarios.py` | 11 | Multi-turn history, conversation isolation, cancellation, untrusted tool payloads, consent withdrawal, edit-then-approve write, proactive dedupe/quiet hours/missing-activity wording |
| `test_privacy.py` | 10 | Minimal category scoping, Mode B consent, Mode C refusal/allowance, redaction, injection wrapping/reporting, context budget, greeting sends nothing |
| `test_voice.py` | 10 | Mock transcription, disabled voice, missing microphone, cloud-consent gate, disabled STT/TTS errors, status, no audio written to disk |
| `test_storage_auth.py` | 9 | SQLCipher encryption + header check, plaintext DB refusal, Argon2id hashes, permission grants, session expiry, revocation blocks tools, approval-only write, encrypted conversations/audit |
| `test_ui.py` | 9 | Ten pages load, seeded tables render, privacy page reports encryption/9 permissions, suggestion card state, evidence bubble, transcript editor, dialog validation, worker success/failure, chat empty state |
| `test_tools.py` | 8 | Unknown tool rejection, argument validation, permission denial, per-turn limit, duplicate protection, timeout, per-tool limit, all 15 tools registered |
| `test_suggestions.py` | 8 | Agent suggestions must be pending, approval executes, rejection never executes, edit stays pending, no re-approval, write permission required, safe unknown id, denied suggestion permission produces none |
| `test_agent_loop.py` | 7 | Grounded answer + source, unsupported claim replaced, five-round cap, duplicate call, cancellation, invalid session, persisted history |
| `test_host_flow.py` | 7 | Disabled agent, missing key, Mode B consent at service level, Mode C rejection, end-to-end pending suggestion → approve → stored memory, provider closed after turn, executor permission |
| `test_permissions.py` | 5 | Exact permission id set, session rejection, denial, `has`/`require_any`, safe messages |
| `live/test_live_providers.py` | 3 | **Skipped:** real Gemini/OpenAI/local calls, opt-in only |

## 5. Smoke scripts (run on 2026-11-18)

| Script | Result |
| --- | --- |
| `scripts/smoke_agent.py` | `OK` — recorded answer, correct source and tool trace |
| `scripts/smoke_host.py` | `OK` — SQLCipher 4.20.0, demo user, 13 permissions, refusal without a key, persisted conversation |
| `scripts/smoke_ui.py` | `OK` — 10 pages, 4 memory rows, all pages construct offscreen |

## 6. Not tested / not verified

These are honest gaps, not passes:

1. **Live Gemini calls.** No key was available. Request conversion, normalization and error mapping are tested with fakes; real network/auth/quota behaviour is not.
2. **Live OpenAI calls.** Same.
3. **Real local LLM server.** `LocalProvider` is tested over an `httpx.MockTransport`; no Ollama/LM Studio instance was run.
4. **Microphone capture.** No microphone was available and `sounddevice` is not installed. Recording/transcription is tested with `FakeRecorder`/`MockSTT`.
5. **Speaker output.** No speaker test; `pyttsx3` is not installed. `WindowsSapiTTS` was not exercised.
6. **Cloud speech-to-text.** `GeminiSTT` consent gating is tested, but no audio was sent to Google.
7. **DPAPI on other machines/users.** The round trip passed on this Windows account. Cross-machine/cross-user decryption is intentionally unsupported and untested.
8. **Streaming responses.** Not implemented; the UI shows a loading state and a cancel button instead.
9. **Long-running/background usage, sleep/resume, low-memory behaviour.** Not exercised.
10. **Security audit / penetration test.** Not performed.

## 7. Reproduce

```powershell
cd E:\AGENT
python -m pip install -r requirements.txt
python -m pip install pytest==9.2.0
$env:PYTHONPATH="$PWD\src"
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest
```

To run the skipped live tests when keys are available:

```powershell
$env:GEMINI_API_KEY="..."
python -m pytest tests/live -m live
```
