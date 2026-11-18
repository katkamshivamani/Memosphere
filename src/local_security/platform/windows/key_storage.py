"""
Windows DPAPI (Data Protection API) Key Storage implementation.
Protects 256-bit database encryption keys using OS user-scoped DPAPI encryption.
"""
import ctypes
from ctypes import wintypes
from pathlib import Path

from local_security.core.exceptions import KeyManagementError
from local_security.platform.base import SecureKeyStorage


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte))
    ]


class WindowsDPAPIKeyStorage(SecureKeyStorage):
    """
    Encrypts secrets using Windows Data Protection API (DPAPI).
    The ciphertext can only be decrypted by the current Windows user login session.
    """

    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = Path(storage_dir) if storage_dir else Path.cwd() / ".local_memory_companion" / "keys"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._crypt32 = ctypes.windll.crypt32
        self._kernel32 = ctypes.windll.kernel32

    def _get_key_file(self, identifier: str) -> Path:
        # Sanitize identifier for filename
        safe_name = "".join(c for c in identifier if c.isalnum() or c in ("-", "_"))
        return self.storage_dir / f"{safe_name}.dpapi.bin"

    def _dpapi_protect(self, data: bytes, description: str = "MemoryCompanionVaultKey") -> bytes:
        data_bytes = (ctypes.c_byte * len(data))(*data)
        blob_in = DATA_BLOB(len(data), ctypes.cast(data_bytes, ctypes.POINTER(ctypes.c_byte)))
        blob_out = DATA_BLOB()

        # CRYPTPROTECT_UI_FORBIDDEN = 0x1
        success = self._crypt32.CryptProtectData(
            ctypes.byref(blob_in),
            ctypes.c_wchar_p(description),
            None,
            None,
            None,
            0x1,
            ctypes.byref(blob_out)
        )
        if not success:
            err = self._kernel32.GetLastError()
            raise KeyManagementError(f"DPAPI CryptProtectData failed with Windows error code {err}")

        try:
            return bytes(ctypes.string_at(blob_out.pbData, blob_out.cbData))
        finally:
            self._kernel32.LocalFree(blob_out.pbData)

    def _dpapi_unprotect(self, protected_data: bytes) -> bytes:
        data_bytes = (ctypes.c_byte * len(protected_data))(*protected_data)
        blob_in = DATA_BLOB(len(protected_data), ctypes.cast(data_bytes, ctypes.POINTER(ctypes.c_byte)))
        blob_out = DATA_BLOB()

        success = self._crypt32.CryptUnprotectData(
            ctypes.byref(blob_in),
            None,
            None,
            None,
            None,
            0x1,
            ctypes.byref(blob_out)
        )
        if not success:
            err = self._kernel32.GetLastError()
            raise KeyManagementError(f"DPAPI CryptUnprotectData failed with Windows error code {err}")

        try:
            return bytes(ctypes.string_at(blob_out.pbData, blob_out.cbData))
        finally:
            self._kernel32.LocalFree(blob_out.pbData)

    def store_key(self, identifier: str, key_bytes: bytes) -> None:
        if not isinstance(key_bytes, (bytes, bytearray)):
            raise ValueError("Key must be bytes.")
        protected = self._dpapi_protect(bytes(key_bytes), description=identifier)
        key_file = self._get_key_file(identifier)
        # Atomic write
        temp_file = key_file.with_suffix(".tmp")
        temp_file.write_bytes(protected)
        temp_file.replace(key_file)

    def retrieve_key(self, identifier: str) -> bytes | None:
        key_file = self._get_key_file(identifier)
        if not key_file.exists():
            return None
        protected = key_file.read_bytes()
        return self._dpapi_unprotect(protected)

    def delete_key(self, identifier: str) -> bool:
        key_file = self._get_key_file(identifier)
        if key_file.exists():
            try:
                # Overwrite before deleting
                size = key_file.stat().st_size
                key_file.write_bytes(b"\x00" * size)
                key_file.unlink()
                return True
            except OSError:
                return False
        return False

    def key_exists(self, identifier: str) -> bool:
        return self._get_key_file(identifier).exists()
