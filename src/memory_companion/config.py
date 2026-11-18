"""Host application paths and non-sensitive settings."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


APP_NAME = "MemoryCompanion"


def default_data_dir() -> Path:
    """Per-user data directory. Environment override is used by tests."""
    override = os.environ.get("MEMORY_COMPANION_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path

    @classmethod
    def default(cls) -> "AppPaths":
        return cls(data_dir=default_data_dir())

    @property
    def database_path(self) -> Path:
        return self.data_dir / "memory.db"

    @property
    def credentials_dir(self) -> Path:
        return self.data_dir / "credentials"

    @property
    def agent_settings_path(self) -> Path:
        return self.data_dir / "agent_settings.json"

    @property
    def consent_path(self) -> Path:
        return self.data_dir / "agent_consent.json"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def app_settings_path(self) -> Path:
        return self.data_dir / "settings.json"

    def ensure(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.credentials_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


class AppSettings:
    """Small non-sensitive preferences (UI state, last user, etc.)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, Any] = {}
        self.load()

    def load(self) -> dict[str, Any]:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data = raw
            except (OSError, ValueError):
                self._data = {}
        return dict(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, indent=2)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
