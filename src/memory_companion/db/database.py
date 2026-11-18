"""SQLCipher database with verified encryption. No plaintext fallback exists.

Security properties:

* the database key is 256-bit random, stored only through the platform secure
  credential store (Windows DPAPI);
* a plain-SQLite file is detected and refused - the app never "helpfully"
  downgrades encryption;
* connections are per-thread (the agent executes tools on worker threads) and
  use WAL mode with a busy timeout;
* the key never appears in logs, exceptions or settings files.
"""

from __future__ import annotations

import logging
import secrets
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from memory_agent.core.exceptions import CredentialStoreUnavailableError
from memory_agent.security.api_key_manager import CredentialStore

logger = logging.getLogger("memory_companion.db")

try:
    from sqlcipher3 import dbapi2 as sqlcipher
except ImportError as exc:  # pragma: no cover - dependency is pinned
    raise ImportError(
        "sqlcipher3 is required. Encrypted storage will not be replaced with plain SQLite."
    ) from exc


class DatabaseError(Exception):
    """Base class for storage errors (messages never include the key)."""


class DatabaseEncryptionError(DatabaseError):
    """The database is not encrypted or the cipher is unavailable."""


class DatabaseKeyError(DatabaseError):
    """The stored key cannot be loaded or does not open the database."""


@dataclass(frozen=True)
class EncryptionStatus:
    encrypted: bool
    cipher_version: str
    sqlcipher_active: bool
    has_plaintext_header: bool
    database_path: str
    detail: str = ""

    def describe(self) -> str:
        if self.encrypted:
            return f"Encrypted with SQLCipher {self.cipher_version}."
        return f"NOT ENCRYPTED: {self.detail}"


_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'owner',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_permissions (
    user_id TEXT NOT NULL,
    permission TEXT NOT NULL,
    granted INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, permission)
);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_user_updated ON memories(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS people (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    relationship TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_people_user ON people(user_id);

CREATE TABLE IF NOT EXISTS relationships (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    person_id TEXT NOT NULL,
    relationship TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_relationships_person ON relationships(user_id, person_id);

CREATE TABLE IF NOT EXISTS places (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'place',
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_places_user ON places(user_id);

CREATE TABLE IF NOT EXISTS activities (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL,
    place_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activities_user_time ON activities(user_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS routines (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    schedule_hint TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_routines_user ON routines(user_id);

CREATE TABLE IF NOT EXISTS routine_events (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    routine_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    notes TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_routine_events_user_time
    ON routine_events(user_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS reminders (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    due_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled',
    related_type TEXT,
    related_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reminders_user_due ON reminders(user_id, due_at);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    actor TEXT NOT NULL DEFAULT 'system',
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT 'New conversation',
    context_mode TEXT NOT NULL DEFAULT 'minimal',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON agent_conversations(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS agent_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    evidence_json TEXT,
    tool_trace_json TEXT,
    error_code TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES agent_conversations(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON agent_messages(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS agent_suggestions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    conversation_id TEXT,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending_approval',
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_suggestions_user_status
    ON agent_suggestions(user_id, status);
"""


class Database:
    """Thread-safe-by-connection SQLCipher store."""

    KEY_NAME = "database:encryption_key"

    def __init__(self, path: Path, credential_store: CredentialStore) -> None:
        self.path = Path(path)
        self._credentials = credential_store
        self._local = threading.local()
        self._connections: list = []
        self._lock = threading.RLock()
        self._key: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Key management
    # ------------------------------------------------------------------ #
    def _load_or_create_key(self) -> str:
        if self._key:
            return self._key
        if not self._credentials.is_available:
            raise CredentialStoreUnavailableError(
                "Secure credential storage is required to protect the database key. "
                + self._credentials.unavailable_reason,
            )
        key = self._credentials.get_secret(self.KEY_NAME)
        if not key:
            key = secrets.token_hex(32)
            self._credentials.set_secret(self.KEY_NAME, key)
            logger.info("Created a new database encryption key protected by the OS.")
        self._key = key
        return key

    # ------------------------------------------------------------------ #
    # Connections
    # ------------------------------------------------------------------ #
    def _connect(self):
        key = self._load_or_create_key()
        connection = sqlcipher.connect(str(self.path), check_same_thread=False, timeout=15)
        connection.row_factory = sqlcipher.Row
        connection.execute(f"PRAGMA key = \"x'{key}'\"")
        connection.execute("PRAGMA cipher_memory_security = ON")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        try:
            connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except Exception as exc:
            connection.close()
            raise DatabaseKeyError(
                "The database could not be opened with the stored encryption key. "
                "The key may belong to a different Windows user profile."
            ) from exc
        return connection

    def connection(self):
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = self._connect()
            self._local.connection = connection
            with self._lock:
                self._connections.append(connection)
        return connection

    @contextmanager
    def write(self) -> Iterator[object]:
        """Serialized write transaction."""
        with self._lock:
            connection = self.connection()
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    # ------------------------------------------------------------------ #
    # Setup and verification
    # ------------------------------------------------------------------ #
    def initialize(self) -> EncryptionStatus:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            status = self.inspect_encryption()
            if status.has_plaintext_header:
                raise DatabaseEncryptionError(
                    "The existing database file is an ordinary SQLite database. "
                    "Refusing to open it: encryption must not be silently disabled. "
                    "Move the file away or migrate it explicitly."
                )
        connection = self.connection()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version < _SCHEMA_VERSION:
            with self.write() as conn:
                conn.executescript(_SCHEMA_SQL)
                conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            logger.info("Database schema initialised at version %s", _SCHEMA_VERSION)
        status = self.verify_encryption()
        if not status.encrypted:
            raise DatabaseEncryptionError(
                "Encryption verification failed: " + status.detail
            )
        return status

    def inspect_encryption(self) -> EncryptionStatus:
        """Check the raw file header without opening the database."""
        cipher_version = ""
        sqlcipher_active = False
        try:
            probe = sqlcipher.connect(":memory:")
            try:
                row = probe.execute("PRAGMA cipher_version").fetchone()
                cipher_version = str(row[0]) if row and row[0] else ""
            finally:
                probe.close()
            sqlcipher_active = bool(cipher_version)
        except Exception:
            sqlcipher_active = False

        plaintext_header = False
        if self.path.exists():
            try:
                with open(self.path, "rb") as handle:
                    header = handle.read(16)
                plaintext_header = header.startswith(b"SQLite format 3\x00")
            except OSError:
                pass

        encrypted = sqlcipher_active and self.path.exists() and not plaintext_header
        detail = ""
        if not sqlcipher_active:
            detail = "SQLCipher library is not available."
        elif not self.path.exists():
            detail = "Database file does not exist yet."
        elif plaintext_header:
            detail = "The file has a plaintext SQLite header."
        return EncryptionStatus(
            encrypted=encrypted,
            cipher_version=cipher_version,
            sqlcipher_active=sqlcipher_active,
            has_plaintext_header=plaintext_header,
            database_path=str(self.path),
            detail=detail,
        )

    def verify_encryption(self) -> EncryptionStatus:
        """Active verification: cipher present, file encrypted, key works."""
        status = self.inspect_encryption()
        if status.has_plaintext_header:
            return status
        if not status.sqlcipher_active:
            return status
        try:
            connection = self.connection()
            connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
            cipher_row = connection.execute("PRAGMA cipher_version").fetchone()
            cipher_version = str(cipher_row[0]) if cipher_row and cipher_row[0] else status.cipher_version
        except Exception as exc:
            return EncryptionStatus(
                encrypted=False,
                cipher_version=status.cipher_version,
                sqlcipher_active=status.sqlcipher_active,
                has_plaintext_header=status.has_plaintext_header,
                database_path=str(self.path),
                detail=f"Key verification failed ({type(exc).__name__}).",
            )
        return EncryptionStatus(
            encrypted=not status.has_plaintext_header and bool(cipher_version),
            cipher_version=cipher_version,
            sqlcipher_active=status.sqlcipher_active,
            has_plaintext_header=status.has_plaintext_header,
            database_path=str(self.path),
            detail="" if cipher_version else "SQLCipher reports no cipher version.",
        )

    def close(self) -> None:
        with self._lock:
            for connection in self._connections:
                try:
                    connection.close()
                except Exception:
                    pass
            self._connections.clear()
        self._local = threading.local()
