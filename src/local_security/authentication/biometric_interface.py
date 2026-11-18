"""
Biometric authentication interface orchestrating OS biometric providers and fallback logic.
"""

from local_security.core.exceptions import (
    BiometricVerificationFailedError,
    HardwareUnavailableError,
)
from local_security.platform.base import (
    BiometricAvailability,
    BiometricProvider,
    BiometricVerificationStatus,
)
from local_security.platform.factory import PlatformFactory


class BiometricAuthenticator:
    """
    Coordinates biometric authentication with the active OS platform provider.
    Provides honest status reporting and seamless PIN fallback.
    """

    def __init__(self, provider: BiometricProvider | None = None):
        self._provider = provider if provider is not None else PlatformFactory.get_biometric_provider()

    def is_biometric_available(self) -> tuple[bool, BiometricAvailability, str]:
        """
        Inspects hardware and OS configuration.
        Returns: (is_available, availability_code, human_readable_description)
        """
        status = self._provider.check_availability()
        descriptions = {
            BiometricAvailability.AVAILABLE: "Biometric hardware is configured and available.",
            BiometricAvailability.NOT_CONFIGURED: "Biometric hardware is present but no credentials/fingerprints are enrolled.",
            BiometricAvailability.DEVICE_NOT_PRESENT: "No biometric sensor hardware detected on this device.",
            BiometricAvailability.DISABLED_BY_POLICY: "Biometrics are disabled by operating system or group policy.",
            BiometricAvailability.DEVICE_BUSY: "Biometric hardware is currently busy or reserved by another process.",
            BiometricAvailability.UNSUPPORTED_PLATFORM: "Biometrics are not supported on this platform.",
            BiometricAvailability.UNKNOWN_ERROR: "Biometric subsystem reported an unexpected status.",
        }
        return (status == BiometricAvailability.AVAILABLE, status, descriptions.get(status, "Unknown status"))

    def authenticate_biometric(self, prompt_message: str = "Authenticate to unlock your Personal Memory Companion") -> bool:
        """
        Requests user verification through the OS biometric facility.
        Returns True on verification success.
        Raises HardwareUnavailableError if hardware is missing/unconfigured.
        Raises BiometricVerificationFailedError on cancellation or verification failure.
        """
        available, code, desc = self.is_biometric_available()
        if not available:
            raise HardwareUnavailableError(f"Biometric authentication unavailable: {desc} ({code.value})")

        status, message = self._provider.verify_user(prompt_message)
        if status == BiometricVerificationStatus.VERIFIED:
            return True
        elif status == BiometricVerificationStatus.CANCELED:
            raise BiometricVerificationFailedError(f"Biometric verification canceled by user: {message}")
        elif status == BiometricVerificationStatus.RETRIES_EXHAUSTED:
            raise BiometricVerificationFailedError(f"Biometric retries exhausted. Please use PIN: {message}")
        elif status == BiometricVerificationStatus.HARDWARE_UNAVAILABLE:
            raise HardwareUnavailableError(f"Biometric hardware error during verification: {message}")
        else:
            raise BiometricVerificationFailedError(f"Biometric verification failed: {message}")
