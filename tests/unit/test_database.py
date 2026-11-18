"""
Unit tests for SQLCipher DatabaseManager, schema migrations, and encryption verification.
"""
import os
from pathlib import Path

import pytest

from local_security.core.exceptions import DecryptionError
from local_security.database.database_manager import DatabaseManager


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_memory_vault.enc.db"


@pytest.fixture
def master_key() -> bytes:
    return os.urandom(32)


def test_database_initialization_and_cipher_version(temp_db_path: Path, master_key: bytes):
    manager = DatabaseManager(temp_db_path)
    assert not manager.is_connected
    manager.connect(master_key)
    assert manager.is_connected

    cipher_version = manager.get_cipher_version()
    assert "community" in cipher_version.lower() or "4." in cipher_version

    # Verify tables created
    cursor = manager.cursor()
    cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='memories';")
    assert cursor.fetchone()[0] == 1

    cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='users';")
    assert cursor.fetchone()[0] == 1

    manager.close()
    assert not manager.is_connected


def test_database_crud_and_persistence(temp_db_path: Path, master_key: bytes):
    manager = DatabaseManager(temp_db_path)
    manager.connect(master_key)

    with manager.transaction() as cur:
        cur.execute(
            """
            INSERT INTO memories (id, title, content, category, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            ("mem-001", "Favorite Park Walk", "Went to Central Rose Garden with Sarah", "places", "2026-11-18T10:00:00Z", "2026-11-18T10:00:00Z")
        )

    # Read back
    cur = manager.cursor()
    cur.execute("SELECT title, content FROM memories WHERE id = ?;", ("mem-001",))
    row = cur.fetchone()
    assert row["title"] == "Favorite Park Walk"
    assert "Rose Garden" in row["content"]

    manager.close()

    # Reopen and check persistence
    manager2 = DatabaseManager(temp_db_path)
    manager2.connect(master_key)
    cur2 = manager2.cursor()
    cur2.execute("SELECT title FROM memories WHERE id = ?;", ("mem-001",))
    row2 = cur2.fetchone()
    assert row2["title"] == "Favorite Park Walk"
    manager2.close()


def test_incorrect_encryption_key_rejected(temp_db_path: Path, master_key: bytes):
    # Initialize database with master_key
    manager = DatabaseManager(temp_db_path)
    manager.connect(master_key)
    with manager.transaction() as cur:
        cur.execute(
            "INSERT INTO memories (id, title, content, category, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?);",
            ("mem-secret", "Secret Title", "Ultra confidential notes", "notes", "2026-11-18T10:00:00Z", "2026-11-18T10:00:00Z")
        )
    manager.close()

    # Attempt to open with wrong key
    wrong_key = os.urandom(32)
    bad_manager = DatabaseManager(temp_db_path)
    with pytest.raises(DecryptionError):
        bad_manager.connect(wrong_key)


def test_rekey_database(temp_db_path: Path, master_key: bytes):
    manager = DatabaseManager(temp_db_path)
    manager.connect(master_key)
    with manager.transaction() as cur:
        cur.execute(
            "INSERT INTO people (id, name, created_at, updated_at) VALUES (?, ?, ?, ?);",
            ("p-1", "Alice Smith", "2026-11-18T10:00:00Z", "2026-11-18T10:00:00Z")
        )

    new_key = os.urandom(32)
    manager.rekey(new_key)
    manager.close()

    # Old key must now fail
    manager_old = DatabaseManager(temp_db_path)
    with pytest.raises(DecryptionError):
        manager_old.connect(master_key)

    # New key must succeed
    manager_new = DatabaseManager(temp_db_path)
    manager_new.connect(new_key)
    cur = manager_new.cursor()
    cur.execute("SELECT name FROM people WHERE id = ?;", ("p-1",))
    assert cur.fetchone()["name"] == "Alice Smith"
    manager_new.close()


def test_ciphertext_on_disk_contains_no_plaintext(temp_db_path: Path, master_key: bytes):
    secret_title = "CLASSIFIED_PERSONAL_SECRET_XYZZY"
    secret_body = "The treasure map is hidden under the oak floorboard 992211"

    manager = DatabaseManager(temp_db_path)
    manager.connect(master_key)
    with manager.transaction() as cur:
        cur.execute(
            "INSERT INTO memories (id, title, content, category, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?);",
            ("m-sec", secret_title, secret_body, "secrets", "2026-11-18T10:00:00Z", "2026-11-18T10:00:00Z")
        )
    manager.close()

    # Read raw bytes from disk
    raw_disk_bytes = temp_db_path.read_bytes()

    # 1. Plaintext strings must not exist anywhere in the raw file
    assert secret_title.encode("utf-8") not in raw_disk_bytes
    assert secret_body.encode("utf-8") not in raw_disk_bytes

    # 2. First 16 bytes must not be standard unencrypted SQLite header
    # Standard SQLite header is b"SQLite format 3\x00"
    assert not raw_disk_bytes.startswith(b"SQLite format 3\x00")
