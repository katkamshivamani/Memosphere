"""
Key Manager for cryptographic key lifecycle, OS-backed storage, rotation, and encrypted backup.
"""
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from local_security.core.exceptions import KeyManagementError, KeyNotFoundError
from local_security.database.database_manager import DatabaseManager
from local_security.platform.base import SecureKeyStorage
from local_security.platform.factory import PlatformFactory


class KeyManager:
    """
    Manages the lifecycle of the 256-bit SQLCipher database master encryption key.
    Ensures keys are never hardcoded, never committed, and protected by OS secure key storage.
    """

    KEY_SIZE_BYTES = 32  # 256 bits

    def __init__(self, key_storage: SecureKeyStorage | None = None):
        self._storage = key_storage if key_storage is not None else PlatformFactory.get_key_storage()

    def generate_key(self) -> bytes:
        """Generates a cryptographically secure 256-bit random key using CSPRNG."""
        return secrets.token_bytes(self.KEY_SIZE_BYTES)

    def get_or_create_vault_key(self, identifier: str) -> tuple[bytes, bool]:
        """
        Retrieves existing vault encryption key from OS secure storage,
        or generates and stores a new one if it does not yet exist.
        Returns: (key_bytes, was_created_new)
        """
        existing_key = self._storage.retrieve_key(identifier)
        if existing_key is not None:
            if len(existing_key) != self.KEY_SIZE_BYTES:
                raise KeyManagementError(
                    f"Retrieved key for '{identifier}' has invalid size: {len(existing_key)} bytes."
                )
            return existing_key, False

        new_key = self.generate_key()
        self._storage.store_key(identifier, new_key)
        return new_key, True

    def retrieve_vault_key(self, identifier: str) -> bytes:
        """Retrieves the vault encryption key from OS storage or raises KeyNotFoundError."""
        key = self._storage.retrieve_key(identifier)
        if key is None:
            raise KeyNotFoundError(f"Encryption key '{identifier}' not found in secure storage.")
        return key

    def rotate_vault_key(self, identifier: str, db_manager: DatabaseManager) -> bytes:
        """
        Rotates the vault key:
        1. Generates a new 256-bit key.
        2. Re-encrypts the SQLCipher database pages via PRAGMA rekey.
        3. Updates OS secure storage with the new key.
        Returns the new key.
        """
        if not db_manager.is_connected:
            raise KeyManagementError("Cannot rotate key while database is closed.")

        new_key = self.generate_key()
        # Rekey database first (if this fails, old key remains valid)
        db_manager.rekey(new_key)

        # Update secure key storage
        self._storage.store_key(identifier, new_key)
        return new_key

    def export_recovery_package(self, vault_key: bytes, recovery_passphrase: str) -> bytes:
        """
        Encrypts the master vault key using AES-256-GCM derived from a recovery passphrase
        via Argon2id. Produces a portable, encrypted recovery blob.
        Format: [16 bytes salt] + [12 bytes nonce] + [ciphertext + tag]
        """
        if len(recovery_passphrase) < 8:
            raise ValueError("Recovery passphrase must be at least 8 characters long.")

        salt = os.urandom(16)
        kdf = Argon2id(
            salt=salt,
            length=32,
            iterations=3,
            lanes=4,
            memory_cost=65536,
        )
        derived_key = kdf.derive(recovery_passphrase.encode("utf-8"))

        aesgcm = AESGCM(derived_key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, vault_key, b"MEMORY_COMPANION_RECOVERY_V1")

        return salt + nonce + ciphertext

    def import_recovery_package(self, recovery_blob: bytes, recovery_passphrase: str) -> bytes:
        """
        Decrypts the master vault key from an exported recovery package using the passphrase.
        """
        if len(recovery_blob) < 16 + 12 + 16:
            raise KeyManagementError("Invalid recovery package: payload too short.")

        salt = recovery_blob[:16]
        nonce = recovery_blob[16:28]
        ciphertext = recovery_blob[28:]

        kdf = Argon2id(
            salt=salt,
            length=32,
            iterations=3,
            lanes=4,
            memory_cost=65536,
        )
        derived_key = kdf.derive(recovery_passphrase.encode("utf-8"))

        aesgcm = AESGCM(derived_key)
        try:
            vault_key = aesgcm.decrypt(nonce, ciphertext, b"MEMORY_COMPANION_RECOVERY_V1")
            if len(vault_key) != self.KEY_SIZE_BYTES:
                raise KeyManagementError("Decrypted key has invalid length.")
            return vault_key
        except Exception as e:
            raise KeyManagementError("Failed to decrypt recovery package: incorrect passphrase or corrupted data.") from e
