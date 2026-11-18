"""
Master Authentication Manager coordinating PIN and Biometric authentication and user profiles.
"""
import json
import uuid
from datetime import UTC, datetime

from local_security.authentication.biometric_interface import BiometricAuthenticator
from local_security.authentication.pin_auth import PINAuthenticator
from local_security.core.exceptions import (
    AuthenticationError,
    InvalidCredentialsError,
    RecordNotFoundError,
)
from local_security.database.database_manager import DatabaseManager
from local_security.models.users import AuditEventType, UserProfile, UserRole


class AuthenticationManager:
    """
    Coordinates PIN authentication, biometric verification, user onboarding,
    and profile authentication state.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        pin_authenticator: PINAuthenticator | None = None,
        biometric_authenticator: BiometricAuthenticator | None = None,
    ):
        self._db = db_manager
        self._pin_auth = pin_authenticator or PINAuthenticator()
        self._bio_auth = biometric_authenticator or BiometricAuthenticator()

    @property
    def pin_authenticator(self) -> PINAuthenticator:
        return self._pin_auth

    @property
    def biometric_authenticator(self) -> BiometricAuthenticator:
        return self._bio_auth

    def log_audit_event(
        self,
        event_type: AuditEventType,
        actor_id: str | None = None,
        module: str | None = None,
        action: str | None = None,
        details: dict | None = None,
    ) -> None:
        """Records an immutable security audit event into the encrypted database."""
        if not self._db.is_connected:
            return

        event_id = str(uuid.uuid4())
        now_iso = datetime.now(UTC).isoformat()
        details_json = json.dumps(details or {})

        try:
            with self._db.transaction() as cur:
                cur.execute(
                    """
                    INSERT INTO audit_events (id, event_type, timestamp, actor_id, module, action, details_json, ip_or_host)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (event_id, event_type.value, now_iso, actor_id, module, action, details_json, "localhost")
                )
        except Exception:
            # Audit logging must not crash primary flow if closed
            pass

    def is_setup_completed(self) -> bool:
        """Returns True if at least one user with a configured PIN exists."""
        if not self._db.is_connected:
            return False
        cur = self._db.cursor()
        cur.execute("SELECT count(*) FROM users WHERE pin_hash IS NOT NULL;")
        row = cur.fetchone()
        return (row[0] > 0) if row else False

    def get_primary_user(self) -> UserProfile | None:
        """Fetches the primary user profile from the database."""
        if not self._db.is_connected:
            return None
        cur = self._db.cursor()
        cur.execute("SELECT * FROM users ORDER BY created_at ASC LIMIT 1;")
        row = cur.fetchone()
        if not row:
            return None

        return UserProfile(
            user_id=row["id"],
            username=row["username"],
            display_name=row["display_name"],
            role=UserRole(row["role"]),
            pin_hash=row["pin_hash"],
            biometrics_enabled=bool(row["biometrics_enabled"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            last_authenticated_at=(
                datetime.fromisoformat(row["last_authenticated_at"]) if row["last_authenticated_at"] else None
            ),
        )

    def setup_initial_user(
        self,
        username: str,
        display_name: str,
        pin: str,
        confirm_pin: str,
        enable_biometrics: bool = False,
    ) -> UserProfile:
        """Sets up the initial primary user account with an Argon2id hashed PIN."""
        if self.is_setup_completed():
            raise AuthenticationError("Initial setup has already been completed.")

        pin_hash = self._pin_auth.create_pin_hash(pin, confirm_pin)
        user_id = str(uuid.uuid4())
        now_iso = datetime.now(UTC).isoformat()

        with self._db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO users (id, username, display_name, role, pin_hash, biometrics_enabled, created_at, updated_at, last_authenticated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (user_id, username, display_name, UserRole.OWNER.value, pin_hash, int(enable_biometrics), now_iso, now_iso, now_iso)
            )

        self.log_audit_event(
            AuditEventType.PIN_CHANGED,
            actor_id=user_id,
            details={"message": "Initial PIN created successfully"}
        )
        self.log_audit_event(
            AuditEventType.AUTH_SUCCESS,
            actor_id=user_id,
            details={"method": "initial_setup"}
        )

        return UserProfile(
            user_id=user_id,
            username=username,
            display_name=display_name,
            role=UserRole.OWNER,
            pin_hash=pin_hash,
            biometrics_enabled=enable_biometrics,
            created_at=datetime.fromisoformat(now_iso),
            updated_at=datetime.fromisoformat(now_iso),
            last_authenticated_at=datetime.fromisoformat(now_iso),
        )

    def authenticate_with_pin(self, username_or_id: str, pin: str) -> UserProfile:
        """Authenticates user with PIN against Argon2id hash."""
        cur = self._db.cursor()
        cur.execute(
            "SELECT * FROM users WHERE username = ? OR id = ? LIMIT 1;",
            (username_or_id, username_or_id)
        )
        row = cur.fetchone()
        if not row:
            self.log_audit_event(
                AuditEventType.AUTH_FAILURE,
                actor_id=username_or_id,
                details={"reason": "User not found"}
            )
            raise RecordNotFoundError(f"User '{username_or_id}' not found.")

        user_id = row["id"]
        pin_hash = row["pin_hash"]
        if not pin_hash:
            raise InvalidCredentialsError("User account has no configured PIN.")

        try:
            valid, needs_rehash = self._pin_auth.verify_pin(user_id, pin, pin_hash)
            now_iso = datetime.now(UTC).isoformat()

            with self._db.transaction() as cur:
                if needs_rehash:
                    new_hash = self._pin_auth.create_pin_hash(pin, pin)
                    cur.execute(
                        "UPDATE users SET pin_hash = ?, last_authenticated_at = ?, updated_at = ? WHERE id = ?;",
                        (new_hash, now_iso, now_iso, user_id)
                    )
                    pin_hash = new_hash
                else:
                    cur.execute(
                        "UPDATE users SET last_authenticated_at = ? WHERE id = ?;",
                        (now_iso, user_id)
                    )

            self.log_audit_event(
                AuditEventType.AUTH_SUCCESS,
                actor_id=user_id,
                details={"method": "pin"}
            )

            return UserProfile(
                user_id=row["id"],
                username=row["username"],
                display_name=row["display_name"],
                role=UserRole(row["role"]),
                pin_hash=pin_hash,
                biometrics_enabled=bool(row["biometrics_enabled"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                last_authenticated_at=datetime.fromisoformat(now_iso),
            )
        except AuthenticationError as e:
            self.log_audit_event(
                AuditEventType.AUTH_FAILURE,
                actor_id=user_id,
                details={"reason": str(e), "method": "pin"}
            )
            raise

    def authenticate_with_biometrics(self, username_or_id: str) -> UserProfile:
        """Authenticates user with OS biometric verification."""
        cur = self._db.cursor()
        cur.execute(
            "SELECT * FROM users WHERE username = ? OR id = ? LIMIT 1;",
            (username_or_id, username_or_id)
        )
        row = cur.fetchone()
        if not row:
            raise RecordNotFoundError(f"User '{username_or_id}' not found.")

        user_id = row["id"]
        if not row["biometrics_enabled"]:
            raise AuthenticationError("Biometric authentication is not enabled for this user account.")

        try:
            verified = self._bio_auth.authenticate_biometric(
                prompt_message="Unlock your Personal Memory Companion"
            )
            if verified:
                # Reset any pending PIN failed attempts upon biometric success
                self._pin_auth.reset_failed_attempts(user_id)
                now_iso = datetime.now(UTC).isoformat()
                with self._db.transaction() as cur:
                    cur.execute("UPDATE users SET last_authenticated_at = ? WHERE id = ?;", (now_iso, user_id))

                self.log_audit_event(
                    AuditEventType.BIOMETRIC_SUCCESS,
                    actor_id=user_id,
                    details={"method": "biometric"}
                )

                return UserProfile(
                    user_id=row["id"],
                    username=row["username"],
                    display_name=row["display_name"],
                    role=UserRole(row["role"]),
                    pin_hash=row["pin_hash"],
                    biometrics_enabled=bool(row["biometrics_enabled"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                    last_authenticated_at=datetime.fromisoformat(now_iso),
                )
        except Exception as e:
            self.log_audit_event(
                AuditEventType.BIOMETRIC_FAILURE,
                actor_id=user_id,
                details={"reason": str(e), "method": "biometric"}
            )
            raise

    def change_pin(self, user_id: str, current_pin: str, new_pin: str, confirm_new_pin: str) -> None:
        """Changes user PIN after verifying current PIN."""
        cur = self._db.cursor()
        cur.execute("SELECT pin_hash FROM users WHERE id = ? LIMIT 1;", (user_id,))
        row = cur.fetchone()
        if not row:
            raise RecordNotFoundError(f"User '{user_id}' not found.")

        # Verify current PIN
        self._pin_auth.verify_pin(user_id, current_pin, row["pin_hash"])

        # Create new hash
        new_hash = self._pin_auth.create_pin_hash(new_pin, confirm_new_pin)
        now_iso = datetime.now(UTC).isoformat()

        with self._db.transaction() as cur:
            cur.execute(
                "UPDATE users SET pin_hash = ?, updated_at = ? WHERE id = ?;",
                (new_hash, now_iso, user_id)
            )

        self.log_audit_event(
            AuditEventType.PIN_CHANGED,
            actor_id=user_id,
            details={"message": "PIN updated successfully"}
        )

    def set_biometrics_enabled(self, user_id: str, enabled: bool) -> None:
        """Enables or disables biometric authentication for a user."""
        now_iso = datetime.now(UTC).isoformat()
        with self._db.transaction() as cur:
            cur.execute(
                "UPDATE users SET biometrics_enabled = ?, updated_at = ? WHERE id = ?;",
                (int(enabled), now_iso, user_id)
            )
