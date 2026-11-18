"""Authentication, sessions and the application permission store.

The agent's :class:`PermissionGuard` calls straight into this service.  Sessions
are in-memory (per application run) and expire after inactivity; permissions are
persisted in the encrypted database.
"""

from __future__ import annotations

import logging
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from memory_agent.core.exceptions import AuthenticationRequiredError, SessionExpiredError
from memory_agent.security.permissions import ALL_PERMISSIONS, WRITE_PERMISSIONS

logger = logging.getLogger("memory_companion.auth")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Session:
    user_id: str
    username: str
    display_name: str
    role: str
    token: str
    created_at: datetime
    expires_at: datetime

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        return (now or _utcnow()) >= self.expires_at


class AuthError(Exception):
    """Authentication failure with a safe message."""


class UsernameTakenError(AuthError):
    pass


class AuthService:
    """Password auth with Argon2id hashing and in-memory sessions."""

    def __init__(
        self,
        db,
        *,
        session_ttl: timedelta = timedelta(minutes=45),
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._db = db
        self._ttl = session_ttl
        self._clock = clock
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()
        self._hasher = PasswordHasher()

    # ------------------------------------------------------------------ #
    # Registration / login
    # ------------------------------------------------------------------ #
    def register(
        self,
        username: str,
        password: str,
        *,
        display_name: str = "",
        role: str = "owner",
    ) -> Session:
        username = (username or "").strip().lower()
        if len(username) < 3:
            raise AuthError("Choose a username with at least 3 characters.")
        if len(password or "") < 8:
            raise AuthError("Choose a password with at least 8 characters.")

        user_id = f"usr_{uuid.uuid4().hex[:12]}"
        password_hash = self._hasher.hash(password)
        try:
            with self._db.write() as conn:
                conn.execute(
                    "INSERT INTO users (id, username, display_name, password_hash, role, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        user_id,
                        username,
                        (display_name or username).strip(),
                        password_hash,
                        role,
                        self._clock().isoformat(),
                    ),
                )
                for permission in ALL_PERMISSIONS:
                    conn.execute(
                        "INSERT OR REPLACE INTO user_permissions (user_id, permission, granted) "
                        "VALUES (?, ?, 1)",
                        (user_id, permission.value),
                    )
                for permission in sorted(WRITE_PERMISSIONS):
                    conn.execute(
                        "INSERT OR REPLACE INTO user_permissions (user_id, permission, granted) "
                        "VALUES (?, ?, 1)",
                        (user_id, permission),
                    )
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise UsernameTakenError("That username is already in use.") from exc
            raise
        logger.info("Registered user id=%s", user_id)
        return self.login(username, password)

    def login(self, username: str, password: str) -> Session:
        row = self._db.connection().execute(
            "SELECT id, username, display_name, password_hash, role FROM users WHERE username = ?",
            ((username or "").strip().lower(),),
        ).fetchone()
        failure = AuthError("The username or password is incorrect.")
        if row is None:
            # Constant-ish work factor even for unknown users.
            try:
                self._hasher.verify(
                    "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHRzb21lc2FsdA$"
                    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    password or "",
                )
            except Exception:
                pass
            raise failure
        try:
            self._hasher.verify(row[3], password or "")
        except (VerificationError, InvalidHashError):
            raise failure
        now = self._clock()
        session = Session(
            user_id=row[0],
            username=row[1],
            display_name=row[2] or row[1],
            role=row[4],
            token=secrets.token_urlsafe(24),
            created_at=now,
            expires_at=now + self._ttl,
        )
        with self._lock:
            self._sessions[session.user_id] = session
        logger.info("User signed in id=%s", session.user_id)
        return session

    def logout(self, user_id: str) -> None:
        with self._lock:
            self._sessions.pop(user_id, None)

    def logout_token(self, token: str) -> None:
        with self._lock:
            for user_id, session in list(self._sessions.items()):
                if session.token == token:
                    self._sessions.pop(user_id, None)

    # ------------------------------------------------------------------ #
    # Session validation (PermissionChecker protocol)
    # ------------------------------------------------------------------ #
    def validate_session(self, user_id: str) -> bool:
        with self._lock:
            session = self._sessions.get(user_id)
            if session is None:
                return False
            now = self._clock()
            if session.is_expired(now):
                self._sessions.pop(user_id, None)
                return False
            # Sliding expiry, capped to the TTL from now.
            session.expires_at = now + self._ttl
            return True

    def require_session(self, user_id: str) -> Session:
        with self._lock:
            session = self._sessions.get(user_id)
            if session is None:
                raise AuthenticationRequiredError("No active session.")
            if session.is_expired(self._clock()):
                self._sessions.pop(user_id, None)
                raise SessionExpiredError("Session expired.")
            return session

    def current_session(self, user_id: str) -> Optional[Session]:
        with self._lock:
            session = self._sessions.get(user_id)
            if session and not session.is_expired(self._clock()):
                return session
        return None

    # ------------------------------------------------------------------ #
    # Permissions
    # ------------------------------------------------------------------ #
    def has_permission(self, user_id: str, permission: str) -> bool:
        try:
            row = self._db.connection().execute(
                "SELECT granted FROM user_permissions WHERE user_id = ? AND permission = ?",
                (user_id, permission),
            ).fetchone()
        except Exception:
            return False
        return bool(row and row[0])

    def set_permission(self, user_id: str, permission: str, granted: bool) -> None:
        with self._db.write() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_permissions (user_id, permission, granted) "
                "VALUES (?, ?, ?)",
                (user_id, permission, 1 if granted else 0),
            )

    def granted_permissions(self, user_id: str) -> list[str]:
        rows = self._db.connection().execute(
            "SELECT permission FROM user_permissions WHERE user_id = ? AND granted = 1",
            (user_id,),
        ).fetchall()
        return sorted(row[0] for row in rows)

    def list_users(self) -> list[dict]:
        rows = self._db.connection().execute(
            "SELECT id, username, display_name, role, created_at FROM users ORDER BY created_at"
        ).fetchall()
        return [
            {
                "id": row[0],
                "username": row[1],
                "display_name": row[2],
                "role": row[3],
                "created_at": row[4],
            }
            for row in rows
        ]

    def has_any_user(self) -> bool:
        row = self._db.connection().execute("SELECT count(*) FROM users").fetchone()
        return bool(row and row[0])
