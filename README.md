# Memosphere v2.0 — Privacy-Focused AI Personal Memory & Dementia Care Companion

A modular **Python (FastAPI + SQLite3) + HTML5 + CSS3 + Vanilla JavaScript (PWA)** application implementing the **Universal Personal Knowledge Base** alongside specialized **Alzheimer's & Dementia Assistance (Module A)**, **Persistent Vibration & Reminder Acknowledgement (Module B)**, **Multilingual Conversational Voice Assistant in English, Kannada & Hindi (Module C)**, and **Intelligent Caregiver & Safety Monitoring (Module D)**.

---

## 🔍 Phase 1: Project Audit of Existing Repository (`memosphere-python-fullstack.zip`)

1. **Existing Working Modules Preserved (100% Backward Compatible)**:
   - **Universal Personal Knowledge Base (`people`, `places`, `activities`, `routines`)**: Full CRUD, search, relationship/category filters, pinned quick-access bar, one-tap activity logging with `"Logged X mins ago"` badges, and streak counters.
   - **Circle of Trust Endpoint (`/api/routines/status`)**: Polls `completed`, `pending`, and `missed` routines where `shareWithCircle = true`.
   - **Unified RAG Knowledge Search (`/api/knowledge-search?q=...`)**: Retrieves across all SQLite tables with structured JSON output.
2. **Issues Identified & Resolved During Audit**:
   - **API Key Isolation**: Moved all LLM API key handling strictly to the Python backend (`config.py` / `.env`). The frontend never stores or receives raw API keys.
   - **Framework Upgrade**: Migrated from single-file Flask to modular **FastAPI** (`main.py`, `config.py`, `database.py`, `routers/`, `services/`, `tests/`) while maintaining compatibility with `python app.py` and `uvicorn main:app --reload`.
   - **Medication Safety**: Added explicit 3-state confirmation (`TAKEN`, `NOT_TAKEN`, `REMIND_LATER`) that records exact timestamps and never auto-marks medication as taken when a popup is dismissed.

---

## 🚀 Complete Setup & Execution Instructions

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Configure environment variables (Backend-only AI API keys)
cp .env.example .env
# Edit .env and set GEMINI_API_KEY or OPENAI_API_KEY on the backend

# 3. Seed (or reset) the local SQLite database (memosphere.db)
python seed.py

# 4. Run the automated verification test suite (8 end-to-end tests)
python -m unittest discover -s tests -p "test_*.py" -v

# 5. Start the FastAPI server (runs on http://localhost:8000)
python app.py
# Or directly with Uvicorn:
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 📊 Implementation Classification & Platform Limitations

| Feature / Subsystem | Status | Notes & Technical Boundary |
| :--- | :--- | :--- |
| **Universal Personal Knowledge Base (People, Places, Activities, Routines)** | **Fully Implemented** | Local SQLite persistence + full FastAPI CRUD + instant search & filters |
| **Module A1–A6 (Familiar Faces, Orientation, Memory Album, Environment Guide, SOS, Medication Confirmation)** | **Fully Implemented** | Matches saved profiles only; never fabricates memories or auto-marks medication taken |
| **Module B (Foreground Persistent Reminder Screen, Web Vibration Loop, Snooze & Caregiver Escalation)** | **Fully Implemented** | Uses `navigator.vibrate`, Web Audio chime loop, and Service Worker notifications while app is open/active |
| **Module C (Voice Assistant: STT/TTS, EN/KN/HI, Proposal & Confirmation Card, Patient Repeat-Question Handling)** | **Fully Implemented** | Uses browser Web Speech API (`SpeechRecognition` & `speechSynthesis`) + backend structured proposal parser |
| **Module D (Safe-Zone Geofence, Routine Deviation Detection, Mood Check-in, Caregiver Notes, Weekly Report, Rest Period)** | **Fully Implemented** | Explicit patient consent toggle (zero covert tracking) + non-diagnostic behavioral observations |
| **External Cloud LLM Generation (Gemini / OpenAI RAG)** | **Requires External API Credentials** | Set `GEMINI_API_KEY` or `OPENAI_API_KEY` in backend `.env`. Degrades gracefully to local SQLite recall when unconfigured |
| **Guaranteed Lock-Screen / Closed-Browser Background Vibration & DND Override** | **Requires Native Android Integration** | Standard web browsers suspend background vibration when locked or closed and cannot bypass OS Do Not Disturb. Wrap `frontend/` with **Capacitor / Android WebView + Native Foreground Service & `AlarmManager`** for guaranteed hardware vibration when locked |
| **Automatic Unknown-Face Biometric Identification / Autonomous Dosage Modification** | **Not Implemented (By Safety Policy)** | Intentionally excluded for patient safety, privacy, and clinical compliance |
