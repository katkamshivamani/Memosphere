"""Microphone controls with an editable transcription preview."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class VoiceControls(QWidget):
    """Recording button plus transcript review.

    Signals
    -------
    start_requested / stop_requested / cancel_requested
        Parent drives the AudioManager (via the controller).
    text_accepted(str)
        The user edited/confirmed a transcript and submitted it.
    """

    start_requested = Signal()
    stop_requested = Signal()
    cancel_requested = Signal()
    text_accepted = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._recording = False
        self._elapsed = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._mic_button = QPushButton("🎤 Speak")
        self._mic_button.setCheckable(True)
        self._mic_button.setToolTip("Record a question (audio is not saved)")
        self._mic_button.clicked.connect(self._toggle_recording)
        row.addWidget(self._mic_button)

        self._stop_button = QPushButton("Stop")
        self._stop_button.setVisible(False)
        self._stop_button.clicked.connect(self._stop)
        row.addWidget(self._stop_button)

        self._status = QLabel("")
        self._status.setProperty("muted", True)
        row.addWidget(self._status)
        row.addStretch(1)
        root.addLayout(row)

        self._recording_timer = QTimer(self)
        self._recording_timer.setInterval(1000)
        self._recording_timer.timeout.connect(self._tick)

        self._preview = QFrame()
        self._preview.setVisible(False)
        self._preview.setProperty("card", True)
        preview_layout = QVBoxLayout(self._preview)
        preview_layout.setContentsMargins(12, 10, 12, 10)
        preview_layout.setSpacing(6)
        label = QLabel("Check the transcription before sending")
        label.setProperty("muted", True)
        preview_layout.addWidget(label)
        self._editor = QTextEdit()
        self._editor.setPlaceholderText("Your spoken question will appear here…")
        self._editor.setFixedHeight(70)
        preview_layout.addWidget(self._editor)
        buttons = QHBoxLayout()
        use = QPushButton("Use this question")
        use.setProperty("primary", True)
        use.clicked.connect(self._accept_text)
        discard = QPushButton("Discard")
        discard.clicked.connect(self._discard)
        buttons.addStretch(1)
        buttons.addWidget(discard)
        buttons.addWidget(use)
        preview_layout.addLayout(buttons)
        root.addWidget(self._preview)

    # ------------------------------------------------------------------ #
    def _toggle_recording(self, checked: bool) -> None:
        if checked:
            self.start_requested.emit()
        else:
            self.stop_requested.emit()

    def _stop(self) -> None:
        self.stop_requested.emit()

    def _tick(self) -> None:
        self._elapsed += 1
        self._status.setText(f"Recording… {self._elapsed}s (audio is not saved)")

    # ------------------------------------------------------------------ #
    def set_recording(self, recording: bool) -> None:
        self._recording = recording
        self._mic_button.blockSignals(True)
        self._mic_button.setChecked(recording)
        self._mic_button.blockSignals(False)
        if recording:
            self._elapsed = 0
            self._status.setText("Recording… 0s (audio is not saved)")
            self._preview.setVisible(False)
            self._recording_timer.start()
            self._stop_button.setVisible(True)
            self._mic_button.setText("● Recording")
        else:
            self._recording_timer.stop()
            self._stop_button.setVisible(False)
            self._mic_button.setText("🎤 Speak")
            self._status.setText("Transcribing…")

    def show_unavailable(self, reason: str) -> None:
        self._mic_button.setEnabled(False)
        self._mic_button.setToolTip(reason)
        self._status.setText(reason)

    def show_transcription(self, text: str, *, is_cloud: bool = False) -> None:
        self._status.setText(
            "Transcription ready (cloud service)" if is_cloud else "Transcription ready (on this computer)"
        )
        self._editor.setPlainText(text)
        self._preview.setVisible(True)
        self._editor.setFocus()

    def show_error(self, message: str) -> None:
        self.set_recording(False)
        self._status.setText(message)
        self._preview.setVisible(False)

    def reset(self) -> None:
        self.set_recording(False)
        self._status.setText("")
        self._preview.setVisible(False)
        self._editor.clear()

    def _accept_text(self) -> None:
        text = self._editor.toPlainText().strip()
        if not text:
            return
        self._preview.setVisible(False)
        self._status.setText("")
        self.text_accepted.emit(text)

    def _discard(self) -> None:
        self._preview.setVisible(False)
        self._editor.clear()
        self._status.setText("")
        self.cancel_requested.emit()
