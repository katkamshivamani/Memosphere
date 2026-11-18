# Setup and configuration

## 1. Requirements

| Requirement | Notes |
| --- | --- |
| Windows 10/11 | Primary target. DPAPI is Windows-only in this build. |
| Python 3.10–3.13 | This build was developed and tested with **Python 3.10.11** because that was the only runnable interpreter on the build machine. Code avoids 3.11+-only syntax. |
| PySide6 6.12 | Installed from `requirements.txt`. |
| SQLCipher (`sqlcipher3` 0.6.5) | Provides encrypted SQLite; verified at startup. |
| No API key needed for tests | The offline suite uses mocked providers. |

Optional voice dependencies (`sounddevice`, `pyttsx3`) are in `requirements-voice.txt` and are **not installed or verified** in this environment.

## 2. Install

```powershell
cd E:\AGENT
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If you want to run the suite exactly as in the test report:

```powershell
python -m pip install pytest==9.2.0
```

`scripts/check_env.py` prints versions and performs a SQLCipher round-trip and an offscreen Qt import check:

```powershell
python scripts/check_env.py
```

## 3. Run

```powershell
# Demo account with sample records (first run only); username demo / password demo-pass-1234
python scripts/run_app.py --demo

# Normal run
python scripts/run_app.py

# Custom data folder (useful for a clean profile)
python scripts/run_app.py --data-dir E:\MemoryCompanionData

# Standard module entry point after `pip install -e .`
python -m memory_companion
```

The login screen also supports creating a new account; new accounts receive the nine agent permission categories plus host write permissions.

## 4. Data folder

Default: `%LOCALAPPDATA%\MemoryCompanion` (override with `--data-dir` or `MEMORY_COMPANION_DATA_DIR`).

| File | Contents |
| --- | --- |
| `memory.db` | SQLCipher-encrypted database (accounts, records, conversations, suggestions, audit) |
| `credentials/agent_keys.json` | DPAPI-protected provider keys (ciphertext only) |
| `agent_settings.json` | Provider, model, mode, limits, voice/proactive settings — no secrets |
| `agent_consent.json` | Consent records with timestamps |
| `settings.json` | Small UI preferences |
| `logs/` | Application log files (no secrets or memory content) |

Back up the whole folder, not just `memory.db`: the credential container and the database key material are separate.

## 5. Configure the assistant

Open **Settings**:

1. **Provider**: Gemini, OpenAI or Local.
2. **API key** (cloud only): paste and save. The field shows a masked value afterwards.
3. **Test connection**: runs off the GUI thread and reports a typed result.
4. **Model**: choose from the live list or type an id. No default is assumed.
5. **Privacy mode**: Minimal / Full authorized / Local only.
   - Full authorized requires the consent button in Privacy or Settings.
   - Local only requires the Local provider and a running local server.
6. **Limits**: tool rounds (1–5), calls per turn, context/record/response character budgets, timeouts.
7. **Proactive suggestions** (optional): enable and set quiet hours.
8. **Voice** (optional): enable recording / spoken answers; cloud transcription needs separate consent.

## 6. Permissions

The nine agent categories can be toggled per user on the **Privacy** page:

```
memory.read, memory.suggest_create, memory.suggest_update,
people.read, places.read, activities.read, routines.read,
reminders.read, reminders.suggest_create
```

Revoking a read permission blocks the matching tool and excludes the category from context. Revoking a suggestion permission blocks the matching `suggest_*` tool. Approving a suggestion additionally requires the host write permission.

## 7. Voice (optional)

```powershell
python -m pip install -r requirements-voice.txt
```

- Recording is user-activated only; the app does not listen in the background.
- Audio is kept in memory and discarded after transcription; it is not written to disk.
- The transcript appears in an editable preview before it is sent.
- Cloud transcription (Gemini STT) requires explicit consent separate from chat consent.
- If no microphone/backend is available, the control shows a clear error and the rest of the app keeps working.

Voice was **not exercised with real hardware** here. See `docs/LIMITATIONS.md`.

## 8. Tests

```powershell
$env:PYTHONPATH="$PWD\src"
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest
```

Live provider tests (network, real key):

```powershell
$env:GEMINI_API_KEY="..."
python -m pytest tests/live -m live
```

Smoke scripts:

```powershell
python scripts/smoke_agent.py
python scripts/smoke_host.py
python scripts/smoke_ui.py
```

## 9. Troubleshooting

| Symptom | Cause / action |
| --- | --- |
| "Secure storage unavailable" at startup | DPAPI unavailable or self-test failed. The app refuses to run rather than store keys in plaintext. |
| "The encrypted database could not be opened" | Wrong SQLCipher library or a corrupt/incompatible file; check the log. A plaintext SQLite file is intentionally rejected. |
| "No API key stored for provider..." | Save a key in Settings, then test the connection. |
| Local-only mode refuses to run | Select the Local provider and start your local server first. |
| "Could not reach the local model server" | Start Ollama/LM Studio and verify the base URL. |
| "Model unavailable" | The provider no longer lists that model; pick another. |
| Voice controls show "unavailable" | Optional dependencies or audio hardware are missing. |
| Qt tests fail to create a window | Set `QT_QPA_PLATFORM=offscreen` (the test conftest sets it automatically). |

## 10. Configuration files and secrets

- Do not put API keys in `agent_settings.json`; saving is rejected if a credential pattern is found.
- Logs intentionally exclude keys and personal record content.
- The DPAPI container is only decryptable by the same Windows user profile. Moving it to another machine/user will not work.
