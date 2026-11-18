"""
PIN Authentication Manager using Argon2id with rate limiting and exponential backoff.
"""
import time
from datetime import UTC

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from local_security.core.configuration import Argon2Config, LockConfig
from local_security.core.exceptions import (
    InvalidCredentialsError,
    PINLockedError,
)
from local_security.models.users import AuthAttemptState

TRIVIAL_PINS = {
    "0000", "1111", "2222", "3333", "4444", "5555", "6666", "7777", "8888", "9999",
    "1234", "4321", "000000", "111111", "222222", "333333", "444444", "555555",
    "666666", "777777", "888888", "999999", "123456", "654321", "123123",
}


class PINAuthenticator:
    """
    Manages PIN creation, Argon2id salted hashing, verification, and retry backoff.
    Guarantees PINs are never stored in plaintext and never logged.
    """

    def __init__(self, argon2_config: Argon2Config | None = None, lock_config: LockConfig | None = None):
        cfg = argon2_config or Argon2Config()
        self._lock_cfg = lock_config or LockConfig()
        self._hasher = PasswordHasher(
            time_cost=cfg.time_cost,
            memory_cost=cfg.memory_cost,
            parallelism=cfg.parallelism,
            hash_len=cfg.hash_len,
            salt_len=cfg.salt_len,
        )
        self._attempt_states: dict[str, AuthAttemptState] = {}

    def validate_pin_policy(self, pin: str, min_length: int = 6) -> tuple[bool, str | None]:
        """Validates that candidate PIN meets length and non-triviality requirements."""
        if not pin or not isinstance(pin, str):
            return False, "PIN must be a non-empty string."
        if len(pin) < min_length:
            return False, f"PIN must be at least {min_length} digits or characters."
        if pin in TRIVIAL_PINS:
            return False, "PIN is too common or easily guessed. Please select a stronger PIN."
        if all(c == pin[0] for c in pin):
            return False, "PIN cannot consist of repeating single characters."
        return True, None

    def create_pin_hash(self, pin: str, confirm_pin: str, min_length: int = 6) -> str:
        """
        Validates candidate PIN and confirmation, and returns Argon2id hash.
        Never persists or logs the plaintext PIN.
        """
        if pin != confirm_pin:
            raise ValueError("PIN and confirmation PIN do not match.")

        valid, error_msg = self.validate_pin_policy(pin, min_length=min_length)
        if not valid:
            raise ValueError(error_msg)

        # Generate Argon2id hash with CSPRNG salt
        return self._hasher.hash(pin)

    def _get_attempt_state(self, user_id: str) -> AuthAttemptState:
        if user_id not in self._attempt_states:
            self._attempt_states[user_id] = AuthAttemptState(user_id=user_id)
        return self._attempt_states[user_id]

    def check_lockout(self, user_id: str) -> None:
        """Checks if user is currently locked out due to excessive failed attempts."""
        state = self._get_attempt_state(user_id)
        if state.locked_until is not None:
            now_ts = time.time()
            lock_ts = state.locked_until.timestamp()
            if now_ts < lock_ts:
                remaining = lock_ts - now_ts
                raise PINLockedError(
                    f"Too many failed PIN attempts. Account locked. Please wait {remaining:.1f} seconds.",
                    retry_after_seconds=remaining,
                )
            else:
                # Lockout period expired
                state.locked_until = None

    def verify_pin(self, user_id: str, candidate_pin: str, stored_hash: str) -> tuple[bool, bool]:
        """
        Verifies candidate PIN against stored Argon2id hash.
        Enforces retry rate-limiting and exponential backoff.
        Returns: (is_valid, needs_rehash)
        Raises: PINLockedError or InvalidCredentialsError
        """
        self.check_lockout(user_id)
        state = self._get_attempt_state(user_id)

        try:
            self._hasher.verify(stored_hash, candidate_pin)
            # Success! Reset failed attempts
            state.failed_attempts = 0
            state.locked_until = None
            needs_rehash = self._hasher.check_needs_rehash(stored_hash)
            return True, needs_rehash

        except (VerifyMismatchError, VerificationError) as e:
            state.failed_attempts += 1
            if state.failed_attempts >= self._lock_cfg.max_failed_attempts:
                # Calculate exponential backoff delay
                exponent = state.failed_attempts - self._lock_cfg.max_failed_attempts
                delay = min(
                    self._lock_cfg.base_backoff_seconds * (2 ** exponent),
                    self._lock_cfg.max_backoff_seconds,
                )
                from datetime import datetime, timedelta
                state.locked_until = datetime.now(UTC) + timedelta(seconds=delay)
                raise PINLockedError(
                    f"Incorrect PIN. Too many consecutive failures. Locked for {delay:.1f}s.",
                    retry_after_seconds=delay,
                ) from e

            remaining_attempts = self._lock_cfg.max_failed_attempts - state.failed_attempts
            raise InvalidCredentialsError(
                f"Incorrect PIN. {remaining_attempts} attempt(s) remaining before temporary lockout."
            ) from e

    def reset_failed_attempts(self, user_id: str) -> None:
        state = self._get_attempt_state(user_id)
        state.failed_attempts = 0
        state.locked_until = None
