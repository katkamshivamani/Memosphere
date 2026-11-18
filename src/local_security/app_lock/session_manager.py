"""
Secure Session Manager tracking active authenticated user sessions and inactivity timeouts.
"""
import secrets
import threading
import time
from dataclasses import dataclass

from local_security.core.exceptions import SessionExpiredError


@dataclass
class ActiveSession:
    session_id: str
    user_id: str
    username: str
    role: str
    created_at: float
    last_activity_at: float
    is_active: bool = True


class SessionManager:
    """
    Thread-safe session manager maintaining authenticated state and enforcing inactivity timeouts.
    """

    def __init__(self, inactivity_timeout_seconds: int = 300):
        self.inactivity_timeout = inactivity_timeout_seconds
        self._lock = threading.RLock()
        self._current_session: ActiveSession | None = None

    @property
    def has_active_session(self) -> bool:
        with self._lock:
            if not self._current_session or not self._current_session.is_active:
                return False
            # Check timeout
            if time.time() - self._current_session.last_activity_at > self.inactivity_timeout:
                self._current_session.is_active = False
                return False
            return True

    def create_session(self, user_id: str, username: str, role: str) -> ActiveSession:
        """Creates a new cryptographically random authenticated session."""
        with self._lock:
            now = time.time()
            session = ActiveSession(
                session_id=secrets.token_urlsafe(32),
                user_id=user_id,
                username=username,
                role=role,
                created_at=now,
                last_activity_at=now,
                is_active=True,
            )
            self._current_session = session
            return session

    def get_current_session(self) -> ActiveSession | None:
        """Returns the active session or raises SessionExpiredError if timed out."""
        with self._lock:
            if not self._current_session:
                return None
            elapsed = time.time() - self._current_session.last_activity_at
            if elapsed > self.inactivity_timeout or not self._current_session.is_active:
                self._current_session.is_active = False
                raise SessionExpiredError(
                    f"Session expired due to {elapsed:.0f}s of inactivity (timeout: {self.inactivity_timeout}s)."
                )
            return self._current_session

    def touch(self) -> None:
        """Updates the session's last activity timestamp to prevent timeout during active use."""
        with self._lock:
            if self._current_session and self._current_session.is_active:
                elapsed = time.time() - self._current_session.last_activity_at
                if elapsed > self.inactivity_timeout:
                    self._current_session.is_active = False
                    raise SessionExpiredError("Session timed out before touch.")
                self._current_session.last_activity_at = time.time()

    def invalidate_session(self) -> None:
        """Terminates and clears the current active session."""
        with self._lock:
            if self._current_session:
                self._current_session.is_active = False
            self._current_session = None
