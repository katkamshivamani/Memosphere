"""
Abstract base classes defining cross-platform platform adapters.
"""
from abc import ABC, abstractmethod
from enum import StrEnum


class BiometricAvailability(StrEnum):
    AVAILABLE = "available"
    NOT_CONFIGURED = "not_configured"
    DEVICE_NOT_PRESENT = "device_not_present"
    DISABLED_BY_POLICY = "disabled_by_policy"
    DEVICE_BUSY = "device_busy"
    UNSUPPORTED_PLATFORM = "unsupported_platform"
    UNKNOWN_ERROR = "unknown_error"


class BiometricVerificationStatus(StrEnum):
    VERIFIED = "verified"
    CANCELED = "canceled"
    FAILED = "failed"
    RETRIES_EXHAUSTED = "retries_exhausted"
    DEVICE_BUSY = "device_busy"
    HARDWARE_UNAVAILABLE = "hardware_unavailable"


class BiometricProvider(ABC):
    """Abstract interface for OS biometric authentication."""

    @abstractmethod
    def check_availability(self) -> BiometricAvailability:
        """Determines whether biometric authentication hardware and configuration are available."""
        pass

    @abstractmethod
    def verify_user(self, prompt_message: str) -> tuple[BiometricVerificationStatus, str | None]:
        """
        Prompts user for biometric verification (fingerprint / face / user consent).
        Returns status and optional diagnostic message.
        """
        pass


class SecureKeyStorage(ABC):
    """Abstract interface for protecting encryption keys using OS secure storage."""

    @abstractmethod
    def store_key(self, identifier: str, key_bytes: bytes) -> None:
        """Securely encrypts and stores the key material."""
        pass

    @abstractmethod
    def retrieve_key(self, identifier: str) -> bytes | None:
        """Retrieves and decrypts the key material from OS storage."""
        pass

    @abstractmethod
    def delete_key(self, identifier: str) -> bool:
        """Securely removes stored key material."""
        pass

    @abstractmethod
    def key_exists(self, identifier: str) -> bool:
        """Checks if key exists in storage."""
        pass


class PlatformInfoProvider(ABC):
    """Provides platform identity and capabilities."""

    @abstractmethod
    def get_os_name(self) -> str:
        pass

    @abstractmethod
    def is_biometrics_supported(self) -> bool:
        pass

    @abstractmethod
    def get_secure_storage_backend_name(self) -> str:
        pass
