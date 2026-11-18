"""
Cross-Platform Adapter tests verifying Windows, Linux, and macOS abstraction layers.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from local_security.authentication.biometric_interface import BiometricAuthenticator
from local_security.core.exceptions import (
    BiometricVerificationFailedError,
    HardwareUnavailableError,
)
from local_security.platform.base import (
    BiometricAvailability,
    BiometricProvider,
    BiometricVerificationStatus,
)
from local_security.platform.factory import NullBiometricProvider, PlatformFactory
from local_security.platform.linux.biometric import LinuxFprintdBiometricProvider
from local_security.platform.linux.key_storage import LinuxSecretServiceKeyStorage
from local_security.platform.macos.biometric import MacOSTouchIDBiometricProvider


def test_platform_factory_resolution():
    PlatformFactory.reset_overrides()
    provider = PlatformFactory.get_biometric_provider()
    key_storage = PlatformFactory.get_key_storage()
    plat_info = PlatformFactory.get_platform_info()

    if sys.platform == "win32":
        from local_security.platform.windows.biometric import WindowsHelloBiometricProvider
        from local_security.platform.windows.key_storage import WindowsDPAPIKeyStorage
        assert isinstance(provider, WindowsHelloBiometricProvider)
        assert isinstance(key_storage, WindowsDPAPIKeyStorage)
        assert plat_info.get_os_name() == "Windows"


def test_dependency_injection_override():
    mock_bio = MagicMock(spec=BiometricProvider)
    mock_bio.check_availability.return_value = BiometricAvailability.AVAILABLE
    mock_bio.verify_user.return_value = (BiometricVerificationStatus.VERIFIED, "OK")

    PlatformFactory.set_biometric_provider(mock_bio)
    assert PlatformFactory.get_biometric_provider() is mock_bio

    auth = BiometricAuthenticator()
    assert auth.authenticate_biometric() is True
    mock_bio.verify_user.assert_called_once()

    PlatformFactory.reset_overrides()


def test_null_biometric_provider():
    null_p = NullBiometricProvider()
    assert null_p.check_availability() == BiometricAvailability.UNSUPPORTED_PLATFORM

    auth = BiometricAuthenticator(null_p)
    with pytest.raises(HardwareUnavailableError):
        auth.authenticate_biometric()


def test_linux_key_storage_roundtrip(tmp_path: Path):
    storage = LinuxSecretServiceKeyStorage(storage_dir=tmp_path / "linux_keys")
    ident = "LinuxKey1"
    key_data = b"L" * 32

    storage.store_key(ident, key_data)
    assert storage.key_exists(ident)
    assert storage.retrieve_key(ident) == key_data
    assert storage.delete_key(ident) is True
    assert not storage.key_exists(ident)


def test_linux_fprintd_biometric_simulated():
    provider = LinuxFprintdBiometricProvider()
    with patch("shutil.which", return_value=None):
        assert provider.check_availability() == BiometricAvailability.DEVICE_NOT_PRESENT

    with (
        patch("shutil.which", return_value="/usr/bin/fprintd-verify"),
        patch("subprocess.run") as mock_run
    ):
        mock_run.return_value.stdout = "verify-match"
        mock_run.return_value.stderr = ""
        status, msg = provider.verify_user("Verify fingerprint")
        assert status == BiometricVerificationStatus.VERIFIED


def test_macos_touch_id_biometric_simulated():
    provider = MacOSTouchIDBiometricProvider()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "AVAILABLE\n"
        assert provider.check_availability() == BiometricAvailability.AVAILABLE

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "VERIFIED:Touch ID verified\n"
        status, msg = provider.verify_user("Unlock")
        assert status == BiometricVerificationStatus.VERIFIED


def test_biometric_failure_fallback():
    mock_bio = MagicMock(spec=BiometricProvider)
    mock_bio.check_availability.return_value = BiometricAvailability.AVAILABLE
    mock_bio.verify_user.return_value = (BiometricVerificationStatus.FAILED, "No match")

    auth = BiometricAuthenticator(mock_bio)
    with pytest.raises(BiometricVerificationFailedError):
        auth.authenticate_biometric()
