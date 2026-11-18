"""
Main Desktop Security Dashboard and Application Window for Personal Memory Companion.
"""
from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from local_security.app_lock.lock_manager import LockState
from local_security.core.security_manager import SecurityManager
from local_security.models.records import MemoryRecord
from local_security.ui.dialogs.pin_change_dialog import PINChangeDialog
from local_security.ui.dialogs.recovery_dialog import RecoveryDialog
from local_security.ui.themes import DARK_THEME_QSS, LIGHT_THEME_QSS
from local_security.ui.windows.lock_widget import LockOverlayWidget


class SecurityDashboardWindow(QMainWindow):
    """Primary desktop window displaying security metrics, database status, audit logs, and settings."""

    def __init__(self, security_manager: SecurityManager):
        super().__init__()
        self.sec_mgr = security_manager
        self.setWindowTitle("Personal Memory Companion - Security & Privacy Center")
        self.resize(960, 680)
        self.setMinimumSize(850, 600)

        self._dark_mode = True
        self.setStyleSheet(DARK_THEME_QSS)

        self._init_ui()
        self._setup_event_listeners()
        self._refresh_dashboard_data()

    def _init_ui(self):
        # Central widget uses QStackedWidget:
        # Index 0: Main Dashboard Content
        # Index 1: Lock Overlay Widget
        self.stacked_widget = QStackedWidget(self)
        self.setCentralWidget(self.stacked_widget)

        # Main content container
        self.main_content = QWidget()
        main_layout = QVBoxLayout(self.main_content)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # Header bar
        header = self._create_header()
        main_layout.addLayout(header)

        # Tab widget
        self.tabs = QTabWidget()
        self.tab_dashboard = self._create_dashboard_tab()
        self.tab_storage = self._create_storage_tab()
        self.tab_audit = self._create_audit_tab()
        self.tab_settings = self._create_settings_tab()

        self.tabs.addTab(self.tab_dashboard, "🛡️ Security Dashboard")
        self.tabs.addTab(self.tab_storage, "📦 Encrypted Storage")
        self.tabs.addTab(self.tab_audit, "📋 Audit Events")
        self.tabs.addTab(self.tab_settings, "⚙️ Settings")

        main_layout.addWidget(self.tabs)
        self.stacked_widget.addWidget(self.main_content)

        # Lock Overlay Widget
        self.lock_overlay = LockOverlayWidget(self.sec_mgr)
        self.lock_overlay.unlocked.connect(self._on_unlocked)
        self.stacked_widget.addWidget(self.lock_overlay)

        # Initial lock state check
        if self.sec_mgr.is_locked:
            self.stacked_widget.setCurrentWidget(self.lock_overlay)
        else:
            self.stacked_widget.setCurrentWidget(self.main_content)

    def _create_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(12)

        title = QLabel("Memory Vault Security Center")
        title.setObjectName("titleLabel")
        header.addWidget(title)

        header.addStretch()

        # Offline Privacy Badge
        self.privacy_badge = QLabel("100% Local-First & Offline")
        self.privacy_badge.setObjectName("statusBadgeSuccess")
        header.addWidget(self.privacy_badge)

        # Theme Toggle
        self.theme_btn = QPushButton("🌓 Toggle Theme")
        self.theme_btn.setObjectName("secondaryBtn")
        self.theme_btn.clicked.connect(self._toggle_theme)
        header.addWidget(self.theme_btn)

        # Quick Manual Lock Button
        self.lock_btn = QPushButton("🔒 Lock Now")
        self.lock_btn.setObjectName("dangerBtn")
        self.lock_btn.clicked.connect(self._on_manual_lock)
        header.addWidget(self.lock_btn)

        return header

    def _create_dashboard_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)

        grid = QGridLayout()
        grid.setSpacing(14)

        # Card 1: SQLCipher Database Status
        db_group = QGroupBox("Encrypted Database (SQLCipher)")
        db_layout = QVBoxLayout(db_group)
        self.lbl_cipher_ver = QLabel("Cipher Version: Loading...")
        self.lbl_db_path = QLabel("Database Path: Loading...")
        self.lbl_page_size = QLabel("Page Size: 4096 bytes")
        self.lbl_kdf = QLabel("KDF Algorithm: PBKDF2_HMAC_SHA512 (256,000 iterations)")
        self.lbl_entropy = QLabel("Disk Status: Encrypted")

        db_layout.addWidget(self.lbl_cipher_ver)
        db_layout.addWidget(self.lbl_db_path)
        db_layout.addWidget(self.lbl_page_size)
        db_layout.addWidget(self.lbl_kdf)
        db_layout.addWidget(self.lbl_entropy)

        btn_verify = QPushButton("Run Live On-Disk Encryption Audit")
        btn_verify.clicked.connect(self._run_disk_audit)
        db_layout.addWidget(btn_verify)
        grid.addWidget(db_group, 0, 0)

        # Card 2: Authentication & Biometrics
        auth_group = QGroupBox("Authentication & Platform Key Protection")
        auth_layout = QVBoxLayout(auth_group)
        self.lbl_bio_status = QLabel("Biometric Hardware: Checking...")
        self.lbl_pin_status = QLabel("PIN Protection: Argon2id (Salted & Rate-limited)")
        self.lbl_backend = QLabel("Key Backend: Windows DPAPI")
        self.lbl_last_auth = QLabel("Last Authentication: Never")

        auth_layout.addWidget(self.lbl_bio_status)
        auth_layout.addWidget(self.lbl_pin_status)
        auth_layout.addWidget(self.lbl_backend)
        auth_layout.addWidget(self.lbl_last_auth)

        btn_rot = QPushButton("Rotate Database Encryption Key")
        btn_rot.setObjectName("secondaryBtn")
        btn_rot.clicked.connect(self._on_rotate_key)
        auth_layout.addWidget(btn_rot)
        grid.addWidget(auth_group, 0, 1)

        layout.addLayout(grid)

        # Quick Actions
        actions_group = QGroupBox("Security Actions")
        act_layout = QHBoxLayout(actions_group)

        btn_backup = QPushButton("Export Encrypted Backup Key...")
        btn_backup.clicked.connect(self._on_export_backup)
        act_layout.addWidget(btn_backup)

        btn_pin = QPushButton("Change Security PIN...")
        btn_pin.setObjectName("secondaryBtn")
        btn_pin.clicked.connect(self._on_change_pin)
        act_layout.addWidget(btn_pin)

        layout.addWidget(actions_group)
        layout.addStretch()
        return widget

    def _create_storage_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)

        desc = QLabel("Universal Memory Vault - Explore how data is encrypted and indexed locally with FTS5.")
        desc.setObjectName("subtitleLabel")
        layout.addWidget(desc)

        # Search Bar & Add Button
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search encrypted memories using FTS5 (e.g. walk, medication, family)...")
        self.search_input.returnPressed.connect(self._search_memories)
        search_layout.addWidget(self.search_input)

        btn_search = QPushButton("Search")
        btn_search.clicked.connect(self._search_memories)
        search_layout.addWidget(btn_search)

        btn_add = QPushButton("+ Add Sample Memory")
        btn_add.setObjectName("secondaryBtn")
        btn_add.clicked.connect(self._add_sample_memory)
        search_layout.addWidget(btn_add)
        layout.addLayout(search_layout)

        # Records Table
        self.records_table = QTableWidget(0, 4)
        self.records_table.setHorizontalHeaderLabels(["Title", "Content Preview", "Category", "Caregiver Shared"])
        self.records_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.records_table)

        return widget

    def _create_audit_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)

        top_layout = QHBoxLayout()
        desc = QLabel("Immutable Security Audit Events Log (Stored in SQLCipher database)")
        desc.setObjectName("subtitleLabel")
        top_layout.addWidget(desc)
        top_layout.addStretch()

        btn_refresh = QPushButton("Refresh Log")
        btn_refresh.setObjectName("secondaryBtn")
        btn_refresh.clicked.connect(self._refresh_audit_logs)
        top_layout.addWidget(btn_refresh)
        layout.addLayout(top_layout)

        self.audit_table = QTableWidget(0, 5)
        self.audit_table.setHorizontalHeaderLabels(["Timestamp (UTC)", "Event Type", "Actor", "Module / Action", "Details"])
        self.audit_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.audit_table)

        return widget

    def _create_settings_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)

        # Auto Lock Settings
        lock_box = QGroupBox("Application Lock & Inactivity")
        l_layout = QVBoxLayout(lock_box)

        t_layout = QHBoxLayout()
        t_layout.addWidget(QLabel("Auto-Lock Timeout:"))
        self.timeout_combo = QComboBox()
        self.timeout_combo.addItems(["1 Minute", "5 Minutes", "15 Minutes", "30 Minutes", "Never (Testing Only)"])
        self.timeout_combo.setCurrentIndex(1)  # 5 min default
        self.timeout_combo.currentIndexChanged.connect(self._on_timeout_changed)
        t_layout.addWidget(self.timeout_combo)
        t_layout.addStretch()
        l_layout.addLayout(t_layout)

        self.chk_minimize = QCheckBox("Lock application when minimized")
        self.chk_minimize.setChecked(self.sec_mgr.config.lock.lock_on_minimize)
        self.chk_minimize.toggled.connect(self._on_toggle_minimize)
        l_layout.addWidget(self.chk_minimize)

        self.chk_focus = QCheckBox("Lock application when window loses focus")
        self.chk_focus.setChecked(self.sec_mgr.config.lock.lock_on_focus_loss)
        self.chk_focus.toggled.connect(self._on_toggle_focus)
        l_layout.addWidget(self.chk_focus)

        layout.addWidget(lock_box)

        # Biometrics Settings
        bio_box = QGroupBox("Biometric Settings")
        b_layout = QVBoxLayout(bio_box)
        self.chk_bio_enabled = QCheckBox("Enable Windows Hello / OS Biometrics")
        user = self.sec_mgr.auth.get_primary_user()
        self.chk_bio_enabled.setChecked(bool(user and user.biometrics_enabled))
        self.chk_bio_enabled.toggled.connect(self._on_toggle_bio)
        b_layout.addWidget(self.chk_bio_enabled)
        layout.addWidget(bio_box)

        layout.addStretch()
        return widget

    def _setup_event_listeners(self):
        # Listen for lock manager state changes
        self.sec_mgr.lock_manager.register_state_listener(self._on_lock_state_change)

        # Periodic timer to check inactivity and refresh UI
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._on_ui_tick)
        self.ui_timer.start(1000)

    def _on_ui_tick(self):
        # Refresh idle status
        if not self.sec_mgr.is_locked:
            self.sec_mgr.lock_manager.check_inactivity()

    def _on_lock_state_change(self, state: LockState):
        if state == LockState.LOCKED:
            self.lock_overlay.reset_state()
            self.stacked_widget.setCurrentWidget(self.lock_overlay)
        else:
            self.stacked_widget.setCurrentWidget(self.main_content)
            self._refresh_dashboard_data()

    def _on_unlocked(self):
        self.stacked_widget.setCurrentWidget(self.main_content)
        self._refresh_dashboard_data()

    def _on_manual_lock(self):
        self.sec_mgr.lock(reason="manual_ui")

    def _toggle_theme(self):
        self._dark_mode = not self._dark_mode
        self.setStyleSheet(DARK_THEME_QSS if self._dark_mode else LIGHT_THEME_QSS)

    def _refresh_dashboard_data(self):
        if not self.sec_mgr.db.is_connected:
            return

        # Cipher version
        ver = self.sec_mgr.db.get_cipher_version()
        self.lbl_cipher_ver.setText(f"Cipher Version: SQLCipher {ver}")
        self.lbl_db_path.setText(f"Database Path: {self.sec_mgr.config.database_path.name}")

        # Biometric status
        bio_avail, code, desc = self.sec_mgr.auth.biometric_authenticator.is_biometric_available()
        status_text = "Available" if bio_avail else f"Unavailable ({code.value})"
        self.lbl_bio_status.setText(f"Biometric Hardware: {status_text}")

        # Key storage backend
        plat_info = self.sec_mgr.key_storage.__class__.__name__
        self.lbl_backend.setText(f"Key Storage Adapter: {plat_info}")

        # Last auth
        user = self.sec_mgr.auth.get_primary_user()
        if user and user.last_authenticated_at:
            self.lbl_last_auth.setText(f"Last Authentication: {user.last_authenticated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        self._refresh_memories_table()
        self._refresh_audit_logs()

    def _run_disk_audit(self):
        is_secure, findings = self.sec_mgr.verify_disk_encryption()
        msg = "\n".join(f"• {f}" for f in findings)
        if is_secure:
            QMessageBox.information(self, "Disk Encryption Audit Passed", f"Audit Succeeded:\n\n{msg}")
        else:
            QMessageBox.warning(self, "Audit Findings", f"Audit Completed with warnings:\n\n{msg}")

    def _on_rotate_key(self):
        confirm = QMessageBox.question(
            self,
            "Confirm Key Rotation",
            "This will generate a new 256-bit encryption key, re-encrypt all database pages, "
            "and update OS secure storage. Proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                self.sec_mgr.rotate_encryption_key()
                QMessageBox.information(self, "Key Rotated", "Database successfully re-keyed with new 256-bit key.")
                self._refresh_dashboard_data()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Key rotation failed: {e}")

    def _on_export_backup(self):
        dlg = RecoveryDialog(self.sec_mgr, self)
        dlg.exec()

    def _on_change_pin(self):
        dlg = PINChangeDialog(self.sec_mgr, self)
        dlg.exec()

    def _refresh_memories_table(self):
        memories = self.sec_mgr.storage.memories.search_memories("")
        self.records_table.setRowCount(len(memories))
        for row_idx, mem in enumerate(memories):
            self.records_table.setItem(row_idx, 0, QTableWidgetItem(mem.title))
            self.records_table.setItem(row_idx, 1, QTableWidgetItem(mem.content[:60] + "..."))
            self.records_table.setItem(row_idx, 2, QTableWidgetItem(mem.category))
            self.records_table.setItem(row_idx, 3, QTableWidgetItem("Yes" if mem.is_shared_with_caregiver else "No"))

    def _search_memories(self):
        query = self.search_input.text().strip()
        memories = self.sec_mgr.storage.memories.search_memories(query)
        self.records_table.setRowCount(len(memories))
        for row_idx, mem in enumerate(memories):
            self.records_table.setItem(row_idx, 0, QTableWidgetItem(mem.title))
            self.records_table.setItem(row_idx, 1, QTableWidgetItem(mem.content[:60] + "..."))
            self.records_table.setItem(row_idx, 2, QTableWidgetItem(mem.category))
            self.records_table.setItem(row_idx, 3, QTableWidgetItem("Yes" if mem.is_shared_with_caregiver else "No"))

    def _add_sample_memory(self):
        sample = MemoryRecord(
            title=f"Memory Note {datetime.now().strftime('%H:%M:%S')}",
            content="Sample encrypted note saved into SQLCipher vault.",
            category="general",
            is_shared_with_caregiver=True,
        )
        self.sec_mgr.storage.memories.save_memory(sample)
        self._refresh_memories_table()

    def _refresh_audit_logs(self):
        cur = self.sec_mgr.db.cursor()
        cur.execute("SELECT * FROM audit_events ORDER BY timestamp DESC LIMIT 50;")
        rows = cur.fetchall()
        self.audit_table.setRowCount(len(rows))
        for r_idx, row in enumerate(rows):
            self.audit_table.setItem(r_idx, 0, QTableWidgetItem(row["timestamp"]))
            self.audit_table.setItem(r_idx, 1, QTableWidgetItem(row["event_type"]))
            self.audit_table.setItem(r_idx, 2, QTableWidgetItem(row["actor_id"] or "system"))
            self.audit_table.setItem(r_idx, 3, QTableWidgetItem(f"{row['module'] or ''} / {row['action'] or ''}"))
            self.audit_table.setItem(r_idx, 4, QTableWidgetItem(row["details_json"]))

    def _on_timeout_changed(self, index: int):
        timeouts = [60, 300, 900, 1800, 999999]
        new_val = timeouts[index]
        self.sec_mgr.config.lock.inactivity_timeout_seconds = new_val
        self.sec_mgr.session_manager.inactivity_timeout = new_val

    def _on_toggle_minimize(self, checked: bool):
        self.sec_mgr.config.lock.lock_on_minimize = checked

    def _on_toggle_focus(self, checked: bool):
        self.sec_mgr.config.lock.lock_on_focus_loss = checked

    def _on_toggle_bio(self, checked: bool):
        user = self.sec_mgr.auth.get_primary_user()
        if user:
            self.sec_mgr.auth.set_biometrics_enabled(user.user_id, checked)
            self._refresh_dashboard_data()

    def changeEvent(self, event):
        """Monitors minimize and activate events."""
        super().changeEvent(event)
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.WindowStateChange:
            if self.isMinimized():
                self.sec_mgr.lock_manager.on_window_minimized()
        elif event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            self.sec_mgr.lock_manager.on_window_focus_lost()
