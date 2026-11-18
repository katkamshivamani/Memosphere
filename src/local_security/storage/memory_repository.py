"""
Memory Repository providing encrypted CRUD, FTS5 full-text search, and caregiver filtering.
"""
import json
import uuid

from local_security.access_control.permission_manager import PermissionManager
from local_security.core.exceptions import RecordNotFoundError
from local_security.database.database_manager import DatabaseManager
from local_security.models.permissions import SecurityAction, SecurityModule
from local_security.models.records import MemoryRecord, utc_now
from local_security.models.users import UserRole


class MemoryRepository:
    """Manages secure persistence and FTS5 search for personal memories."""

    def __init__(self, db_manager: DatabaseManager, permission_manager: PermissionManager | None = None):
        self._db = db_manager
        self._perms = permission_manager or PermissionManager()

    def _row_to_record(self, row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            category=row["category"],
            importance_level=row["importance_level"],
            tags=json.loads(row["tags_json"] or "[]"),
            people_mentioned=json.loads(row["people_mentioned_json"] or "[]"),
            places_mentioned=json.loads(row["places_mentioned_json"] or "[]"),
            is_shared_with_caregiver=bool(row["is_shared_with_caregiver"]),
            metadata=json.loads(row["metadata_json"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def save_memory(self, memory: MemoryRecord, role: UserRole = UserRole.OWNER) -> str:
        """Saves a new memory into the encrypted database."""
        self._perms.check_access(SecurityModule.MEMORIES, SecurityAction.CREATE, role=role)

        mem_id = memory.id or str(uuid.uuid4())
        now_str = utc_now().isoformat()
        created_str = memory.created_at.isoformat() if hasattr(memory.created_at, "isoformat") else str(memory.created_at)

        with self._db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO memories (
                    id, title, content, category, importance_level,
                    tags_json, people_mentioned_json, places_mentioned_json,
                    is_shared_with_caregiver, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    mem_id,
                    memory.title,
                    memory.content,
                    memory.category,
                    memory.importance_level,
                    json.dumps(memory.tags),
                    json.dumps(memory.people_mentioned),
                    json.dumps(memory.places_mentioned),
                    int(memory.is_shared_with_caregiver),
                    json.dumps(memory.metadata),
                    created_str,
                    now_str,
                )
            )
        return mem_id

    def get_memory(self, memory_id: str, role: UserRole = UserRole.OWNER) -> MemoryRecord | None:
        """Retrieves a single memory by ID, enforcing selective caregiver sharing."""
        cur = self._db.cursor()
        cur.execute("SELECT * FROM memories WHERE id = ?;", (memory_id,))
        row = cur.fetchone()
        if not row:
            return None

        is_shared = bool(row["is_shared_with_caregiver"])
        self._perms.check_access(
            SecurityModule.MEMORIES,
            SecurityAction.READ,
            role=role,
            is_shared_with_caregiver=is_shared
        )
        return self._row_to_record(row)

    def search_memories(
        self,
        query: str,
        category: str | None = None,
        role: UserRole = UserRole.OWNER,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        """
        Executes full-text search using SQLCipher FTS5 index.
        Falls back to parameterized LIKE search if FTS5 query encounters syntax error.
        """
        self._perms.check_access(SecurityModule.MEMORIES, SecurityAction.READ, role=role)
        cur = self._db.cursor()

        # FTS5 search
        records: list[MemoryRecord] = []
        try:
            # Clean search query for FTS5 tokens
            clean_tokens = [t.strip() for t in query.split() if t.strip().isalnum()]
            if clean_tokens:
                fts_query = " OR ".join(f'"{t}"*' for t in clean_tokens)
                cur.execute(
                    """
                    SELECT m.* FROM memories m
                    JOIN memories_fts f ON m.id = f.content_id
                    WHERE memories_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?;
                    """,
                    (fts_query, limit)
                )
                rows = cur.fetchall()
            else:
                rows = []
        except Exception:
            # Fallback to standard LIKE
            like_pat = f"%{query}%"
            cur.execute(
                """
                SELECT * FROM memories
                WHERE title LIKE ? OR content LIKE ?
                ORDER BY updated_at DESC LIMIT ?;
                """,
                (like_pat, like_pat, limit)
            )
            rows = cur.fetchall()

        for row in rows:
            is_shared = bool(row["is_shared_with_caregiver"])
            if self._perms.check_access(
                SecurityModule.MEMORIES,
                SecurityAction.READ,
                role=role,
                is_shared_with_caregiver=is_shared,
                raise_exception=False,
            ):
                records.append(self._row_to_record(row))

        if category:
            records = [r for r in records if r.category == category]
        return records

    def update_memory(self, memory_id: str, updates: dict, role: UserRole = UserRole.OWNER) -> MemoryRecord:
        """Updates fields of an existing memory record."""
        existing = self.get_memory(memory_id, role=role)
        if not existing:
            raise RecordNotFoundError(f"Memory with ID '{memory_id}' not found.")

        self._perms.check_access(
            SecurityModule.MEMORIES,
            SecurityAction.UPDATE,
            role=role,
            is_shared_with_caregiver=existing.is_shared_with_caregiver
        )

        title = updates.get("title", existing.title)
        content = updates.get("content", existing.content)
        category = updates.get("category", existing.category)
        importance = updates.get("importance_level", existing.importance_level)
        tags = updates.get("tags", existing.tags)
        people = updates.get("people_mentioned", existing.people_mentioned)
        places = updates.get("places_mentioned", existing.places_mentioned)
        is_shared = updates.get("is_shared_with_caregiver", existing.is_shared_with_caregiver)
        meta = updates.get("metadata", existing.metadata)
        now_str = utc_now().isoformat()

        with self._db.transaction() as cur:
            cur.execute(
                """
                UPDATE memories SET
                    title = ?, content = ?, category = ?, importance_level = ?,
                    tags_json = ?, people_mentioned_json = ?, places_mentioned_json = ?,
                    is_shared_with_caregiver = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?;
                """,
                (
                    title,
                    content,
                    category,
                    importance,
                    json.dumps(tags),
                    json.dumps(people),
                    json.dumps(places),
                    int(is_shared),
                    json.dumps(meta),
                    now_str,
                    memory_id,
                )
            )
        return self.get_memory(memory_id, role=role)  # type: ignore

    def delete_memory(self, memory_id: str, role: UserRole = UserRole.OWNER) -> bool:
        """Deletes a memory record."""
        self._perms.check_access(SecurityModule.MEMORIES, SecurityAction.DELETE, role=role)
        with self._db.transaction() as cur:
            cur.execute("DELETE FROM memories WHERE id = ?;", (memory_id,))
            return cur.rowcount > 0

    def get_memories_for_caregiver(self, limit: int = 50) -> list[MemoryRecord]:
        """Retrieves only memories explicitly marked as shared with caregivers."""
        cur = self._db.cursor()
        cur.execute(
            """
            SELECT * FROM memories
            WHERE is_shared_with_caregiver = 1
            ORDER BY updated_at DESC
            LIMIT ?;
            """,
            (limit,)
        )
        return [self._row_to_record(row) for row in cur.fetchall()]
