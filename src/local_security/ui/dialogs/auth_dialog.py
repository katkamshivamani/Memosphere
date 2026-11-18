"""
Authentication dialog supporting PIN and Biometric unlocking.
"""
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout

from local_security.core.exceptions import InvalidCredentialsError, PINLockedError
from local_security.core.security_manager import SecurityManager


class AuthDialog(QDialog):
    """User unlock dialog presented when starting or after locking."""

    def __init__(self, security_manager: SecurityManager, parent=None):
        super().__init__(parent)
        self.sec_mgr = security_manager
        self.setWindowTitle("Unlock Memory Companion")
        self.setFixedSize(420, 420)
        self.setModal(True)
        self._user = self.sec_mgr.auth.get_primary_user()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(28, 28, 28, 28)

        # Title & User welcome
        title = QLabel("Vault Locked")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        user_name = self._user.display_name if self._user else "User"
        welcome_lbl = QLabel(f"Welcome back, {user_name}. Please authenticate to continue.")
        welcome_lbl.setObjectName("subtitleLabel")
        welcome_lbl.setWordWrap(True)
        layout.addWidget(welcome_lbl)
        layout.addSpacing(10)

        # PIN input
        layout.addWidget(QLabel("Security PIN:"))
        self.pin_edit = QLineEdit()
        self.pin_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_edit.setPlaceholderText("Enter PIN")
        self.pin_edit.setStyleSheet("font-size: 18px; padding: 10px;")
        self.pin_edit.returnPressed.connect(self._on_pin_unlock)
        layout.addWidget(self.pin_edit)

        # Unlock with PIN button
        self.unlock_pin_btn = QPushButton("Unlock with PIN")
        self.unlock_pin_btn.clicked.connect(self._on_pin_unlock)
        layout.addWidget(self.unlock_pin_btn)

        # Biometrics button
        bio_avail, _, _ = self.sec_mgr.auth.biometric_authenticator.is_biometric_available()
        bio_enabled = bool(self._user and self._user.biometrics_enabled)

        self.bio_btn = QPushButton("Use Biometrics (Windows Hello / Touch ID)")
        self.bio_btn.setObjectName("secondaryBtn")
        self.bio_btn.setEnabled(bio_avail and bio_enabled)
        self.bio_btn.clicked.connect(self._on_bio_unlock)
        layout.addWidget(self.bio_btn)

        # Error / Feedback label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #EF4444; font-weight: 600;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()

    def _on_pin_unlock(self):
        pin = self.pin_edit.text()
        if not pin:
            self.status_label.setText("Please enter your PIN.")
            return

        username = self._user.username if self._user else "owner"
        try:
            self.sec_mgr.unlock_with_pin(username, pin)
            self.accept()
        except PINLockedError as e:
            self.status_label.setText(str(e))
        except InvalidCredentialsError as e:
            self.status_label.setText(str(e))
            self.pin_edit.clear()
        except Exception as e:
            self.status_label.setText(f"Error: {e}")

    def _on_bio_unlock(self):
        username = self._user.username if self._user else "owner"
        self.status_label.setText("Prompting for biometric verification...")
        try:
            self.sec_mgr.unlock_with_biometrics(username)
            self.accept()
        except Exception as e:
            self.status_label.setText(f"Biometric failed: {e}. Please enter PIN.")
