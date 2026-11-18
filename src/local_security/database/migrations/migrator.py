"""
Database schema migration engine for SQLCipher.
"""
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from local_security.core.exceptions import SchemaMigrationError
from local_security.database.schema import FTS5_DDL, INDEXES_DDL, TABLES_DDL


class Migration:
    def __init__(self, version: int, name: str, up: Callable[[Any], None]):
        self.version = version
        self.name = name
        self.up = up


def migration_v1_baseline(cursor: Any) -> None:
    """Creates baseline schema, tables, indexes and FTS5 triggers."""
    for ddl in TABLES_DDL:
        cursor.execute(ddl)
    for idx in INDEXES_DDL:
        cursor.execute(idx)
    try:
        for fts in FTS5_DDL:
            cursor.execute(fts)
    except Exception:
        # FTS5 might be unavailable in non-standard builds, continue gracefully
        pass


MIGRATIONS: list[Migration] = [
    Migration(1, "baseline_schema", migration_v1_baseline),
]


class DatabaseMigrator:
    """Manages schema versioning and sequential migrations."""

    def __init__(self, connection: Any):
        self._conn = connection

    def get_current_version(self) -> int:
        cursor = self._conn.cursor()
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations';")
            if not cursor.fetchone():
                return 0
            cursor.execute("SELECT MAX(version) FROM schema_migrations;")
            row = cursor.fetchone()
            return row[0] if (row and row[0] is not None) else 0
        except Exception as e:
            raise SchemaMigrationError(f"Failed to query migration version: {e}") from e

    def apply_all(self) -> int:
        """Applies pending migrations up to latest version."""
        cursor = self._conn.cursor()
        current_version = self.get_current_version()
        applied_count = 0

        for migration in MIGRATIONS:
            if migration.version > current_version:
                try:
                    cursor.execute("BEGIN IMMEDIATE;")
                    migration.up(cursor)
                    now_str = datetime.now(UTC).isoformat()
                    cursor.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?);",
                        (migration.version, migration.name, now_str)
                    )
                    self._conn.commit()
                    applied_count += 1
                except Exception as e:
                    self._conn.rollback()
                    raise SchemaMigrationError(
                        f"Failed migrating to version {migration.version} ({migration.name}): {e}"
                    ) from e

        return applied_count
