"""
First-time setup and PIN creation dialog.
"""
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from local_security.core.security_manager import SecurityManager


class SetupDialog(QDialog):
    """Initial onboarding dialog to configure user profile, PIN, and biometrics."""

    def __init__(self, security_manager: SecurityManager, parent=None):
        super().__init__(parent)
        self.sec_mgr = security_manager
        self.setWindowTitle("Welcome to Personal Memory Companion")
        self.setFixedSize(480, 500)
        self.setModal(True)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(28, 28, 28, 28)

        # Title & Subtitle
        title = QLabel("Initial Security Setup")
        title.setObjectName("titleLabel")
        subtitle = QLabel("Create your personal PIN to encrypt and protect your memory vault.")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(8)

        # Display Name
        layout.addWidget(QLabel("Your Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Eleanor Vance")
        layout.addWidget(self.name_edit)

        # Username
        layout.addWidget(QLabel("Username:"))
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("e.g. eleanor")
        layout.addWidget(self.username_edit)

        # Create PIN
        layout.addWidget(QLabel("Create Security PIN (minimum 6 digits):"))
        self.pin_edit = QLineEdit()
        self.pin_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_edit.setPlaceholderText("Enter at least 6 digits")
        layout.addWidget(self.pin_edit)

        # Confirm PIN
        layout.addWidget(QLabel("Confirm Security PIN:"))
        self.confirm_pin_edit = QLineEdit()
        self.confirm_pin_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_pin_edit.setPlaceholderText("Re-enter your PIN")
        layout.addWidget(self.confirm_pin_edit)

        # Biometrics checkbox
        bio_avail, bio_code, bio_desc = self.sec_mgr.auth.biometric_authenticator.is_biometric_available()
        self.bio_checkbox = QCheckBox("Enable Operating System Biometrics (Windows Hello / Touch ID)")
        self.bio_checkbox.setEnabled(bio_avail)
        self.bio_checkbox.setChecked(bio_avail)
        layout.addWidget(self.bio_checkbox)

        if not bio_avail:
            bio_info = QLabel(f"Note: {bio_desc}")
            bio_info.setObjectName("subtitleLabel")
            bio_info.setWordWrap(True)
            layout.addWidget(bio_info)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #EF4444; font-weight: 600;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        layout.addStretch()

        # Submit button
        self.submit_btn = QPushButton("Complete Setup & Encrypt Vault")
        self.submit_btn.clicked.connect(self._on_submit)
        layout.addWidget(self.submit_btn)

    def _on_submit(self):
        name = self.name_edit.text().strip()
        username = self.username_edit.text().strip()
        pin = self.pin_edit.text().strip()
        confirm_pin = self.confirm_pin_edit.text().strip()
        enable_bio = self.bio_checkbox.isChecked()

        if not name or not username:
            self.error_label.setText("Please enter your name and username.")
            return

        try:
            self.sec_mgr.auth.setup_initial_user(
                username=username,
                display_name=name,
                pin=pin,
                confirm_pin=confirm_pin,
                enable_biometrics=enable_bio,
            )
            QMessageBox.information(
                self,
                "Setup Successful",
                "Your encryption key and PIN have been configured successfully. Your vault is secured."
            )
            self.accept()
        except Exception as e:
            self.error_label.setText(str(e))
