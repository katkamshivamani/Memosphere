"""
Linux Biometric Provider interfacing with fprintd / PAM facilities.
Detects fprintd service on DBus and delegates verification without storing biometric templates.
"""
import shutil
import subprocess

from local_security.platform.base import (
    BiometricAvailability,
    BiometricProvider,
    BiometricVerificationStatus,
)


class LinuxFprintdBiometricProvider(BiometricProvider):
    """
    Linux fprintd biometric adapter.
    Uses 'fprintd-verify' CLI or DBus interface where available on Linux Mint / Ubuntu.
    """

    def check_availability(self) -> BiometricAvailability:
        fprintd_verify = shutil.which("fprintd-verify")
        if not fprintd_verify:
            return BiometricAvailability.DEVICE_NOT_PRESENT

        try:
            # Query fprintd-list
            res = subprocess.run(
                ["fprintd-list", "$USER"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "No devices available" in res.stderr or "No devices available" in res.stdout:
                return BiometricAvailability.DEVICE_NOT_PRESENT
            if "has no fingers enrolled" in res.stdout or "has no fingers enrolled" in res.stderr:
                return BiometricAvailability.NOT_CONFIGURED
            return BiometricAvailability.AVAILABLE
        except Exception:
            return BiometricAvailability.DEVICE_NOT_PRESENT

    def verify_user(self, prompt_message: str) -> tuple[BiometricVerificationStatus, str | None]:
        fprintd_verify = shutil.which("fprintd-verify")
        if not fprintd_verify:
            return (
                BiometricVerificationStatus.HARDWARE_UNAVAILABLE,
                "fprintd is not installed or available on this system",
            )

        try:
            res = subprocess.run(
                ["fprintd-verify"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = res.stdout + res.stderr
            if "verify-match" in output:
                return BiometricVerificationStatus.VERIFIED, "Fingerprint verification matched"
            elif "verify-no-match" in output:
                return BiometricVerificationStatus.FAILED, "Fingerprint did not match"
            elif "verify-unknown-error" in output:
                return BiometricVerificationStatus.FAILED, "Unknown error during verification"
            else:
                return BiometricVerificationStatus.FAILED, output.strip()
        except subprocess.TimeoutExpired:
            return BiometricVerificationStatus.CANCELED, "Fingerprint verification timed out"
        except Exception as e:
            return BiometricVerificationStatus.FAILED, str(e)
