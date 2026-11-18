"""
People and Relationships Repository.
"""
import json
import uuid

from local_security.access_control.permission_manager import PermissionManager
from local_security.database.database_manager import DatabaseManager
from local_security.models.permissions import SecurityAction, SecurityModule
from local_security.models.records import PersonRecord, RelationshipRecord, utc_now
from local_security.models.users import UserRole


class PeopleRepository:
    """Manages secure records for contacts, relationships, and people."""

    def __init__(self, db_manager: DatabaseManager, permission_manager: PermissionManager | None = None):
        self._db = db_manager
        self._perms = permission_manager or PermissionManager()

    def _row_to_person(self, row) -> PersonRecord:
        return PersonRecord(
            id=row["id"],
            name=row["name"],
            nickname=row["nickname"],
            relationship_to_user=row["relationship_to_user"],
            phone=row["phone"],
            email=row["email"],
            notes=row["notes"],
            avatar_path=row["avatar_path"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def save_person(self, person: PersonRecord, role: UserRole = UserRole.OWNER) -> str:
        self._perms.check_access(SecurityModule.PEOPLE, SecurityAction.CREATE, role=role)
        p_id = person.id or str(uuid.uuid4())
        now_str = utc_now().isoformat()
        created_str = person.created_at.isoformat() if hasattr(person.created_at, "isoformat") else str(person.created_at)

        with self._db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO people (
                    id, name, nickname, relationship_to_user, phone, email,
                    notes, avatar_path, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    p_id,
                    person.name,
                    person.nickname,
                    person.relationship_to_user,
                    person.phone,
                    person.email,
                    person.notes,
                    person.avatar_path,
                    json.dumps(person.metadata),
                    created_str,
                    now_str,
                )
            )
        return p_id

    def get_person(self, person_id: str, role: UserRole = UserRole.OWNER) -> PersonRecord | None:
        self._perms.check_access(SecurityModule.PEOPLE, SecurityAction.READ, role=role)
        cur = self._db.cursor()
        cur.execute("SELECT * FROM people WHERE id = ?;", (person_id,))
        row = cur.fetchone()
        return self._row_to_person(row) if row else None

    def search_people(self, query: str, role: UserRole = UserRole.OWNER, limit: int = 20) -> list[PersonRecord]:
        self._perms.check_access(SecurityModule.PEOPLE, SecurityAction.READ, role=role)
        cur = self._db.cursor()
        pattern = f"%{query}%"
        cur.execute(
            """
            SELECT * FROM people
            WHERE name LIKE ? OR nickname LIKE ? OR relationship_to_user LIKE ?
            ORDER BY name ASC LIMIT ?;
            """,
            (pattern, pattern, pattern, limit)
        )
        return [self._row_to_person(row) for row in cur.fetchall()]

    def save_relationship(self, rel: RelationshipRecord, role: UserRole = UserRole.OWNER) -> str:
        self._perms.check_access(SecurityModule.PEOPLE, SecurityAction.CREATE, role=role)
        r_id = rel.id or str(uuid.uuid4())
        created_str = rel.created_at.isoformat() if hasattr(rel.created_at, "isoformat") else str(rel.created_at)

        with self._db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO relationships (id, person_a_id, person_b_id, relationship_type, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (r_id, rel.person_a_id, rel.person_b_id, rel.relationship_type, rel.description, created_str)
            )
        return r_id

    def get_relationships(self, person_id: str, role: UserRole = UserRole.OWNER) -> list[RelationshipRecord]:
        self._perms.check_access(SecurityModule.PEOPLE, SecurityAction.READ, role=role)
        cur = self._db.cursor()
        cur.execute(
            "SELECT * FROM relationships WHERE person_a_id = ? OR person_b_id = ?;",
            (person_id, person_id)
        )
        rows = cur.fetchall()
        return [
            RelationshipRecord(
                id=row["id"],
                person_a_id=row["person_a_id"],
                person_b_id=row["person_b_id"],
                relationship_type=row["relationship_type"],
                description=row["description"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
