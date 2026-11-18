"""Sign-in and first-run account creation."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from memory_companion.security.auth import AuthError, AuthService, Session, UsernameTakenError


class LoginDialog(QDialog):
    """Modal login/registration dialog returning an authenticated session."""

    def __init__(self, auth: AuthService, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._auth = auth
        self.session: Optional[Session] = None
        self.setWindowTitle("Personal Memory Companion")
        self.setMinimumWidth(440)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("Personal Memory Companion")
        title.setProperty("h1", True)
        layout.addWidget(title)
        subtitle = QLabel(
            "Your memories stay in an encrypted database on this computer."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", True)
        layout.addWidget(subtitle)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_login_tab(), "Sign in")
        if not auth.has_any_user():
            self._tabs.addTab(self._build_register_tab(), "Create account")
        else:
            self._tabs.addTab(self._build_register_tab(), "Create account")
            self._tabs.setCurrentIndex(0)
        layout.addWidget(self._tabs)

        self._error = QLabel("")
        self._error.setWordWrap(True)
        self._error.setProperty("warning", True)
        layout.addWidget(self._error)

        self._database_note = QLabel("")
        self._database_note.setWordWrap(True)
        self._database_note.setProperty("muted", True)
        layout.addWidget(self._database_note)

        quit_row = QVBoxLayout()
        quit_button = QPushButton("Quit")
        quit_button.setProperty("flat", True)
        quit_button.clicked.connect(self.reject)
        quit_row.addWidget(quit_button, 0, Qt.AlignRight)
        layout.addLayout(quit_row)

    # ------------------------------------------------------------------ #
    def _build_login_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        form = QFormLayout()
        form.setSpacing(8)
        self.login_username = QLineEdit()
        self.login_username.setPlaceholderText("Username")
        self.login_password = QLineEdit()
        self.login_password.setEchoMode(QLineEdit.Password)
        self.login_password.setPlaceholderText("Password")
        self.login_password.returnPressed.connect(self._attempt_login)
        form.addRow("Username", self.login_username)
        form.addRow("Password", self.login_password)
        layout.addLayout(form)
        button = QPushButton("Sign in")
        button.setProperty("primary", True)
        button.clicked.connect(self._attempt_login)
        layout.addWidget(button)
        layout.addStretch(1)
        return page

    def _build_register_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        form = QFormLayout()
        form.setSpacing(8)
        self.register_name = QLineEdit()
        self.register_name.setPlaceholderText("How should the app address you?")
        self.register_username = QLineEdit()
        self.register_username.setPlaceholderText("At least 3 characters")
        self.register_password = QLineEdit()
        self.register_password.setEchoMode(QLineEdit.Password)
        self.register_password.setPlaceholderText("At least 8 characters")
        self.register_confirm = QLineEdit()
        self.register_confirm.setEchoMode(QLineEdit.Password)
        form.addRow("Display name", self.register_name)
        form.addRow("Username", self.register_username)
        form.addRow("Password", self.register_password)
        form.addRow("Confirm password", self.register_confirm)
        layout.addLayout(form)
        self._register_consent = QCheckBox(
            "I understand this app stores personal information locally in an "
            "encrypted database and that I can delete it at any time."
        )
        self._register_consent.setWordWrap(True)
        layout.addWidget(self._register_consent)
        button = QPushButton("Create account")
        button.setProperty("primary", True)
        button.clicked.connect(self._attempt_register)
        layout.addWidget(button)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------ #
    def set_database_note(self, text: str) -> None:
        self._database_note.setText(text)

    def prefill_username(self, username: str) -> None:
        self.login_username.setText(username)

    def _attempt_login(self) -> None:
        self._error.setText("")
        try:
            self.session = self._auth.login(
                self.login_username.text(), self.login_password.text()
            )
        except AuthError as exc:
            self._error.setText(str(exc))
            return
        self.accept()

    def _attempt_register(self) -> None:
        self._error.setText("")
        username = self.register_username.text().strip()
        password = self.register_password.text()
        confirm = self.register_confirm.text()
        if password != confirm:
            self._error.setText("The passwords do not match.")
            return
        if not self._register_consent.isChecked():
            self._error.setText("Please confirm that you understand how your data is stored.")
            return
        try:
            self.session = self._auth.register(
                username,
                password,
                display_name=self.register_name.text().strip(),
            )
        except UsernameTakenError as exc:
            self._error.setText(str(exc))
            return
        except AuthError as exc:
            self._error.setText(str(exc))
            return
        except Exception as exc:  # database failure
            QMessageBox.critical(
                self,
                "Account could not be created",
                f"The encrypted database rejected the change ({type(exc).__name__}).",
            )
            return
        self.accept()
