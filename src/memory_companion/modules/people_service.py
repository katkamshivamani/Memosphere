"""People and relationships in the shared encrypted database."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from memory_agent.core.exceptions import RecordNotFoundError

from memory_companion.modules.audit import AuditService
from memory_companion.modules.common import like_clause, new_id, search_tokens, utc_now_iso


class PeopleService:
    def __init__(self, db, audit: Optional[AuditService] = None) -> None:
        self._db = db
        self._audit = audit

    def search_people(self, user_id: str, query: str) -> list[dict]:
        sql = (
            "SELECT id, user_id, name, relationship, notes, created_at, updated_at "
            "FROM people WHERE user_id = ?"
        )
        params: list[Any] = [user_id]
        clause, clause_params = like_clause(("name", "relationship", "notes"), search_tokens(query))
        if clause:
            sql += f" AND {clause}"
            params.extend(clause_params)
        sql += " ORDER BY name COLLATE NOCASE LIMIT 25"
        return [dict(row) for row in self._db.connection().execute(sql, params).fetchall()]

    def get_person(self, user_id: str, person_id: str) -> Optional[dict]:
        row = self._db.connection().execute(
            "SELECT id, user_id, name, relationship, notes, created_at, updated_at "
            "FROM people WHERE user_id = ? AND id = ?",
            (user_id, person_id),
        ).fetchone()
        return dict(row) if row else None

    def get_relationships(self, user_id: str, person_id: str) -> list[dict]:
        rows = self._db.connection().execute(
            "SELECT r.id, r.user_id, r.person_id, r.relationship, r.notes, "
            "r.created_at, r.updated_at, p.name AS person_name "
            "FROM relationships r JOIN people p ON p.id = r.person_id AND p.user_id = r.user_id "
            "WHERE r.user_id = ? AND r.person_id = ? ORDER BY r.created_at",
            (user_id, person_id),
        ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["title"] = f"{item.get('person_name', 'Person')} - {item['relationship']}"
            item["content"] = item.get("notes") or f"Relationship: {item['relationship']}"
            results.append(item)
        return results

    def create_person(self, user_id: str, data: Mapping[str, Any]) -> dict:
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("A person needs a name.")
        person_id = new_id("per")
        now = utc_now_iso()
        with self._db.write() as conn:
            conn.execute(
                "INSERT INTO people (id, user_id, name, relationship, notes, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    person_id,
                    user_id,
                    name,
                    str(data.get("relationship") or ""),
                    str(data.get("notes") or ""),
                    now,
                    now,
                ),
            )
        if self._audit:
            self._audit.log(
                action="person.create", user_id=user_id, target_type="person", target_id=person_id
            )
        return self.get_person(user_id, person_id) or {}

    def create_relationship(self, user_id: str, person_id: str, data: Mapping[str, Any]) -> dict:
        if self.get_person(user_id, person_id) is None:
            raise RecordNotFoundError("Person not found for this user.")
        relationship_id = new_id("rel")
        now = utc_now_iso()
        with self._db.write() as conn:
            conn.execute(
                "INSERT INTO relationships (id, user_id, person_id, relationship, notes, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    relationship_id,
                    user_id,
                    person_id,
                    str(data.get("relationship") or "contact"),
                    str(data.get("notes") or ""),
                    now,
                    now,
                ),
            )
        if self._audit:
            self._audit.log(
                action="relationship.create",
                user_id=user_id,
                target_type="relationship",
                target_id=relationship_id,
            )
        return {
            "id": relationship_id,
            "user_id": user_id,
            "person_id": person_id,
            "relationship": str(data.get("relationship") or "contact"),
            "notes": str(data.get("notes") or ""),
            "created_at": now,
            "updated_at": now,
        }

    def count(self, user_id: str) -> int:
        row = self._db.connection().execute(
            "SELECT count(*) FROM people WHERE user_id = ?", (user_id,)
        ).fetchone()
        return int(row[0]) if row else 0
