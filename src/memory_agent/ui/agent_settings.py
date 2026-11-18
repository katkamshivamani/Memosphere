"""Assistant settings: provider, API key, privacy, voice.

Security notes:

* a stored key is never displayed again - only a masked suffix;
* test/save use worker threads (no GUI-thread network calls);
* enabling the agent with a cloud provider requires a key and a successful
  connection test is offered, not assumed;
* context mode C is only offered when a local provider is selected.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QThreadPool, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from memory_agent.config import AgentSettings, ContextMode, VoiceSettings
from memory_agent.core.exceptions import AgentError
from memory_agent.providers.schemas import ConnectionTestResult
from memory_agent.ui.workers import FunctionWorker
from memory_agent.voice.audio_manager import AudioManager


class AgentSettingsWidget(QWidget):
    settings_saved = Signal()
    clear_history_requested = Signal()

    def __init__(
        self,
        *,
        service,
        audio: AudioManager,
        user_id: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._audio = audio
        self._user_id = user_id
        self._pool = QThreadPool.globalInstance()
        self._settings = service.settings()
        self._catalog = {item["id"]: item for item in service.provider_catalog()}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 12, 12)
        layout.setSpacing(12)
        scroll.setWidget(content)

        intro = QLabel(
            "Configure how the Personal Memory Assistant connects to an AI provider and "
            "how much of your personal information may be shared. Changes are saved only "
            "when you press Save."
        )
        intro.setWordWrap(True)
        intro.setProperty("muted", True)
        layout.addWidget(intro)

        layout.addWidget(self._build_general_group())
        layout.addWidget(self._build_provider_group())
        layout.addWidget(self._build_privacy_group())
        layout.addWidget(self._build_voice_group())
        layout.addWidget(self._build_advanced_group())

        self._feedback = QLabel("")
        self._feedback.setWordWrap(True)
        layout.addWidget(self._feedback)

        buttons = QHBoxLayout()
        self._save_button = QPushButton("Save settings")
        self._save_button.setProperty("primary", True)
        self._save_button.clicked.connect(self._save)
        buttons.addWidget(self._save_button)
        self._test_button = QPushButton("Test connection")
        self._test_button.clicked.connect(self._test_connection)
        buttons.addWidget(self._test_button)
        self._clear_button = QPushButton("Clear this conversation")
        self._clear_button.clicked.connect(self.clear_history_requested.emit)
        buttons.addWidget(self._clear_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(1)

        self._load_into_widgets()
        self._refresh_voice_status()

    # ------------------------------------------------------------------ #
    # Sections
    # ------------------------------------------------------------------ #
    def set_audio(self, audio: AudioManager) -> None:
        self._audio = audio
        self._refresh_voice_status()

    def _build_general_group(self) -> QGroupBox:
        group = QGroupBox("Assistant")
        form = QFormLayout(group)
        self.enabled_check = QCheckBox("Enable the Personal Memory Assistant")
        form.addRow("", self.enabled_check)
        self._store_status = QLabel(self._service.credential_store_status)
        self._store_status.setWordWrap(True)
        self._store_status.setProperty("muted", True)
        form.addRow("Credential storage", self._store_status)
        return group

    def _build_provider_group(self) -> QGroupBox:
        group = QGroupBox("AI provider")
        form = QFormLayout(group)

        self.provider_combo = QComboBox()
        for provider_id, info in self._catalog.items():
            label = info["label"]
            if info["is_local"]:
                label += " (local)"
            self.provider_combo.addItem(label, provider_id)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("Provider", self.provider_combo)

        model_row = QHBoxLayout()
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setMinimumWidth(240)
        model_row.addWidget(self.model_combo, 1)
        self._refresh_models_button = QPushButton("Load available models")
        self._refresh_models_button.clicked.connect(self._load_models)
        model_row.addWidget(self._refresh_models_button)
        form.addRow("Model", self._wrap(model_row))

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("http://127.0.0.1:11434/v1")
        self.base_url_row = self.base_url_edit
        form.addRow("Local server URL", self.base_url_row)

        self._provider_notes = QLabel("")
        self._provider_notes.setWordWrap(True)
        self._provider_notes.setProperty("muted", True)
        form.addRow("", self._provider_notes)

        key_row = QHBoxLayout()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("Paste a new API key to replace the stored one")
        key_row.addWidget(self.api_key_edit, 1)
        self._save_key_button = QPushButton("Save key")
        self._save_key_button.clicked.connect(self._save_key)
        key_row.addWidget(self._save_key_button)
        self._delete_key_button = QPushButton("Delete key")
        self._delete_key_button.clicked.connect(self._delete_key)
        key_row.addWidget(self._delete_key_button)
        self._key_row_widget = self._wrap(key_row)
        form.addRow("API key", self._key_row_widget)

        self._key_status = QLabel("")
        self._key_status.setWordWrap(True)
        self._key_status.setProperty("muted", True)
        form.addRow("", self._key_status)

        test_row = QHBoxLayout()
        self._test_provider_button = QPushButton("Test this provider")
        self._test_provider_button.clicked.connect(self._test_connection)
        test_row.addWidget(self._test_provider_button)
        test_row.addStretch(1)
        form.addRow("", self._wrap(test_row))
        return group

    def _build_privacy_group(self) -> QGroupBox:
        group = QGroupBox("Privacy and context")
        layout = QVBoxLayout(group)

        self.mode_combo = QComboBox()
        for mode in (ContextMode.MINIMAL, ContextMode.FULL_AUTHORIZED, ContextMode.LOCAL_ONLY):
            self.mode_combo.addItem(mode.label, mode.value)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        layout.addWidget(self.mode_combo)

        self.mode_explanation = QLabel("")
        self.mode_explanation.setWordWrap(True)
        self.mode_explanation.setProperty("muted", True)
        layout.addWidget(self.mode_explanation)

        self.consent_check = QCheckBox(
            "I consent to sending authorized personal context categories to the selected AI provider"
        )
        layout.addWidget(self.consent_check)

        self.consent_status = QLabel("")
        self.consent_status.setWordWrap(True)
        layout.addWidget(self.consent_status)

        self._withdraw_consent_button = QPushButton("Withdraw full-context consent")
        self._withdraw_consent_button.clicked.connect(self._withdraw_consent)
        layout.addWidget(self._withdraw_consent_button, 0, Qt.AlignLeft)

        note = QLabel(
            "Full context never exports the database. Passwords, API keys, authentication "
            "tokens, security answers and audit data are always excluded, and the amount "
            "of context is capped. Local-only mode requires a local provider."
        )
        note.setWordWrap(True)
        note.setProperty("muted", True)
        layout.addWidget(note)
        return group

    def _build_voice_group(self) -> QGroupBox:
        group = QGroupBox("Voice")
        form = QFormLayout(group)

        self.voice_enabled_check = QCheckBox("Enable microphone input")
        form.addRow("", self.voice_enabled_check)

        self.stt_combo = QComboBox()
        for value, label in (
            ("auto", "Automatic (prefer local)"),
            ("local", "Local (faster-whisper)"),
            ("gemini", "Cloud (Gemini)"),
            ("disabled", "Disabled"),
        ):
            self.stt_combo.addItem(label, value)
        form.addRow("Transcription", self.stt_combo)

        self.cloud_consent_check = QCheckBox(
            "I allow audio to be sent to the cloud transcription service"
        )
        form.addRow("", self.cloud_consent_check)

        self.speak_check = QCheckBox("Read answers aloud")
        form.addRow("", self.speak_check)

        self.tts_combo = QComboBox()
        for value, label in (("auto", "Automatic (Windows SAPI)"), ("disabled", "Disabled")):
            self.tts_combo.addItem(label, value)
        form.addRow("Speech output", self.tts_combo)

        self._voice_status = QLabel("")
        self._voice_status.setWordWrap(True)
        self._voice_status.setProperty("muted", True)
        form.addRow("Status", self._voice_status)

        note = QLabel(
            "Recordings are held in memory only and discarded after transcription. "
            "Nothing is recorded until you press the microphone button."
        )
        note.setWordWrap(True)
        note.setProperty("muted", True)
        form.addRow("", note)
        return group

    def _build_advanced_group(self) -> QGroupBox:
        group = QGroupBox("Limits")
        form = QFormLayout(group)
        self.rounds_spin = QSpinBox()
        self.rounds_spin.setRange(1, 5)
        form.addRow("Maximum lookup rounds", self.rounds_spin)
        self.calls_spin = QSpinBox()
        self.calls_spin.setRange(1, 40)
        form.addRow("Maximum tool calls per question", self.calls_spin)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 120)
        self.timeout_spin.setSuffix(" s")
        form.addRow("Provider timeout", self.timeout_spin)
        return group

    @staticmethod
    def _wrap(layout) -> QWidget:
        widget = QWidget()
        widget.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        return widget

    # ------------------------------------------------------------------ #
    # Load / save
    # ------------------------------------------------------------------ #
    def _load_into_widgets(self) -> None:
        settings = self._service.settings()
        self._settings = settings
        self.enabled_check.setChecked(settings.enabled)

        index = self.provider_combo.findData(settings.provider_id)
        self.provider_combo.setCurrentIndex(max(0, index))
        self._on_provider_changed()

        self.base_url_edit.setText(
            settings.base_urls.get(settings.provider_id, "")
        )
        self.model_combo.setCurrentText(settings.model_for(settings.provider_id) or "")

        mode_index = self.mode_combo.findData(settings.context_mode.value)
        self.mode_combo.setCurrentIndex(max(0, mode_index))
        self.consent_check.setChecked(self._service.has_full_context_consent())
        self._on_mode_changed()

        voice = settings.voice
        self.voice_enabled_check.setChecked(voice.enabled)
        self.speak_check.setChecked(voice.speak_responses)
        self.cloud_consent_check.setChecked(voice.cloud_transcription_allowed)
        self.stt_combo.setCurrentIndex(max(0, self.stt_combo.findData(voice.stt_backend)))
        self.tts_combo.setCurrentIndex(max(0, self.tts_combo.findData(voice.tts_backend)))
        self.rounds_spin.setValue(settings.max_tool_rounds)
        self.calls_spin.setValue(settings.max_tool_calls_per_turn)
        self.timeout_spin.setValue(int(settings.provider_timeout_s))
        self._refresh_key_status()
        self._refresh_voice_status()

    def _current_provider(self) -> str:
        return str(self.provider_combo.currentData())

    def _on_provider_changed(self) -> None:
        provider_id = self._current_provider()
        info = self._catalog.get(provider_id, {})
        is_local = bool(info.get("is_local"))
        self.base_url_row.setVisible(is_local)
        for widget in (self.api_key_edit, self._save_key_button, self._delete_key_button):
            widget.setVisible(not is_local)
        self._key_row_widget.setVisible(not is_local)
        self._provider_notes.setText(info.get("notes") or "")
        if is_local:
            self.base_url_edit.setText(
                self._settings.base_urls.get(provider_id, "http://127.0.0.1:11434/v1")
            )
        else:
            self.base_url_edit.clear()
        existing_model = self._settings.model_for(provider_id) or ""
        self.model_combo.clear()
        if existing_model:
            self.model_combo.addItem(existing_model, existing_model)
            self.model_combo.setCurrentText(existing_model)
        self._refresh_key_status()
        self._refresh_mode_availability()

    def _refresh_key_status(self) -> None:
        provider_id = self._current_provider()
        info = self._catalog.get(provider_id, {})
        if info.get("is_local"):
            self._key_status.setText("Local providers do not use an API key.")
            return
        masked = self._service.masked_api_key(provider_id)
        if masked:
            self._key_status.setText(f"Stored key: {masked} (stored by the operating system)")
        elif not self._service.credential_store_available:
            self._key_status.setText(
                "Secure credential storage is unavailable, so keys cannot be saved."
            )
        else:
            self._key_status.setText("No key stored for this provider.")

    def _refresh_mode_availability(self) -> None:
        provider_id = self._current_provider()
        info = self._catalog.get(provider_id, {})
        is_local = bool(info.get("is_local"))
        model = self.mode_combo.model()
        # Disable local-only when a cloud provider is selected.
        for row in range(self.mode_combo.count()):
            if self.mode_combo.itemData(row) == ContextMode.LOCAL_ONLY.value:
                item = model.item(row) if hasattr(model, "item") else None
                if item is not None:
                    item.setEnabled(is_local)

    def _on_mode_changed(self) -> None:
        mode = self.mode_combo.currentData()
        explanations = {
            ContextMode.MINIMAL.value: (
                "Minimal context: only records relevant to your current question are "
                "retrieved and shared."
            ),
            ContextMode.FULL_AUTHORIZED.value: (
                "Full authorized context: broader authorized categories (memories, people, "
                "places, activities, routines, reminders) may be shared. Requires your "
                "explicit consent and is still limited in size."
            ),
            ContextMode.LOCAL_ONLY.value: (
                "Local only: no personal information leaves this computer. Requires a local "
                "model provider."
            ),
        }
        self.mode_explanation.setText(explanations.get(str(mode), ""))
        granted = self._service.has_full_context_consent()
        self.consent_status.setText(
            "Full-context consent: granted." if granted else "Full-context consent: not granted."
        )
        self._withdraw_consent_button.setEnabled(granted)

    def _collect_settings(self) -> AgentSettings:
        provider_id = self._current_provider()
        mode = ContextMode(str(self.mode_combo.currentData()))
        model = self.model_combo.currentText().strip()
        base_url = self.base_url_edit.text().strip()
        voice = VoiceSettings(
            enabled=self.voice_enabled_check.isChecked(),
            speak_responses=self.speak_check.isChecked(),
            cloud_transcription_allowed=self.cloud_consent_check.isChecked(),
            stt_backend=str(self.stt_combo.currentData()),
            tts_backend=str(self.tts_combo.currentData()),
            max_recording_seconds=self._settings.voice.max_recording_seconds,
        )
        return self._settings.model_copy(
            update={
                "enabled": self.enabled_check.isChecked(),
                "provider_id": provider_id,
                "models": {**self._settings.models, provider_id: model} if model else self._settings.models,
                "base_urls": {**self._settings.base_urls, provider_id: base_url} if base_url else self._settings.base_urls,
                "context_mode": mode,
                "voice": voice,
                "max_tool_rounds": self.rounds_spin.value(),
                "max_tool_calls_per_turn": self.calls_spin.value(),
                "provider_timeout_s": float(self.timeout_spin.value()),
            }
        )

    def _save(self) -> None:
        try:
            candidate = self._collect_settings()
            info = self._catalog.get(candidate.provider_id, {})
            if candidate.context_mode is ContextMode.LOCAL_ONLY and not info.get("is_local"):
                raise AgentError(
                    "Local-only mode requires a local provider.",
                    user_message="Select a local provider before enabling local-only mode.",
                )
            if candidate.context_mode is ContextMode.FULL_AUTHORIZED:
                if not self._service.has_full_context_consent():
                    if not self.consent_check.isChecked():
                        raise AgentError(
                            "Consent checkbox not ticked.",
                            user_message=(
                                "Tick the consent checkbox to use full authorized context."
                            ),
                        )
                    self._service.grant_full_context_consent(
                        ["memories", "people", "places", "activities", "routines", "reminders"]
                    )
            if candidate.voice.cloud_transcription_allowed:
                # Recording consent is independent of full-context consent.
                if not self._service.has_cloud_transcription_consent():
                    self._service.grant_cloud_transcription_consent()
            if not candidate.voice.cloud_transcription_allowed:
                self._service.withdraw_cloud_transcription_consent()

            if candidate.enabled and info.get("requires_api_key"):
                if not self._service.masked_api_key(candidate.provider_id):
                    raise AgentError(
                        "Enabling requires a stored API key.",
                        user_message=(
                            "Add an API key for this provider (and test the connection) "
                            "before enabling the assistant."
                        ),
                    )
            saved = self._service.update_settings(candidate)
            self._settings = saved
            self._audio.update_settings(saved)
            self._feedback.setText("Settings saved.")
            self._feedback.setProperty("warning", False)
            self._feedback.setStyleSheet("color: #166534;")
            self._refresh_key_status()
            self._refresh_voice_status()
            self.settings_saved.emit()
        except AgentError as exc:
            self._show_error(exc.user_message)
        except Exception as exc:  # defensive: never show internals
            self._show_error(f"Settings could not be saved ({type(exc).__name__}).")

    def _show_error(self, message: str) -> None:
        self._feedback.setText(message)
        self._feedback.setStyleSheet("color: #b42318;")

    # ------------------------------------------------------------------ #
    # Key operations (network only in workers)
    # ------------------------------------------------------------------ #
    def _save_key(self) -> None:
        key = self.api_key_edit.text().strip()
        provider_id = self._current_provider()
        if not key:
            self._show_error("Paste a key first.")
            return
        try:
            self._service.save_api_key(provider_id, key)
        except AgentError as exc:
            self._show_error(exc.user_message)
            return
        self.api_key_edit.clear()
        self._feedback.setText("API key stored securely. Test the connection next.")
        self._feedback.setStyleSheet("color: #166534;")
        self._refresh_key_status()

    def _delete_key(self) -> None:
        provider_id = self._current_provider()
        try:
            self._service.delete_api_key(provider_id)
        except AgentError as exc:
            self._show_error(exc.user_message)
            return
        self._feedback.setText("Stored API key deleted.")
        self._feedback.setStyleSheet("color: #166534;")
        self._refresh_key_status()

    def _test_connection(self) -> None:
        provider_id = self._current_provider()
        api_key = self.api_key_edit.text().strip() or None
        model = self.model_combo.currentText().strip() or None
        base_url = self.base_url_edit.text().strip() or None
        self._test_button.setEnabled(False)
        self._test_provider_button.setEnabled(False)
        self._feedback.setText("Testing connection…")
        self._feedback.setStyleSheet("color: #475467;")

        worker = FunctionWorker(
            self._service.test_connection,
            provider_id=provider_id,
            api_key=api_key,
            model=model,
            base_url=base_url,
        )
        worker.signals.finished.connect(self._on_test_finished)
        worker.signals.failed.connect(self._on_test_failed)
        self._pool.start(worker)

    def _on_test_finished(self, result: ConnectionTestResult) -> None:
        self._test_button.setEnabled(True)
        self._test_provider_button.setEnabled(True)
        if result.ok:
            self._feedback.setText("Connection successful. " + result.message)
            self._feedback.setStyleSheet("color: #166534;")
            if result.available_models:
                self.model_combo.clear()
                self.model_combo.addItems(result.available_models)
                current = self._settings.model_for(self._current_provider())
                if current and current in result.available_models:
                    self.model_combo.setCurrentText(current)
        else:
            self._show_error(result.message or "The connection test failed.")

    def _on_test_failed(self, error: object) -> None:
        self._test_button.setEnabled(True)
        self._test_provider_button.setEnabled(True)
        message = error.user_message if isinstance(error, AgentError) else "The connection test failed."
        self._show_error(message)

    def _load_models(self) -> None:
        provider_id = self._current_provider()
        self._refresh_models_button.setEnabled(False)
        self._feedback.setText("Loading models…")
        self._feedback.setStyleSheet("color: #475467;")
        worker = FunctionWorker(self._service.available_models, provider_id)
        worker.signals.finished.connect(self._on_models_loaded)
        worker.signals.failed.connect(self._on_models_failed)
        self._pool.start(worker)

    def _on_models_loaded(self, models) -> None:
        self._refresh_models_button.setEnabled(True)
        self.model_combo.clear()
        for model in models:
            self.model_combo.addItem(model.label or model.id, model.id)
        if not models:
            self._show_error("The provider returned no usable chat models.")
        else:
            self._feedback.setText(f"{len(models)} model(s) available.")
            self._feedback.setStyleSheet("color: #166534;")

    def _on_models_failed(self, error: object) -> None:
        self._refresh_models_button.setEnabled(True)
        message = error.user_message if isinstance(error, AgentError) else "Models could not be loaded."
        self._show_error(message)

    # ------------------------------------------------------------------ #
    # Consent / voice
    # ------------------------------------------------------------------ #
    def _withdraw_consent(self) -> None:
        self._service.withdraw_full_context_consent()
        self.consent_check.setChecked(False)
        index = self.mode_combo.findData(ContextMode.MINIMAL.value)
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)
        self._on_mode_changed()
        self._feedback.setText("Full-context consent withdrawn. Minimal context is now selected.")
        self._feedback.setStyleSheet("color: #166534;")

    def _refresh_voice_status(self) -> None:
        try:
            self._audio.update_settings(self._service.settings())
            status = self._audio.status()
        except Exception:
            self._voice_status.setText("Voice status unavailable.")
            return
        parts = [
            f"Microphone: {'available' if status['recording_available'] else 'unavailable'}",
            f"Transcription: {status['stt_backend']}"
            + ("" if status["stt_available"] else f" ({status['stt_reason']})"),
            f"Speech output: {status['tts_backend']}"
            + ("" if status["tts_available"] else f" ({status['tts_reason']})"),
        ]
        self._voice_status.setText(" · ".join(parts))
