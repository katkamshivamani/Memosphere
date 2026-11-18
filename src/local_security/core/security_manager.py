"""
Master Security Manager orchestrating database lifecycle, platform key protection, authentication,
application locking, permissions, and storage repositories.
"""

from local_security.access_control.permission_manager import PermissionManager
from local_security.app_lock.lock_manager import ApplicationLockManager
from local_security.app_lock.session_manager import ActiveSession, SessionManager
from local_security.authentication.auth_manager import AuthenticationManager
from local_security.core.configuration import SecurityConfig
from local_security.core.exceptions import (
    SecurityError,
)
from local_security.database.database_manager import DatabaseManager
from local_security.encryption.encryption_manager import EncryptionManager
from local_security.encryption.key_manager import KeyManager
from local_security.models.users import AuditEventType
from local_security.platform.factory import PlatformFactory
from local_security.storage.secure_storage import SecureStorage


class SecurityManager:
    """
    Main entry point for the Local Privacy & Security Module.
    Coordinates all security services into a single unified facade for the host application.
    """

    def __init__(self, config: SecurityConfig | None = None):
        self.config = config or SecurityConfig()
        self.config.ensure_directories()

        # Database Manager
        self.db = DatabaseManager(self.config.database_path)

        # Platform Secure Key Storage & Key Manager
        self.key_storage = PlatformFactory.get_key_storage(str(self.config.keystore_path))
        self.key_manager = KeyManager(self.key_storage)

        # Access Control
        self.permissions = PermissionManager()

        # Session & Lock Managers
        self.session_manager = SessionManager(self.config.lock.inactivity_timeout_seconds)
        self.lock_manager = ApplicationLockManager(self.config.lock, self.session_manager)

        # Authentication Manager
        self.auth = AuthenticationManager(self.db)

        # Shared Storage Facade
        self.storage = SecureStorage(self.db, self.permissions)

        self._is_initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    @property
    def is_locked(self) -> bool:
        return self.lock_manager.is_locked

    def initialize(self) -> None:
        """
        Initializes the security layer:
        1. Obtains or generates the 256-bit vault encryption key from OS secure storage.
        2. Opens and verifies the SQLCipher encrypted database.
        3. Starts background idle lock monitor if configured.
        """
        if self._is_initialized and self.db.is_connected:
            return

        vault_key, _ = self.key_manager.get_or_create_vault_key(self.config.key_identifier)
        self.db.connect(vault_key)
        self._is_initialized = True

        # Start idle monitor
        self.lock_manager.start_background_idle_monitor(poll_interval_seconds=1.0)

    def unlock_with_pin(self, username_or_id: str, pin: str) -> ActiveSession:
        """Authenticates with PIN and unlocks the application."""
        user = self.auth.authenticate_with_pin(username_or_id, pin)
        session = self.session_manager.create_session(
            user_id=user.user_id,
            username=user.username,
            role=user.role.value,
        )
        self.lock_manager.unlock_application(session)
        self.auth.log_audit_event(
            AuditEventType.APP_UNLOCKED,
            actor_id=user.user_id,
            details={"method": "pin"}
        )
        return session

    def unlock_with_biometrics(self, username_or_id: str) -> ActiveSession:
        """Authenticates with biometrics and unlocks the application."""
        user = self.auth.authenticate_with_biometrics(username_or_id)
        session = self.session_manager.create_session(
            user_id=user.user_id,
            username=user.username,
            role=user.role.value,
        )
        self.lock_manager.unlock_application(session)
        self.auth.log_audit_event(
            AuditEventType.APP_UNLOCKED,
            actor_id=user.user_id,
            details={"method": "biometric"}
        )
        return session

    def lock(self, reason: str = "manual") -> None:
        """Manually locks the application and terminates the active session."""
        current_sess = self.session_manager.get_current_session()
        actor = current_sess.user_id if current_sess else None
        self.lock_manager.lock_application(reason=reason)
        self.auth.log_audit_event(
            AuditEventType.APP_LOCKED,
            actor_id=actor,
            details={"reason": reason}
        )

    def verify_disk_encryption(self, sample_sensitive_data: list[str] | None = None) -> tuple[bool, list[str]]:
        """Verifies on-disk encryption of the active database file."""
        samples = sample_sensitive_data or []
        return EncryptionManager.verify_disk_encryption(self.config.database_path, samples)

    def rotate_encryption_key(self) -> None:
        """Rotates the vault key in OS secure storage and re-encrypts database pages."""
        if not self.db.is_connected:
            raise SecurityError("Cannot rotate key when database is not connected.")
        self.key_manager.rotate_vault_key(self.config.key_identifier, self.db)
        self.auth.log_audit_event(
            AuditEventType.KEY_ROTATED,
            details={"key_identifier": self.config.key_identifier}
        )

    def shutdown(self) -> None:
        """Safely terminates timers, closes database connection, and clears in-memory state."""
        self.lock_manager.stop_background_idle_monitor()
        self.session_manager.invalidate_session()
        self.db.close()
        self._is_initialized = False
