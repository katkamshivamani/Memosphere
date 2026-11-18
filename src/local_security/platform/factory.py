"""
Cross-platform factory and dependency injection registry for platform adapters.
"""
import sys

from local_security.platform.base import (
    BiometricAvailability,
    BiometricProvider,
    BiometricVerificationStatus,
    PlatformInfoProvider,
    SecureKeyStorage,
)


class GenericPlatformInfo(PlatformInfoProvider):
    def __init__(self, os_name: str, biometric_supported: bool, backend_name: str):
        self._os_name = os_name
        self._biometric_supported = biometric_supported
        self._backend_name = backend_name

    def get_os_name(self) -> str:
        return self._os_name

    def is_biometrics_supported(self) -> bool:
        return self._biometric_supported

    def get_secure_storage_backend_name(self) -> str:
        return self._backend_name


class NullBiometricProvider(BiometricProvider):
    """Fallback provider when platform or hardware does not support biometrics."""
    def check_availability(self) -> BiometricAvailability:
        return BiometricAvailability.UNSUPPORTED_PLATFORM

    def verify_user(self, prompt_message: str):
        return (
            BiometricVerificationStatus.HARDWARE_UNAVAILABLE,
            "Biometrics are not supported on this operating system or configuration."
        )


class PlatformFactory:
    """Factory selecting operating-system-specific implementations with DI overrides."""

    _biometric_override: BiometricProvider | None = None
    _key_storage_override: SecureKeyStorage | None = None

    @classmethod
    def set_biometric_provider(cls, provider: BiometricProvider | None) -> None:
        cls._biometric_override = provider

    @classmethod
    def set_key_storage(cls, storage: SecureKeyStorage | None) -> None:
        cls._key_storage_override = storage

    @classmethod
    def reset_overrides(cls) -> None:
        cls._biometric_override = None
        cls._key_storage_override = None

    @classmethod
    def get_biometric_provider(cls) -> BiometricProvider:
        if cls._biometric_override is not None:
            return cls._biometric_override

        platform = sys.platform
        if platform == "win32":
            from local_security.platform.windows.biometric import WindowsHelloBiometricProvider
            return WindowsHelloBiometricProvider()
        elif platform.startswith("linux"):
            from local_security.platform.linux.biometric import LinuxFprintdBiometricProvider
            return LinuxFprintdBiometricProvider()
        elif platform == "darwin":
            from local_security.platform.macos.biometric import MacOSTouchIDBiometricProvider
            return MacOSTouchIDBiometricProvider()
        else:
            return NullBiometricProvider()

    @classmethod
    def get_key_storage(cls, storage_dir: str | None = None) -> SecureKeyStorage:
        if cls._key_storage_override is not None:
            return cls._key_storage_override

        platform = sys.platform
        if platform == "win32":
            from local_security.platform.windows.key_storage import WindowsDPAPIKeyStorage
            return WindowsDPAPIKeyStorage(storage_dir)
        elif platform.startswith("linux"):
            from local_security.platform.linux.key_storage import LinuxSecretServiceKeyStorage
            return LinuxSecretServiceKeyStorage(storage_dir)
        elif platform == "darwin":
            from local_security.platform.macos.key_storage import MacOSKeychainKeyStorage
            return MacOSKeychainKeyStorage()
        else:
            from local_security.platform.linux.key_storage import LinuxSecretServiceKeyStorage
            return LinuxSecretServiceKeyStorage(storage_dir)

    @classmethod
    def get_platform_info(cls) -> PlatformInfoProvider:
        platform = sys.platform
        if platform == "win32":
            return GenericPlatformInfo("Windows", True, "Windows DPAPI")
        elif platform.startswith("linux"):
            return GenericPlatformInfo("Linux", True, "Linux Secret Service / Protected File")
        elif platform == "darwin":
            return GenericPlatformInfo("macOS", True, "macOS Keychain")
        else:
            return GenericPlatformInfo("Generic/Unknown", False, "Fallback")
