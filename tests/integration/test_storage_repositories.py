"""
Integration tests for domain repositories and the shared SecureStorage API.
"""
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from local_security.core.exceptions import PermissionDeniedError
from local_security.database.database_manager import DatabaseManager
from local_security.models.records import (
    ActivityRecord,
    MemoryRecord,
    PersonRecord,
    RelationshipRecord,
    RoutineFrequency,
    RoutineLogRecord,
    RoutineLogStatus,
    RoutineRecord,
)
from local_security.models.users import UserRole
from local_security.storage.secure_storage import SecureStorage


@pytest.fixture
def secure_storage(tmp_path: Path) -> SecureStorage:
    db_path = tmp_path / "integration_vault.db"
    db = DatabaseManager(db_path)
    db.connect(os.urandom(32))
    return SecureStorage(db)


def test_memory_repository_crud_and_fts5_search(secure_storage: SecureStorage):
    repo = secure_storage.memories

    m1 = MemoryRecord(
        title="Walk in Kensington Gardens",
        content="Saw beautiful autumn trees near Peter Pan statue with Eleanor.",
        category="places",
        importance_level=4,
        tags=["autumn", "walk", "park"],
        is_shared_with_caregiver=False,
    )
    m1_id = repo.save_memory(m1)
    assert m1_id is not None

    m2 = MemoryRecord(
        title="Morning Medication Schedule",
        content="Blood pressure pills taken daily after breakfast with water.",
        category="medical",
        importance_level=5,
        tags=["health", "medication"],
        is_shared_with_caregiver=True,
    )
    m2_id = repo.save_memory(m2)

    # Search with FTS5: keyword "autumn"
    results = repo.search_memories("autumn")
    assert len(results) == 1
    assert results[0].id == m1_id

    # Search with FTS5: keyword "medication"
    results_med = repo.search_memories("medication")
    assert len(results_med) == 1
    assert results_med[0].id == m2_id

    # Caregiver access check:
    # Caregiver reading shared memory succeeds
    caregiver_m2 = repo.get_memory(m2_id, role=UserRole.CAREGIVER)
    assert caregiver_m2.title == "Morning Medication Schedule"

    # Caregiver reading unshared memory fails
    with pytest.raises(PermissionDeniedError):
        repo.get_memory(m1_id, role=UserRole.CAREGIVER)

    # Caregiver query only returns shared memories
    caregiver_memories = repo.get_memories_for_caregiver()
    assert len(caregiver_memories) == 1
    assert caregiver_memories[0].id == m2_id

    # Update memory
    repo.update_memory(m1_id, {"title": "Updated Walk in Kensington Gardens"})
    updated = repo.get_memory(m1_id)
    assert updated.title == "Updated Walk in Kensington Gardens"

    # Delete memory
    assert repo.delete_memory(m1_id) is True
    assert repo.get_memory(m1_id) is None


def test_people_repository_and_relationships(secure_storage: SecureStorage):
    repo = secure_storage.people

    p1 = PersonRecord(name="Eleanor Vance", relationship_to_user="Daughter", phone="555-0192")
    p1_id = repo.save_person(p1)

    p2 = PersonRecord(name="Dr. Marcus Bell", relationship_to_user="Primary Physician", phone="555-0188")
    p2_id = repo.save_person(p2)

    # Search
    found = repo.search_people("Eleanor")
    assert len(found) == 1
    assert found[0].name == "Eleanor Vance"

    # Save Relationship
    rel = RelationshipRecord(
        person_a_id=p1_id,
        person_b_id=p2_id,
        relationship_type="care_coordinator",
        description="Eleanor coordinates appointments with Dr. Bell",
    )
    rel_id = repo.save_relationship(rel)
    assert rel_id is not None

    rels = repo.get_relationships(p1_id)
    assert len(rels) == 1
    assert rels[0].relationship_type == "care_coordinator"


def test_routine_repository_and_missed_tracking(secure_storage: SecureStorage):
    repo = secure_storage.routines

    r1 = RoutineRecord(
        title="Take Morning Blood Pressure Pill",
        frequency=RoutineFrequency.DAILY,
        time_of_day="08:00",
        is_shared_with_caregiver=True,
    )
    r1_id = repo.save_routine(r1)

    r2 = RoutineRecord(
        title="Evening 15-Minute Stroll",
        frequency=RoutineFrequency.DAILY,
        time_of_day="18:00",
        is_shared_with_caregiver=False,
    )
    r2_id = repo.save_routine(r2)

    today = date.today()

    # Before logging, both active routines are "missed" (uncompleted) for today
    missed_before = repo.get_missed_routines(today)
    assert len(missed_before) == 2

    # Log routine 1 as completed
    log = RoutineLogRecord(
        routine_id=r1_id,
        scheduled_date=today,
        status=RoutineLogStatus.COMPLETED,
        notes="Taken with orange juice",
    )
    repo.log_routine_status(log)

    # Now only routine 2 is missed
    missed_after = repo.get_missed_routines(today)
    assert len(missed_after) == 1
    assert missed_after[0].id == r2_id

    # Check routine logs history
    history = repo.get_routine_logs(r1_id)
    assert len(history) == 1
    assert history[0].status == RoutineLogStatus.COMPLETED


def test_activity_repository_and_weekly_summary(secure_storage: SecureStorage):
    repo = secure_storage.activities
    now = datetime.now(UTC)

    # Log activities across past 3 days
    for day_offset in [0, 1, 2]:
        act_time = now - timedelta(days=day_offset, hours=2)
        repo.save_activity(ActivityRecord(
            activity_name=f"Walk Day {day_offset}",
            category="exercise",
            started_at=act_time,
        ))

    summary = repo.get_weekly_consistency_summary()
    assert summary["days_with_activity"] == 3
    assert summary["total_activities_logged"] == 3
    assert "exercise" in summary["category_distribution"]
    assert summary["consistency_score_percentage"] > 0


def test_generic_secure_storage_api(secure_storage: SecureStorage):
    # Save record generic
    rec_id = secure_storage.save_record(
        module="people",
        record_type="person",
        data={"name": "Samuel Jackson", "relationship_to_user": "Neighbor"}
    )
    assert rec_id is not None

    # Get record generic
    record = secure_storage.get_record("people", rec_id)
    assert record is not None
    assert record["name"] == "Samuel Jackson"

    # Search generic
    search_res = secure_storage.search_records("people", "Samuel")
    assert len(search_res) == 1
    assert search_res[0]["name"] == "Samuel Jackson"
