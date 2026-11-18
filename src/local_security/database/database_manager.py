"""
Database Manager for SQLCipher encrypted database connections, verification, and transactions.
"""
import threading
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

try:
    import sqlcipher3
except ImportError as err:
    raise ImportError(
        "SQLCipher driver 'sqlcipher3' is required but not installed. "
        "Please install 'sqlcipher3-wheels'."
    ) from err

from local_security.core.exceptions import DatabaseError, DecryptionError
from local_security.database.migrations.migrator import DatabaseMigrator


class DatabaseManager:
    """
    Manages connections to the local SQLCipher encrypted SQLite database.
    Guarantees encryption, verifies credentials on open, and provides thread-safe access.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._conn: Any | None = None
        self._current_key_bytes: bytes | None = None

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    def connect(self, encryption_key: bytes) -> None:
        """
        Opens connection to SQLCipher database and authenticates with 256-bit binary key.
        Raises DecryptionError if decryption fails.
        """
        if not isinstance(encryption_key, (bytes, bytearray)) or len(encryption_key) != 32:
            raise ValueError("Encryption key must be exactly 32 bytes (256-bit).")

        with self._lock:
            if self._conn is not None:
                self.close()

            # Ensure parent directory exists
            if self.db_path != Path(":memory:"):
                self.db_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                conn = sqlcipher3.connect(
                    str(self.db_path),
                    check_same_thread=False,
                    timeout=10.0
                )
                conn.row_factory = sqlcipher3.Row
                cursor = conn.cursor()

                # Provide raw hex key to SQLCipher PRAGMA key
                hex_key = encryption_key.hex()
                cursor.execute(f"PRAGMA key = \"x'{hex_key}'\";")

                # Configure standard cipher parameters
                cursor.execute("PRAGMA cipher_page_size = 4096;")
                cursor.execute("PRAGMA kdf_iter = 256000;")
                cursor.execute("PRAGMA cipher_hmac_algorithm = HMAC_SHA512;")
                cursor.execute("PRAGMA cipher_default_kdf_algorithm = PBKDF2_HMAC_SHA512;")
                cursor.execute("PRAGMA foreign_keys = ON;")

                # Verification query: attempt to read sqlite_master
                # If key is invalid or file corrupted, SQLCipher fails here
                cursor.execute("SELECT count(*) FROM sqlite_master;")
                cursor.fetchone()

                self._conn = conn
                self._current_key_bytes = bytes(encryption_key)

                # Run migrations
                migrator = DatabaseMigrator(self._conn)
                migrator.apply_all()

            except sqlcipher3.DatabaseError as e:
                if self._conn:
                    with suppress(Exception):
                        self._conn.close()
                    self._conn = None
                raise DecryptionError(
                    f"Failed to decrypt database at {self.db_path}: invalid key or corrupted file. Details: {e}"
                ) from e
            except Exception as e:
                if self._conn:
                    with suppress(Exception):
                        self._conn.close()
                    self._conn = None
                raise DatabaseError(f"Database connection error: {e}") from e

    def get_cipher_version(self) -> str:
        """Returns the active SQLCipher library version."""
        with self._lock:
            if not self._conn:
                raise DatabaseError("Database is not connected.")
            cursor = self._conn.cursor()
            cursor.execute("PRAGMA cipher_version;")
            row = cursor.fetchone()
            return row[0] if row else "unknown"

    def rekey(self, new_key_bytes: bytes) -> None:
        """
        Re-encrypts the entire database file with a new 256-bit encryption key.
        Performs atomic re-encryption via SQLCipher PRAGMA rekey.
        """
        if not isinstance(new_key_bytes, (bytes, bytearray)) or len(new_key_bytes) != 32:
            raise ValueError("New encryption key must be exactly 32 bytes.")

        with self._lock:
            if not self._conn:
                raise DatabaseError("Cannot rekey: database is not connected.")

            hex_new_key = new_key_bytes.hex()
            cursor = self._conn.cursor()
            try:
                cursor.execute(f"PRAGMA rekey = \"x'{hex_new_key}'\";")
                self._current_key_bytes = bytes(new_key_bytes)
            except Exception as e:
                raise DatabaseError(f"Database re-keying failed: {e}") from e

    def close(self) -> None:
        """Safely closes the database connection and clears sensitive in-memory references."""
        with self._lock:
            if self._conn is not None:
                with suppress(Exception):
                    self._conn.close()
                self._conn = None
            self._current_key_bytes = None

    @contextmanager
    def transaction(self):
        """Context manager for thread-safe database transaction execution."""
        with self._lock:
            if not self._conn:
                raise DatabaseError("Database is not connected.")
            cursor = self._conn.cursor()
            try:
                cursor.execute("BEGIN IMMEDIATE;")
                yield cursor
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def cursor(self):
        """Returns a cursor from the active connection."""
        with self._lock:
            if not self._conn:
                raise DatabaseError("Database is not connected.")
            return self._conn.cursor()
