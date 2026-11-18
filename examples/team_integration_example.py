"""
Example 3: Cross-Team Integration Demonstration.
Shows how the three peer modules integrate with the Local Privacy & Security foundation:
  Module A: Universal Personal Knowledge Base (People, Places, Items, Memories)
  Module B: Conversational AI Companion (Dialogue History, Local Retrieval)
  Module C: Permission-Based Monitoring Dashboard (Routines, Adherence, Caregiver Sharing)
"""
from datetime import UTC, date, datetime
from pathlib import Path

from local_security.core.configuration import SecurityConfig
from local_security.core.exceptions import PermissionDeniedError
from local_security.core.security_manager import SecurityManager
from local_security.models.records import (
    MemoryRecord,
    PersonRecord,
    RoutineFrequency,
    RoutineLogRecord,
    RoutineLogStatus,
    RoutineRecord,
)
from local_security.models.users import UserRole


def main():
    print("=================================================================")
    print("   AI-POWERED PERSONAL MEMORY COMPANION - INTEGRATION DEMO       ")
    print("=================================================================\n")

    config = SecurityConfig(
        app_data_dir=Path("./example_data"),
        database_filename="team_integration_vault.enc.db",
        key_identifier="TeamIntegrationVaultKey",
    )
    sec_mgr = SecurityManager(config)
    sec_mgr.initialize()

    # Setup primary user
    if not sec_mgr.auth.is_setup_completed():
        sec_mgr.auth.setup_initial_user(
            username="robert",
            display_name="Robert Vance",
            pin="819203",
            confirm_pin="819203",
        )

    sec_mgr.unlock_with_pin("robert", "819203")

    # -----------------------------------------------------------------
    # MODULE A: Universal Personal Knowledge Base
    # -----------------------------------------------------------------
    print("--- [MODULE A] Universal Personal Knowledge Base ---")
    storage = sec_mgr.storage

    # Store Person & Caregiver relationship
    dr_id = storage.people.save_person(PersonRecord(
        name="Dr. Helen Cho",
        relationship_to_user="Neurologist",
        phone="555-0144",
        notes="Clinic on 4th floor, appointments on Tuesdays.",
    ))
    print(f"[OK] Person registered: Dr. Helen Cho (ID: {dr_id[:8]}...)")

    # Store Place & Item
    storage.save_record(
        module="places",
        record_type="place",
        data={"name": "Maple Community Garden", "category": "park", "address": "120 Elm St"}
    )
    print("[OK] Place saved: Maple Community Garden")

    # Store Personal Memories
    mem_id1 = storage.memories.save_memory(MemoryRecord(
        title="Favorite Blue Reading Glasses",
        content="I keep my blue reading glasses in the wooden drawer beside the armchair in the living room.",
        category="items",
        tags=["glasses", "reading", "living room"],
        is_shared_with_caregiver=False,  # Private memory
    ))

    mem_id2 = storage.memories.save_memory(MemoryRecord(
        title="Afternoon Physical Therapy Exercises",
        content="Perform 10 leg raises and shoulder stretch routine before tea time.",
        category="medical",
        tags=["exercise", "therapy", "health"],
        is_shared_with_caregiver=True,  # Shared with Caregiver
    ))
    print("[OK] Memories stored with FTS5 indexing.")

    # -----------------------------------------------------------------
    # MODULE B: Conversational AI Companion
    # -----------------------------------------------------------------
    print("\n--- [MODULE B] Conversational AI Companion ---")
    user_query = "Where did I put my reading glasses?"
    print(f"User Voice/Text Input: '{user_query}'")

    # Local FTS5 lookup for context-aware memory retrieval
    relevant_memories = storage.memories.search_memories("glasses")
    context_text = relevant_memories[0].content if relevant_memories else "No matching memory found."
    print(f"Retrieved Local Context: \"{context_text}\"")

    ai_reply = "You mentioned that your blue reading glasses are kept in the wooden drawer beside the armchair in the living room."
    print(f"AI Companion Response: \"{ai_reply}\"")

    # Log dialogue securely
    conv_id = "conv-session-001"
    sec_mgr.db.cursor()
    with sec_mgr.db.transaction() as tx:
        tx.execute(
            "INSERT INTO conversations (id, conversation_id, sender, message_text, created_at) VALUES (?, ?, ?, ?, ?);",
            ("msg-1", conv_id, "user", user_query, datetime.now(UTC).isoformat())
        )
        tx.execute(
            "INSERT INTO conversations (id, conversation_id, sender, message_text, created_at) VALUES (?, ?, ?, ?, ?);",
            ("msg-2", conv_id, "companion_ai", ai_reply, datetime.now(UTC).isoformat())
        )
    print("[OK] Conversation dialogue securely logged into encrypted vault.")

    # -----------------------------------------------------------------
    # MODULE C: Permission-Based Monitoring Dashboard (Caregiver View)
    # -----------------------------------------------------------------
    print("\n--- [MODULE C] Caregiver Monitoring & Escalation Dashboard ---")

    # Create daily routine
    routine_id = storage.routines.save_routine(RoutineRecord(
        title="Take Morning Blood Pressure Medicine",
        frequency=RoutineFrequency.DAILY,
        time_of_day="08:30",
        is_shared_with_caregiver=True,
    ))

    today = date.today()
    # Check missed routines before logging
    missed = storage.routines.get_missed_routines(today)
    print(f"- Missed/Pending Routines for Today ({today}): {len(missed)}")
    for m in missed:
        print(f"   [PENDING] Routine: '{m.title}' scheduled for {m.time_of_day}")

    # Log routine completion
    storage.routines.log_routine_status(RoutineLogRecord(
        routine_id=routine_id,
        scheduled_date=today,
        status=RoutineLogStatus.COMPLETED,
        notes="Logged by Robert with water",
    ))
    print("- Robert completed routine. Re-checking missed routines:")
    missed_after = storage.routines.get_missed_routines(today)
    print(f"   Pending Routines Remaining: {len(missed_after)}")

    # Caregiver Selective Access Verification:
    print("\n[Access Control Check for Caregiver Role]:")
    # 1. Caregiver accessing shared exercise memory -> SUCCEEDS
    shared_mem = storage.memories.get_memory(mem_id2, role=UserRole.CAREGIVER)
    print(f"  [OK] Caregiver access to shared memory '{shared_mem.title}': ALLOWED")

    # 2. Caregiver accessing private glasses memory -> DENIED
    try:
        storage.memories.get_memory(mem_id1, role=UserRole.CAREGIVER)
        print("  [ERROR] Caregiver accessed unshared private memory!")
    except PermissionDeniedError as e:
        print(f"  [OK] Caregiver access to unshared memory: REJECTED ({e.reason})")

    # 7-day consistency summary
    summary = storage.activities.get_weekly_consistency_summary()
    print(f"\n- Weekly Routine & Activity Consistency Score: {summary['consistency_score_percentage']}%")

    sec_mgr.shutdown()
    print("\n=================================================================")
    print("   Integration demonstration finished successfully!              ")
    print("=================================================================")


if __name__ == "__main__":
    main()
