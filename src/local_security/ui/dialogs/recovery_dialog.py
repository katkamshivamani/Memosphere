"""
Vault Key Backup and Recovery Dialog.
"""
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from local_security.core.security_manager import SecurityManager


class RecoveryDialog(QDialog):
    """Dialog allowing user to export an encrypted backup of their master key using a passphrase."""

    def __init__(self, security_manager: SecurityManager, parent=None):
        super().__init__(parent)
        self.sec_mgr = security_manager
        self.setWindowTitle("Backup & Key Recovery")
        self.setFixedSize(450, 360)
        self.setModal(True)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("Vault Key Backup")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        desc = QLabel(
            "Export an encrypted copy of your vault master key protected by an emergency passphrase. "
            "You can use this file to recover your memories if you move to a new computer or reset your OS account."
        )
        desc.setObjectName("subtitleLabel")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addSpacing(10)

        layout.addWidget(QLabel("Recovery Passphrase (min 8 characters):"))
        self.passphrase_edit = QLineEdit()
        self.passphrase_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.passphrase_edit.setPlaceholderText("Enter a strong passphrase")
        layout.addWidget(self.passphrase_edit)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #EF4444; font-weight: 600;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        layout.addStretch()

        self.export_btn = QPushButton("Export Encrypted Backup File...")
        self.export_btn.clicked.connect(self._on_export)
        layout.addWidget(self.export_btn)

    def _on_export(self):
        passphrase = self.passphrase_edit.text()
        if len(passphrase) < 8:
            self.error_label.setText("Passphrase must be at least 8 characters.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Encrypted Recovery Key",
            str(Path.home() / "memory_vault_recovery.enc.key"),
            "Encrypted Key Files (*.key *.enc);;All Files (*)"
        )
        if not file_path:
            return

        try:
            vault_key = self.sec_mgr.key_manager.retrieve_vault_key(self.sec_mgr.config.key_identifier)
            package = self.sec_mgr.key_manager.export_recovery_package(vault_key, passphrase)
            Path(file_path).write_bytes(package)
            QMessageBox.information(
                self,
                "Backup Created",
                f"Encrypted recovery key successfully saved to:\n{file_path}\n\nKeep this file and passphrase in a safe location."
            )
            self.accept()
        except Exception as e:
            self.error_label.setText(f"Export failed: {e}")
