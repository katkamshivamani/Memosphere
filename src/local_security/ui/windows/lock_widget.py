"""
Application Lock Overlay Widget that obscures sensitive content when locked.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from local_security.core.exceptions import InvalidCredentialsError, PINLockedError
from local_security.core.security_manager import SecurityManager


class LockOverlayWidget(QWidget):
    """
    Full-size overlay widget displayed when the application is locked.
    Guarantees sensitive data is completely hidden until fresh authentication occurs.
    """

    unlocked = Signal()

    def __init__(self, security_manager: SecurityManager, parent=None):
        super().__init__(parent)
        self.sec_mgr = security_manager
        self._init_ui()

    def _init_ui(self):
        # Semi-transparent or solid dark shield
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: #0B0D11;")

        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Centered card
        card = QFrame()
        card.setFixedSize(400, 440)
        card.setStyleSheet("""
            QFrame {
                background-color: #161A22;
                border: 1px solid #28303F;
                border-radius: 12px;
                padding: 24px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(14)

        icon_lbl = QLabel("🔒")
        icon_lbl.setStyleSheet("font-size: 42px; border: none;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(icon_lbl)

        title = QLabel("Vault Locked")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("border: none; font-size: 20px;")
        card_layout.addWidget(title)

        subtitle = QLabel("Your personal memory data is securely encrypted. Enter your PIN or use Windows Hello to unlock.")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("border: none; color: #94A3B8;")
        card_layout.addWidget(subtitle)

        # PIN field
        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setPlaceholderText("Enter Security PIN")
        self.pin_input.setStyleSheet("font-size: 16px; padding: 10px; border: 1px solid #334155;")
        self.pin_input.returnPressed.connect(self._unlock_with_pin)
        card_layout.addWidget(self.pin_input)

        # PIN button
        self.pin_btn = QPushButton("Unlock with PIN")
        self.pin_btn.clicked.connect(self._unlock_with_pin)
        card_layout.addWidget(self.pin_btn)

        # Biometrics button
        bio_avail, _, _ = self.sec_mgr.auth.biometric_authenticator.is_biometric_available()
        self.bio_btn = QPushButton("Use Biometrics")
        self.bio_btn.setObjectName("secondaryBtn")
        self.bio_btn.setEnabled(bio_avail)
        self.bio_btn.clicked.connect(self._unlock_with_bio)
        card_layout.addWidget(self.bio_btn)

        # Error feedback
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #EF4444; font-weight: 600; border: none;")
        self.error_label.setWordWrap(True)
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.error_label)

        card_layout.addStretch()
        main_layout.addWidget(card)

    def reset_state(self):
        self.pin_input.clear()
        self.error_label.setText("")

    def _unlock_with_pin(self):
        pin = self.pin_input.text()
        if not pin:
            self.error_label.setText("Please enter your PIN.")
            return

        user = self.sec_mgr.auth.get_primary_user()
        username = user.username if user else "owner"
        try:
            self.sec_mgr.unlock_with_pin(username, pin)
            self.reset_state()
            self.unlocked.emit()
        except PINLockedError as e:
            self.error_label.setText(str(e))
        except InvalidCredentialsError as e:
            self.error_label.setText(str(e))
            self.pin_input.clear()
        except Exception as e:
            self.error_label.setText(str(e))

    def _unlock_with_bio(self):
        user = self.sec_mgr.auth.get_primary_user()
        username = user.username if user else "owner"
        self.error_label.setText("Prompting for biometric verification...")
        try:
            self.sec_mgr.unlock_with_biometrics(username)
            self.reset_state()
            self.unlocked.emit()
        except Exception as e:
            self.error_label.setText(f"Biometric failed: {e}")
