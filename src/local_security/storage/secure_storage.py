"""
Shared Secure Storage API providing generic and domain repository access for team integration.
"""
import uuid
from typing import Any

from local_security.access_control.permission_manager import PermissionManager
from local_security.database.database_manager import DatabaseManager
from local_security.models.records import (
    ActivityRecord,
    MemoryRecord,
    PersonRecord,
    RoutineRecord,
)
from local_security.models.users import UserRole
from local_security.storage.activity_repository import ActivityRepository
from local_security.storage.memory_repository import MemoryRepository
from local_security.storage.people_repository import PeopleRepository
from local_security.storage.routine_repository import RoutineRepository


class SecureStorage:
    """
    Unified public storage interface used by all companion modules.
    Abstracts SQLCipher, encryption, and platform keys behind clean typed APIs.
    """

    def __init__(self, db_manager: DatabaseManager, permission_manager: PermissionManager | None = None):
        self._db = db_manager
        self._perms = permission_manager or PermissionManager()

        # Domain repositories
        self.memories = MemoryRepository(db_manager, self._perms)
        self.people = PeopleRepository(db_manager, self._perms)
        self.routines = RoutineRepository(db_manager, self._perms)
        self.activities = ActivityRepository(db_manager, self._perms)

    def save_record(
        self,
        module: str,
        record_type: str,
        data: dict[str, Any],
        role: UserRole = UserRole.OWNER,
    ) -> str:
        """Generic record saver routing to domain models."""
        mod = module.lower()
        if mod in ("memories", "memory"):
            rec = MemoryRecord(**data)
            return self.memories.save_memory(rec, role=role)
        elif mod in ("people", "person"):
            rec = PersonRecord(**data)
            return self.people.save_person(rec, role=role)
        elif mod in ("places", "place"):
            from local_security.models.records import PlaceRecord
            rec = PlaceRecord(**data)
            p_id = rec.id or str(uuid.uuid4())
            import json

            from local_security.models.records import utc_now
            now_str = utc_now().isoformat()
            with self._db.transaction() as cur:
                cur.execute(
                    """
                    INSERT INTO places (id, name, address, category, description, latitude, longitude, metadata_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (p_id, rec.name, rec.address, rec.category, rec.description, rec.latitude, rec.longitude, json.dumps(rec.metadata), now_str, now_str)
                )
            return p_id
        elif mod in ("items", "item"):
            from local_security.models.records import ItemRecord
            rec = ItemRecord(**data)
            i_id = rec.id or str(uuid.uuid4())
            import json

            from local_security.models.records import utc_now
            now_str = utc_now().isoformat()
            with self._db.transaction() as cur:
                cur.execute(
                    """
                    INSERT INTO items (id, name, usual_location, current_location, category, description, image_path, last_seen_at, metadata_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (i_id, rec.name, rec.usual_location, rec.current_location, rec.category, rec.description, rec.image_path, rec.last_seen_at, json.dumps(rec.metadata), now_str, now_str)
                )
            return i_id
        elif mod in ("routines", "routine"):
            rec = RoutineRecord(**data)
            return self.routines.save_routine(rec, role=role)
        elif mod in ("activities", "activity"):
            rec = ActivityRecord(**data)
            return self.activities.save_activity(rec, role=role)
        else:
            raise ValueError(f"Unsupported storage module '{module}'.")

    def get_record(
        self,
        module: str,
        record_id: str,
        role: UserRole = UserRole.OWNER,
    ) -> dict[str, Any] | None:
        """Generic record retriever returning dictionary representation."""
        mod = module.lower()
        if mod in ("memories", "memory"):
            item = self.memories.get_memory(record_id, role=role)
            return item.model_dump() if item else None
        elif mod in ("people", "person"):
            item = self.people.get_person(record_id, role=role)
            return item.model_dump() if item else None
        elif mod in ("routines", "routine"):
            item = self.routines.get_routine(record_id, role=role)
            return item.model_dump() if item else None
        else:
            raise ValueError(f"Unsupported storage module '{module}'.")

    def update_record(
        self,
        module: str,
        record_id: str,
        data: dict[str, Any],
        role: UserRole = UserRole.OWNER,
    ) -> dict[str, Any]:
        """Generic record updater."""
        mod = module.lower()
        if mod in ("memories", "memory"):
            updated = self.memories.update_memory(record_id, data, role=role)
            return updated.model_dump()
        elif mod in ("routines", "routine"):
            updated = self.routines.update_routine(record_id, data, role=role)
            return updated.model_dump()
        else:
            raise ValueError(f"Module '{module}' does not support generic update_record.")

    def delete_record(
        self,
        module: str,
        record_id: str,
        role: UserRole = UserRole.OWNER,
    ) -> bool:
        """Generic record deleter."""
        mod = module.lower()
        if mod in ("memories", "memory"):
            return self.memories.delete_memory(record_id, role=role)
        elif mod in ("routines", "routine"):
            return self.routines.delete_routine(record_id, role=role)
        else:
            raise ValueError(f"Module '{module}' does not support generic delete_record.")

    def search_records(
        self,
        module: str,
        query: str,
        role: UserRole = UserRole.OWNER,
    ) -> list[dict[str, Any]]:
        """Generic search over module records."""
        mod = module.lower()
        if mod in ("memories", "memory"):
            results = self.memories.search_memories(query, role=role)
            return [r.model_dump() for r in results]
        elif mod in ("people", "person"):
            results = self.people.search_people(query, role=role)
            return [r.model_dump() for r in results]
        else:
            raise ValueError(f"Module '{module}' does not support generic search.")
