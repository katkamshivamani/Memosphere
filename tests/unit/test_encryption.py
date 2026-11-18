"""
Unit tests for KeyManager, platform secure key storage, recovery package, and disk encryption auditing.
"""
import os
from pathlib import Path

import pytest

from local_security.core.exceptions import KeyManagementError
from local_security.database.database_manager import DatabaseManager
from local_security.encryption.encryption_manager import EncryptionManager
from local_security.encryption.key_manager import KeyManager
from local_security.platform.factory import PlatformFactory


@pytest.fixture
def temp_keys_dir(tmp_path: Path) -> Path:
    return tmp_path / "keys"


@pytest.fixture
def temp_db_file(tmp_path: Path) -> Path:
    return tmp_path / "encrypted_vault.db"


def test_key_generation():
    km = KeyManager()
    key1 = km.generate_key()
    key2 = km.generate_key()
    assert len(key1) == 32
    assert len(key2) == 32
    assert key1 != key2


def test_platform_key_storage_roundtrip(temp_keys_dir: Path):
    storage = PlatformFactory.get_key_storage(str(temp_keys_dir))
    identifier = "TestVaultKeyIdentifier"

    secret_key = os.urandom(32)
    storage.store_key(identifier, secret_key)
    assert storage.key_exists(identifier)

    retrieved = storage.retrieve_key(identifier)
    assert retrieved == secret_key

    # Delete key
    assert storage.delete_key(identifier)
    assert not storage.key_exists(identifier)
    assert storage.retrieve_key(identifier) is None


def test_get_or_create_vault_key(temp_keys_dir: Path):
    storage = PlatformFactory.get_key_storage(str(temp_keys_dir))
    km = KeyManager(storage)
    identifier = "UniqueKeyId_123"

    key, created_new = km.get_or_create_vault_key(identifier)
    assert created_new is True
    assert len(key) == 32

    key2, created_new2 = km.get_or_create_vault_key(identifier)
    assert created_new2 is False
    assert key == key2


def test_recovery_package_export_and_import():
    km = KeyManager()
    vault_key = os.urandom(32)
    passphrase = "CorrectHorseBatteryStaple2026!"

    package = km.export_recovery_package(vault_key, passphrase)
    assert isinstance(package, bytes)
    assert len(package) > 32

    # Restoring with correct passphrase
    restored_key = km.import_recovery_package(package, passphrase)
    assert restored_key == vault_key

    # Restoring with wrong passphrase fails
    with pytest.raises(KeyManagementError):
        km.import_recovery_package(package, "WrongPassword123!")


def test_key_rotation_with_database(temp_db_file: Path, temp_keys_dir: Path):
    storage = PlatformFactory.get_key_storage(str(temp_keys_dir))
    km = KeyManager(storage)
    key_id = "RotationTestKey"

    key1, _ = km.get_or_create_vault_key(key_id)
    db = DatabaseManager(temp_db_file)
    db.connect(key1)

    with db.transaction() as cur:
        cur.execute(
            "INSERT INTO memories (id, title, content, category, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?);",
            ("m-rot", "Before Rotation", "Important Memory", "general", "2026-11-18T10:00:00Z", "2026-11-18T10:00:00Z")
        )

    # Perform key rotation
    key2 = km.rotate_vault_key(key_id, db)
    assert key2 != key1
    db.close()

    # Reopen using storage's updated key
    retrieved_key = storage.retrieve_key(key_id)
    assert retrieved_key == key2

    db_new = DatabaseManager(temp_db_file)
    db_new.connect(retrieved_key)
    cur = db_new.cursor()
    cur.execute("SELECT title FROM memories WHERE id = ?;", ("m-rot",))
    assert cur.fetchone()["title"] == "Before Rotation"
    db_new.close()


def test_encryption_manager_disk_verification(temp_db_file: Path):
    key = os.urandom(32)
    secret_text = "SECRET_STRING_SHOULD_BE_ENCRYPTED_AND_NOT_IN_PLAINTEXT"

    db = DatabaseManager(temp_db_file)
    db.connect(key)
    with db.transaction() as cur:
        cur.execute(
            "INSERT INTO memories (id, title, content, category, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?);",
            ("m-audit", "Sensitive Title", secret_text, "secrets", "2026-11-18T10:00:00Z", "2026-11-18T10:00:00Z")
        )
    db.close()

    is_secure, findings = EncryptionManager.verify_disk_encryption(
        temp_db_file,
        forbidden_plaintexts=[secret_text, "Sensitive Title"]
    )
    assert is_secure is True
    assert any("No sensitive plaintext strings found" in f for f in findings)
    assert any("Plaintext SQLite magic header is absent" in f for f in findings)
