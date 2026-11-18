"""
macOS Keychain Key Storage implementation.
Integrates with the macOS Keychain via the system 'security' command-line interface.
"""
import subprocess

from local_security.core.exceptions import KeyManagementError
from local_security.platform.base import SecureKeyStorage


class MacOSKeychainKeyStorage(SecureKeyStorage):
    """Stores encryption keys in the macOS user Keychain."""

    def __init__(self, service_name: str = "LocalMemoryCompanion"):
        self.service_name = service_name

    def store_key(self, identifier: str, key_bytes: bytes) -> None:
        hex_data = key_bytes.hex()
        # Delete existing entry if present
        self.delete_key(identifier)
        cmd = [
            "security", "add-generic-password",
            "-a", identifier,
            "-s", self.service_name,
            "-w", hex_data,
            "-U"
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            raise KeyManagementError(f"Failed to store key in macOS Keychain: {e.stderr}") from e

    def retrieve_key(self, identifier: str) -> bytes | None:
        cmd = [
            "security", "find-generic-password",
            "-a", identifier,
            "-s", self.service_name,
            "-w"
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                return None
            hex_data = res.stdout.strip()
            return bytes.fromhex(hex_data)
        except Exception as e:
            raise KeyManagementError(f"Failed to retrieve key from macOS Keychain: {e}") from e

    def delete_key(self, identifier: str) -> bool:
        cmd = [
            "security", "delete-generic-password",
            "-a", identifier,
            "-s", self.service_name
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        return res.returncode == 0

    def key_exists(self, identifier: str) -> bool:
        return self.retrieve_key(identifier) is not None
