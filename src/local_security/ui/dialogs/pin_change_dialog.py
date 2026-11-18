"""
PIN Change Dialog.
"""
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

from local_security.core.security_manager import SecurityManager


class PINChangeDialog(QDialog):
    """Dialog to safely update the security PIN after verifying the current PIN."""

    def __init__(self, security_manager: SecurityManager, parent=None):
        super().__init__(parent)
        self.sec_mgr = security_manager
        self.setWindowTitle("Change Security PIN")
        self.setFixedSize(400, 380)
        self.setModal(True)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("Change PIN")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        layout.addWidget(QLabel("Current PIN:"))
        self.current_pin = QLineEdit()
        self.current_pin.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.current_pin)

        layout.addWidget(QLabel("New PIN (min 6 digits):"))
        self.new_pin = QLineEdit()
        self.new_pin.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.new_pin)

        layout.addWidget(QLabel("Confirm New PIN:"))
        self.confirm_new_pin = QLineEdit()
        self.confirm_new_pin.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.confirm_new_pin)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #EF4444; font-weight: 600;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        layout.addStretch()

        self.save_btn = QPushButton("Update PIN")
        self.save_btn.clicked.connect(self._on_save)
        layout.addWidget(self.save_btn)

    def _on_save(self):
        cur_p = self.current_pin.text()
        new_p = self.new_pin.text()
        conf_p = self.confirm_new_pin.text()

        user = self.sec_mgr.auth.get_primary_user()
        if not user:
            self.error_label.setText("No active user found.")
            return

        try:
            self.sec_mgr.auth.change_pin(user.user_id, cur_p, new_p, conf_p)
            QMessageBox.information(self, "PIN Changed", "Your security PIN has been updated successfully.")
            self.accept()
        except Exception as e:
            self.error_label.setText(str(e))
