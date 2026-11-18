"""
Core exceptions hierarchy for Local Privacy & Security Module.
"""

class SecurityError(Exception):
    """Base exception for all security and privacy module errors."""
    pass


class ConfigurationError(SecurityError):
    """Raised when there is an invalid or missing security configuration."""
    pass


class AuthenticationError(SecurityError):
    """Base exception for authentication failures."""
    pass


class InvalidCredentialsError(AuthenticationError):
    """Raised when PIN or biometric authentication credentials are invalid."""
    pass


class PINLockedError(AuthenticationError):
    """Raised when PIN attempts are temporarily or permanently locked due to rate-limiting."""
    def __init__(self, message: str, retry_after_seconds: float = 0.0):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class HardwareUnavailableError(AuthenticationError):
    """Raised when requested biometric hardware or OS service is unavailable."""
    pass


class BiometricVerificationFailedError(AuthenticationError):
    """Raised when biometric verification fails or is canceled by user."""
    pass


class KeyManagementError(SecurityError):
    """Base exception for cryptographic key generation, retrieval, or rotation errors."""
    pass


class KeyNotFoundError(KeyManagementError):
    """Raised when the requested encryption key cannot be found in secure storage."""
    pass


class DatabaseError(SecurityError):
    """Base exception for database errors."""
    pass


class DecryptionError(DatabaseError):
    """Raised when database decryption fails (e.g. invalid key or corrupted ciphertext)."""
    pass


class SchemaMigrationError(DatabaseError):
    """Raised when a schema migration fails to apply or roll back."""
    pass


class RecordNotFoundError(DatabaseError):
    """Raised when a requested database record does not exist."""
    pass


class SessionError(SecurityError):
    """Base exception for session management errors."""
    pass


class SessionExpiredError(SessionError):
    """Raised when an operation is attempted on an expired session."""
    pass


class ApplicationLockedError(SecurityError):
    """Raised when an operation is attempted while the application is locked."""
    pass


class PermissionDeniedError(SecurityError):
    """Raised when an operation is denied by the access control policy."""
    def __init__(self, module: str, action: str, reason: str = "Access denied"):
        super().__init__(f"Permission denied for module '{module}', action '{action}': {reason}")
        self.module = module
        self.action = action
        self.reason = reason
