"""
Configuration models and defaults for the Local Privacy & Security Module.
"""
from pathlib import Path

from pydantic import BaseModel, Field


class Argon2Config(BaseModel):
    """Argon2id hashing configuration according to OWASP guidelines."""
    time_cost: int = Field(default=3, description="Number of iterations")
    memory_cost: int = Field(default=65536, description="Memory size in KiB (64 MiB)")
    parallelism: int = Field(default=4, description="Number of parallel threads")
    hash_len: int = Field(default=32, description="Length of the hash in bytes")
    salt_len: int = Field(default=16, description="Length of random salt in bytes")


class LockConfig(BaseModel):
    """Application auto-lock and session inactivity configuration."""
    inactivity_timeout_seconds: int = Field(default=300, description="Auto-lock after 5 min inactivity")
    lock_on_minimize: bool = Field(default=False, description="Lock when application is minimized")
    lock_on_focus_loss: bool = Field(default=False, description="Lock when application loses window focus")
    lock_on_restart: bool = Field(default=True, description="Always require auth on app startup")
    max_failed_attempts: int = Field(default=5, description="Consecutive failed PIN attempts before backoff")
    base_backoff_seconds: float = Field(default=2.0, description="Base exponential backoff in seconds")
    max_backoff_seconds: float = Field(default=60.0, description="Maximum backoff delay")


class SecurityConfig(BaseModel):
    """Master security configuration."""
    app_data_dir: Path = Field(
        default_factory=lambda: Path.cwd() / ".local_memory_companion",
        description="Local application data root directory"
    )
    database_filename: str = Field(default="memory_vault.enc.db", description="Database file name")
    key_identifier: str = Field(default="LocalMemoryCompanionVaultKey", description="Key identifier in OS storage")
    argon2: Argon2Config = Field(default_factory=Argon2Config)
    lock: LockConfig = Field(default_factory=LockConfig)
    enable_biometrics: bool = Field(default=True, description="Attempt biometric authentication if available")
    enforce_fts5: bool = Field(default=True, description="Enable FTS5 full text search indexes")

    @property
    def database_path(self) -> Path:
        return self.app_data_dir / self.database_filename

    @property
    def keystore_path(self) -> Path:
        return self.app_data_dir / "keys"

    def ensure_directories(self) -> None:
        """Create necessary directories with restrictive permissions."""
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.keystore_path.mkdir(parents=True, exist_ok=True)
