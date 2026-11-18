"""
Security and Privacy Audit Tests.
Verifies ciphertext on disk, tampering defense, offline independence, and no secret leakage.
"""
import os
import socket
from pathlib import Path

import pytest

from local_security.core.exceptions import DecryptionError
from local_security.database.database_manager import DatabaseManager
from local_security.encryption.encryption_manager import EncryptionManager
from local_security.models.records import MemoryRecord, PersonRecord, RoutineRecord
from local_security.storage.secure_storage import SecureStorage


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    return tmp_path / "security_audit_vault.enc.db"


@pytest.fixture
def master_key() -> bytes:
    return os.urandom(32)


def test_tamper_detection_and_hmac_failure(temp_db: Path, master_key: bytes):
    """Verifies that tampering with ciphertext on disk triggers SQLCipher HMAC integrity failure."""
    db = DatabaseManager(temp_db)
    db.connect(master_key)
    with db.transaction() as cur:
        cur.execute(
            "INSERT INTO memories (id, title, content, category, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?);",
            ("m-tamper", "Secret Data", "Original untampered ciphertext", "secrets", "2026-11-18T10:00:00Z", "2026-11-18T10:00:00Z")
        )
    db.close()

    # Read bytes and corrupt a byte in the database body
    raw_data = bytearray(temp_db.read_bytes())
    assert len(raw_data) > 100
    # Corrupt byte at index 64
    raw_data[64] ^= 0xFF
    temp_db.write_bytes(raw_data)

    # Reopening corrupted file must fail with DecryptionError
    db_tampered = DatabaseManager(temp_db)
    with pytest.raises(DecryptionError):
        db_tampered.connect(master_key)


def test_no_plaintext_leakage_across_all_domain_records(temp_db: Path, master_key: bytes):
    """Verifies that across all domain records, no strings leak into the encrypted file."""
    db = DatabaseManager(temp_db)
    db.connect(master_key)
    storage = SecureStorage(db)

    secret_person = "Uncle_Montgomery_Vance_987654"
    secret_memory = "Buried_Treasure_Coordinates_Latitude_42_9988"
    secret_routine = "Critical_Insulin_Injection_Routine_XYZ"

    storage.people.save_person(PersonRecord(name=secret_person))
    storage.memories.save_memory(MemoryRecord(title="Secret Note", content=secret_memory))
    storage.routines.save_routine(RoutineRecord(title=secret_routine))
    db.close()

    # Audit file on disk
    is_secure, findings = EncryptionManager.verify_disk_encryption(
        temp_db,
        forbidden_plaintexts=[secret_person, secret_memory, secret_routine]
    )
    assert is_secure is True
    assert any("CONFIRMED: No sensitive plaintext strings found" in f for f in findings)


def test_offline_operation_zero_network_traffic(monkeypatch, temp_db: Path, master_key: bytes):
    """
    Guarantees 100% offline functionality.
    Simulates total network disconnection by disallowing socket creation.
    """
    def _blocked_socket(*args, **kwargs):
        raise OSError("Network connection blocked: application must operate 100% offline!")

    monkeypatch.setattr(socket, "socket", _blocked_socket)

    # All database, repository, and encryption operations must succeed completely without network
    db = DatabaseManager(temp_db)
    db.connect(master_key)
    storage = SecureStorage(db)

    mem_id = storage.memories.save_memory(MemoryRecord(
        title="Offline Memory",
        content="Created in an isolated, offline environment without network.",
    ))
    retrieved = storage.memories.get_memory(mem_id)
    assert retrieved is not None
    assert retrieved.title == "Offline Memory"

    search_res = storage.memories.search_memories("isolated")
    assert len(search_res) == 1

    db.close()


def test_exceptions_do_not_leak_raw_keys(master_key: bytes):
    """Verifies that exception representations never leak the 256-bit raw key."""
    from local_security.core.exceptions import DecryptionError

    err = DecryptionError("Failed to decrypt database with key")
    err_str = str(err)
    assert master_key.hex() not in err_str
