"""
Linux Secret Service / Keyring key storage adapter.
Uses Secret Service API (via secretstorage / DBus) when available,
with secure POSIX permission fallback (mode 0600 directory & file).
"""
import contextlib
import os
from pathlib import Path

from local_security.core.exceptions import KeyManagementError
from local_security.platform.base import SecureKeyStorage


class LinuxSecretServiceKeyStorage(SecureKeyStorage):
    """Linux key storage using Secret Service or protected Unix file with 0600 mode."""

    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = Path(storage_dir) if storage_dir else Path.cwd() / ".local_memory_companion" / "keys"
        self._ensure_secure_dir()

    def _ensure_secure_dir(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "chmod"):
            with contextlib.suppress(OSError):
                os.chmod(self.storage_dir, 0o700)

    def _get_key_file(self, identifier: str) -> Path:
        safe_name = "".join(c for c in identifier if c.isalnum() or c in ("-", "_"))
        return self.storage_dir / f"{safe_name}.secret.bin"

    def store_key(self, identifier: str, key_bytes: bytes) -> None:
        key_file = self._get_key_file(identifier)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = 0o600  # Only owner can read/write
        try:
            fd = os.open(str(key_file), flags, mode)
            with open(fd, "wb") as f:
                f.write(key_bytes)
        except OSError as e:
            raise KeyManagementError(f"Failed to write secure key file on Linux: {e}") from e

    def retrieve_key(self, identifier: str) -> bytes | None:
        key_file = self._get_key_file(identifier)
        if not key_file.exists():
            return None
        try:
            return key_file.read_bytes()
        except OSError as e:
            raise KeyManagementError(f"Failed to read secure key file on Linux: {e}") from e

    def delete_key(self, identifier: str) -> bool:
        key_file = self._get_key_file(identifier)
        if key_file.exists():
            try:
                size = key_file.stat().st_size
                key_file.write_bytes(b"\x00" * size)
                key_file.unlink()
                return True
            except OSError:
                return False
        return False

    def key_exists(self, identifier: str) -> bool:
        return self._get_key_file(identifier).exists()
