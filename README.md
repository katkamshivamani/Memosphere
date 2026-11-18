# MEMOSPHERE — Your Personal AI Memory Companion

> **Tagline:** *Never Lose a Memory. Never Feel Alone.*

MEMOSPHERE is a privacy-focused, full-stack personal AI memory companion designed to help individuals effortlessly capture everyday moments, locate misplaced items, receive patient answers to repeated questions, stay on track with tone-adapted reminders and daily routines, and optionally share consent-gated routine adherence summaries with a trusted caregiver.

---

## Key Architectural Highlights

1. **Modular External AI API Integration Layer (Zero Custom ML Models)**:
   - Located in `backend/services/ai/` (`init.py`, `ai_client.py`, `provider_factory.py`, `groq_provider.py`, `nvidia_nim_provider.py`, `gemini_provider.py`, `openai_provider.py`, `prompt_manager.py`, `response_parser.py`).
   - Supports **Groq API**, **NVIDIA NIM API**, **Google Gemini API**, and **OpenAI API** through one common `BaseAIProvider` contract.
   - Each provider has its own key and model environment variables, so switching `AI_PROVIDER` never carries another provider's model name into the request:
     - Groq: `GROQ_API_KEY`, `GROQ_MODEL` (default `llama-3.3-70b-versatile`), optional `GROQ_BASE_URL`
     - NVIDIA NIM: `NVIDIA_NIM_API_KEY`, `NVIDIA_NIM_MODEL` (default `meta/llama-3.1-70b-instruct`), `NVIDIA_NIM_BASE_URL`
     - Gemini: `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-2.5-flash`)
     - OpenAI: `OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-4o-mini`), optional `OPENAI_BASE_URL`
   - All providers use standard HTTPS REST via `requests`; no vendor SDK is required.
   - **Single-Provider Requirement**: Only the selected provider's API key is required. If no API key is configured or if the network is unreachable, MEMOSPHERE seamlessly falls back to its transparent, deterministic `RuleBasedFallbackEngine`.
   - **Strict Secret Protection**: API keys are loaded strictly from backend environment variables, masked in status endpoints, and never exposed to frontend JavaScript or `localStorage`.

2. **Privacy-First Natural Language Memory Q&A & Patient Repetition**:
   - Retrieves only the top matching SQLite records via `MemoryService.retrieve_relevant_memories()`—never transmitting the entire personal database to the external AI API.
   - Detects repeated questions via `MemoryService.detect_repeated_question()` and responds with warmth and reassurance without irritation.

3. **Quick Voice & Text Brain Dump Capture**:
   - Extracts structured JSON (`category`, `title`, `content`, `entity_name`, `location`, `event_date`) across five categories: `People`, `Places`, `Items`, `Activities`, and `Routines`.
   - Prompts for clarification when details are ambiguous, allows manual editing before saving, and prevents duplicate memory records.

4. **Deterministic APScheduler Reminders & Adaptive Accessibility UI**:
   - Schedules one-time and recurring reminders with **Friendly**, **Calm**, and **Direct** notification tones.
   - Switches seamlessly between **Standard SaaS Dashboard Mode** and **Simplified Accessibility Mode** (high-contrast WCAG AAA palette, 21px base typography, oversized action buttons, and Web Speech API voice readout), persisted in `localStorage`.

5. **Role-Based Caregiver Dashboard with Explicit Consent**:
   - Requires explicit `consent_status = "granted"` in `CaregiverPermissions`.
   - Displays daily routine completion, missed routines, frequently missed activities, and pending reminders while redacting private personal memories and conversations.

---

## Project Structure

```text
memosphere/
├── app.py
├── config.py
├── requirements.txt
├── .gitignore
├── .env.example
├── README.md
├── backend/
│   ├── models.py
│   ├── routes/
│   │   ├── auth.py
│   │   ├── memories.py
│   │   ├── assistant.py
│   │   ├── reminders.py
│   │   ├── routines.py
│   │   ├── caregiver.py
│   │   └── ai_settings.py
│   └── services/
│       ├── ai/
│       │   ├── init.py
│       │   ├── ai_client.py
│       │   ├── provider_factory.py
│       │   ├── groq_provider.py
│       │   ├── nvidia_nim_provider.py
│       │   ├── gemini_provider.py
│       │   ├── openai_provider.py
│       │   ├── prompt_manager.py
│       │   └── response_parser.py
│       ├── memory_service.py
│       └── reminder_service.py
├── frontend/
│   ├── index.html
│   ├── login.html
│   ├── caregiver.html
│   ├── settings.html
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   ├── app.js
│   │   ├── assistant.js
│   │   ├── voice.js
│   │   ├── memories.js
│   │   ├── reminders.js
│   │   └── accessibility.js
│   └── assets/
├── instance/
│   └── memosphere.db
└── tests/
    ├── test_memories.py
    ├── test_ai.py
    └── test_reminders.py
```

---

## Exact Windows VS Code Terminal Commands to Run MEMOSPHERE

Open the `memosphere` folder in **Visual Studio Code** on Windows, open a **PowerShell** or **Command Prompt** terminal (`Ctrl + ~`), and run:

### 1. Create and Activate a Virtual Environment

**PowerShell:**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

*(If PowerShell execution policy blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first, or use Command Prompt: `.venv\Scripts\activate.bat`)*

### 2. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure Environment Variables (`.env`)

```powershell
copy .env.example .env
```

Edit `.env` in VS Code to set your preferred `AI_PROVIDER` (`groq`, `nvidia_nim`, `gemini`, or `openai`) and paste the matching API key (or leave blank to run with the built-in local rule-based fallback). Each provider has its own MODEL variable; use the Settings page (`/settings.html`) to switch providers at runtime without browser-side secrets. `.env` and local `*.db` files are excluded from Git by `.gitignore`.

### 4. Run the Automated Test Suite

```powershell
pytest -v
```

### 5. Start the MEMOSPHERE Application Server

```powershell
python app.py
```

Open your browser at:
- **Main Companion Dashboard:** `http://127.0.0.1:5000`
- **Caregiver Dashboard:** `http://127.0.0.1:5000/caregiver.html`
- **AI API Configuration & Status:** `http://127.0.0.1:5000/settings.html`
- **Login / Switch Role:** `http://127.0.0.1:5000/login.html`
