"""Secure API-key storage.

Windows uses DPAPI (``CryptProtectData``) through ``ctypes`` - no extra wheel is
required and the ciphertext is bound to the current Windows user.  Keys live in
their own file, separate from the personal memory database.

Honesty rules implemented here:

* if secure storage cannot be used, the app raises
  :class:`CredentialStoreUnavailableError` instead of writing plaintext;
* keys are never logged, returned to the UI, or written to settings;
* :meth:`ApiKeyManager.masked_key` only ever reveals the last four characters.
"""

from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import platform
import sys
import tempfile
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from memory_agent.core.exceptions import (
    CredentialStoreUnavailableError,
    InvalidRequestError,
    MissingApiKeyError,
    ProviderError,
)
from memory_agent.providers.registry import create_provider, get_provider_info
from memory_agent.providers.schemas import ConnectionTestResult

logger = logging.getLogger("memory_agent.security.credentials")

_ENTROPY = b"MemoryCompanion::agent-api-keys::v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1
_KEY_NAME_TEMPLATE = "provider:{provider_id}:api_key"


class CredentialStore(ABC):
    """Minimal secret store interface (set/get/delete by logical name)."""

    @property
    @abstractmethod
    def is_available(self) -> bool: ...

    @property
    @abstractmethod
    def unavailable_reason(self) -> str: ...

    @abstractmethod
    def set_secret(self, name: str, secret: str) -> None: ...

    @abstractmethod
    def get_secret(self, name: str) -> Optional[str]: ...

    @abstractmethod
    def delete_secret(self, name: str) -> None: ...

    def list_names(self) -> list[str]:
        return []


# --------------------------------------------------------------------------- #
# Windows DPAPI
# --------------------------------------------------------------------------- #
class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi_available() -> bool:
    return sys.platform == "win32"


class DpapiCredentialStore(CredentialStore):
    """Per-user DPAPI-encrypted JSON container.

    Each value is individually protected, so the file is useless without the
    Windows user profile that created it.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._self_test_passed: Optional[bool] = None

    # -- platform availability ------------------------------------------- #
    @property
    def is_available(self) -> bool:
        if not _dpapi_available():
            return False
        if self._self_test_passed is None:
            self._self_test_passed = self._run_self_test()
        return bool(self._self_test_passed)

    @property
    def unavailable_reason(self) -> str:
        if not _dpapi_available():
            return "Windows DPAPI is only available on Windows."
        return "Windows DPAPI self-test failed; secure storage cannot be verified."

    def _run_self_test(self) -> bool:
        try:
            probe = "self-test-" + os.urandom(8).hex()
            sealed = self._protect(probe.encode("utf-8"))
            opened = self._unprotect(sealed).decode("utf-8")
            return opened == probe
        except Exception:  # pragma: no cover - platform dependent
            return False

    # -- DPAPI primitives ------------------------------------------------ #
    @staticmethod
    def _crypt32():
        return ctypes.windll.crypt32  # type: ignore[attr-defined]

    def _protect(self, data: bytes) -> bytes:
        buffer_in = ctypes.create_string_buffer(data, len(data))
        blob_in = _DataBlob(len(data), ctypes.cast(buffer_in, ctypes.POINTER(ctypes.c_ubyte)))
        entropy_buffer = ctypes.create_string_buffer(_ENTROPY, len(_ENTROPY))
        blob_entropy = _DataBlob(
            len(_ENTROPY), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte))
        )
        blob_out = _DataBlob()
        crypt32 = self._crypt32()
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.c_wchar_p,
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(_DataBlob),
        ]
        crypt32.CryptProtectData.restype = ctypes.c_bool
        ok = crypt32.CryptProtectData(
            ctypes.byref(blob_in),
            "Memory Companion agent credential",
            ctypes.byref(blob_entropy),
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(blob_out),
        )
        if not ok:
            raise OSError(f"CryptProtectData failed (error {ctypes.GetLastError()})")
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)  # type: ignore[attr-defined]

    def _unprotect(self, sealed: bytes) -> bytes:
        buffer_in = ctypes.create_string_buffer(sealed, len(sealed))
        blob_in = _DataBlob(len(sealed), ctypes.cast(buffer_in, ctypes.POINTER(ctypes.c_ubyte)))
        entropy_buffer = ctypes.create_string_buffer(_ENTROPY, len(_ENTROPY))
        blob_entropy = _DataBlob(
            len(_ENTROPY), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte))
        )
        blob_out = _DataBlob()
        crypt32 = self._crypt32()
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.POINTER(ctypes.c_wchar_p),
            ctypes.POINTER(_DataBlob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(_DataBlob),
        ]
        crypt32.CryptUnprotectData.restype = ctypes.c_bool
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(blob_in),
            None,
            ctypes.byref(blob_entropy),
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(blob_out),
        )
        if not ok:
            raise OSError(f"CryptUnprotectData failed (error {ctypes.GetLastError()})")
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)  # type: ignore[attr-defined]

    # -- file container -------------------------------------------------- #
    def _read_container(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            return {str(k): str(v) for k, v in data.items()}
        except (OSError, ValueError):
            return {}

    def _write_container(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            try:
                os.chmod(tmp, 0o600)
            except OSError:  # pragma: no cover - Windows
                pass
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def _require_available(self) -> None:
        if not self.is_available:
            raise CredentialStoreUnavailableError(
                f"Secure credential storage is unavailable: {self.unavailable_reason}",
            )

    def set_secret(self, name: str, secret: str) -> None:
        self._require_available()
        if not name or not secret:
            raise InvalidRequestError("Secret name and value are required.")
        with self._lock:
            container = self._read_container()
            container[name] = base64.b64encode(self._protect(secret.encode("utf-8"))).decode("ascii")
            self._write_container(container)

    def get_secret(self, name: str) -> Optional[str]:
        self._require_available()
        with self._lock:
            container = self._read_container()
            sealed = container.get(name)
            if not sealed:
                return None
            try:
                return self._unprotect(base64.b64decode(sealed)).decode("utf-8")
            except Exception as exc:
                logger.warning("Stored credential could not be decrypted: %s", type(exc).__name__)
                return None

    def delete_secret(self, name: str) -> None:
        self._require_available()
        with self._lock:
            container = self._read_container()
            if name in container:
                del container[name]
                self._write_container(container)

    def list_names(self) -> list[str]:
        return sorted(self._read_container().keys())


class LinuxSecretServiceStore(CredentialStore):
    """Designed for future Linux support via the Secret Service (libsecret).

    Not implemented in this build.  It reports itself unavailable rather than
    falling back to plaintext, and the app surfaces a clear error.
    """

    @property
    def is_available(self) -> bool:
        return False

    @property
    def unavailable_reason(self) -> str:
        return (
            "Linux Secret Service storage is not implemented in this build. "
            "Add a secure backend before enabling cloud AI on Linux."
        )

    def set_secret(self, name: str, secret: str) -> None:
        raise CredentialStoreUnavailableError(self.unavailable_reason)

    def get_secret(self, name: str) -> Optional[str]:
        raise CredentialStoreUnavailableError(self.unavailable_reason)

    def delete_secret(self, name: str) -> None:
        raise CredentialStoreUnavailableError(self.unavailable_reason)


class MacKeychainStore(CredentialStore):
    """Designed for future macOS support via the Keychain. Not implemented here."""

    @property
    def is_available(self) -> bool:
        return False

    @property
    def unavailable_reason(self) -> str:
        return "macOS Keychain storage is not implemented in this build."

    def set_secret(self, name: str, secret: str) -> None:
        raise CredentialStoreUnavailableError(self.unavailable_reason)

    def get_secret(self, name: str) -> Optional[str]:
        raise CredentialStoreUnavailableError(self.unavailable_reason)

    def delete_secret(self, name: str) -> None:
        raise CredentialStoreUnavailableError(self.unavailable_reason)


class InMemoryCredentialStore(CredentialStore):
    """Process-memory store. Used only by tests, never by the desktop app."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    is_available = True
    unavailable_reason = ""

    def set_secret(self, name: str, secret: str) -> None:
        self._data[name] = secret

    def get_secret(self, name: str) -> Optional[str]:
        return self._data.get(name)

    def delete_secret(self, name: str) -> None:
        self._data.pop(name, None)

    def list_names(self) -> list[str]:
        return sorted(self._data)


def create_default_credential_store(data_dir: str | Path) -> CredentialStore:
    """Pick the platform-appropriate secure store (never plaintext)."""
    platform_name = platform.system().lower()
    path = Path(data_dir) / "credentials" / "agent_keys.json"
    if platform_name == "windows":
        return DpapiCredentialStore(path)
    if platform_name == "linux":
        return LinuxSecretServiceStore()
    if platform_name == "darwin":
        return MacKeychainStore()
    return LinuxSecretServiceStore()


# --------------------------------------------------------------------------- #
# Manager
# --------------------------------------------------------------------------- #
class ApiKeyManager:
    """High-level key lifecycle used by the settings UI.

    Keys are held only transiently for validation calls.  The manager never
    returns a full key to the caller and never logs one.
    """

    def __init__(self, store: CredentialStore) -> None:
        self._store = store

    @property
    def store_available(self) -> bool:
        return self._store.is_available

    @property
    def store_status(self) -> str:
        if self._store.is_available:
            return "Secure credential storage available (Windows DPAPI)."
        return self._store.unavailable_reason

    @staticmethod
    def _name(provider_id: str) -> str:
        get_provider_info(provider_id)  # validates the provider id
        return _KEY_NAME_TEMPLATE.format(provider_id=provider_id)

    def has_key(self, provider_id: str) -> bool:
        if not self._store.is_available:
            return False
        try:
            return bool(self._store.get_secret(self._name(provider_id)))
        except CredentialStoreUnavailableError:
            return False

    def get_key(self, provider_id: str) -> Optional[str]:
        """Return the key for a provider call. Callers must never display it."""
        return self._store.get_secret(self._name(provider_id))

    def require_key(self, provider_id: str) -> str:
        key = self.get_key(provider_id)
        if not key:
            raise MissingApiKeyError(
                f"No API key stored for provider {provider_id}.",
            )
        return key

    def masked_key(self, provider_id: str) -> Optional[str]:
        try:
            key = self.get_key(provider_id)
        except CredentialStoreUnavailableError:
            return None
        if not key:
            return None
        suffix = key[-4:] if len(key) >= 8 else ""
        return f"••••••••{suffix}"

    def store_key(self, provider_id: str, api_key: str) -> None:
        key = (api_key or "").strip()
        if len(key) < 8:
            raise InvalidRequestError(
                "That API key looks too short.",
                user_message="That API key looks too short. Check that you copied all of it.",
            )
        if any(char.isspace() for char in key):
            raise InvalidRequestError(
                "API keys must not contain whitespace.",
                user_message="The API key contains spaces or line breaks. Paste it again.",
            )
        self._store.set_secret(self._name(provider_id), key)
        logger.info("Stored API key for provider=%s", provider_id)

    def delete_key(self, provider_id: str) -> None:
        self._store.delete_secret(self._name(provider_id))
        logger.info("Deleted API key for provider=%s", provider_id)

    def test_connection(
        self,
        provider_id: str,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_s: float = 20.0,
    ) -> ConnectionTestResult:
        """Test a key before the user enables the agent.

        If ``api_key`` is supplied it is validated directly and *not* stored;
        otherwise the stored key is used.
        """
        key = api_key if api_key is not None else self.get_key(provider_id)
        info = get_provider_info(provider_id)

        if info.is_local:
            provider = create_provider(
                provider_id, api_key=None, model=model, base_url=base_url, timeout_s=timeout_s
            )
            return provider.validate_api_key()

        if not key:
            return ConnectionTestResult(
                ok=False,
                provider_id=provider_id,
                model=model,
                message="No API key is configured for this provider.",
            )
        try:
            provider = create_provider(
                provider_id, api_key=key, model=model, base_url=base_url, timeout_s=timeout_s
            )
            result = provider.validate_api_key()
        except ProviderError as exc:
            return ConnectionTestResult(
                ok=False,
                provider_id=provider_id,
                model=model,
                message=exc.user_message,
            )
        finally:
            # Drop the transient key copy as soon as the check finishes.
            del key
        return result

    def provider_status(self) -> list[dict[str, object]]:
        from memory_agent.providers.registry import list_provider_info

        statuses = []
        for info in list_provider_info():
            statuses.append(
                {
                    "provider_id": info.id,
                    "label": info.label,
                    "is_local": info.is_local,
                    "requires_api_key": info.requires_api_key,
                    "has_key": self.has_key(info.id) if info.requires_api_key else True,
                    "masked_key": self.masked_key(info.id) if info.requires_api_key else None,
                    "store_available": self._store.is_available,
                }
            )
        return statuses

    def __repr__(self) -> str:  # never include secrets
        return f"<ApiKeyManager store_available={self.store_available}>"
