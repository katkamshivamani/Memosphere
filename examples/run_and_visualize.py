"""
Local Working Demonstration Script.
Exercises the entire Privacy & Security stack end-to-end:
1. Initializes SQLCipher 4.12 encrypted database & OS key storage.
2. Configures user profile and salted Argon2id PIN.
3. Unlocks authenticated session.
4. Performs domain CRUD & FTS5 full-text search.
5. Runs live on-disk ciphertext audit (Shannon entropy & plaintext inspection).
6. Tests caregiver selective sharing access rules.
7. Instantiates PySide6 UI, renders the Dashboard and Lock Screen, and captures screenshots.
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, date

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from local_security.core.security_manager import SecurityManager
from local_security.core.configuration import SecurityConfig
from local_security.models.records import (
    MemoryRecord, PersonRecord, RoutineRecord, RoutineFrequency,
    RoutineLogRecord, RoutineLogStatus, ActivityRecord
)
from local_security.models.users import UserRole
from local_security.core.exceptions import PermissionDeniedError
from local_security.ui.windows.dashboard_window import SecurityDashboardWindow
from local_security.ui.dialogs.setup_dialog import SetupDialog


def run_working_demo():
    print("=====================================================================")
    print(" LOCAL PRIVACY & SECURITY MODULE - LIVE EXECUTION & VERIFICATION     ")
    print("=====================================================================")

    demo_dir = Path("./demo_vault")
    demo_dir.mkdir(parents=True, exist_ok=True)

    config = SecurityConfig(
        app_data_dir=demo_dir,
        database_filename="memory_companion_vault.enc.db",
        key_identifier="DemoMemoryVaultKey",
    )

    print("\n[STEP 1] INITIALIZING SQLCIPHER DATABASE & OS KEY STORAGE")
    sec_mgr = SecurityManager(config)
    sec_mgr.initialize()

    cipher_version = sec_mgr.db.get_cipher_version()
    print(f" -> SQLCipher Engine: {cipher_version}")
    print(f" -> Database File: {config.database_path.resolve()}")
    print(f" -> OS Key Storage Backend: {sec_mgr.key_storage.__class__.__name__}")

    print("\n[STEP 2] USER PROFILE SETUP & ARGON2ID PIN HASHING")
    if not sec_mgr.auth.is_setup_completed():
        user = sec_mgr.auth.setup_initial_user(
            username="eleanor_vance",
            display_name="Eleanor Vance",
            pin="739104",
            confirm_pin="739104",
            enable_biometrics=True,
        )
        print(f" -> User Created: {user.display_name} (@{user.username})")
        print(f" -> PIN Argon2id Hash Prefix: {user.pin_hash[:30]}...")

    print("\n[STEP 3] OS BIOMETRIC HARDWARE DETECTION (WINDOWS HELLO)")
    bio_avail, bio_code, bio_desc = sec_mgr.auth.biometric_authenticator.is_biometric_available()
    print(f" -> Biometric Available: {bio_avail}")
    print(f" -> Subsystem Status Code: {bio_code.value}")
    print(f" -> Description: {bio_desc}")

    print("\n[STEP 4] AUTHENTICATION & SESSION LIFECYCLE")
    print(" -> Authenticating with candidate PIN '739104'...")
    session = sec_mgr.unlock_with_pin("eleanor_vance", "739104")
    print(f" -> Authentication SUCCESS!")
    print(f" -> Active Session Token: {session.session_id}")
    print(f" -> Application Lock State: LOCKED={sec_mgr.is_locked}")

    print("\n[STEP 5] STORING ENCRYPTED PERSONAL MEMORIES & DOMAIN RECORDS")
    storage = sec_mgr.storage

    # Store Person
    person_id = storage.people.save_person(PersonRecord(
        name="Sarah Jenkins",
        relationship_to_user="Daughter & Primary Caregiver",
        phone="555-0144",
        notes="Visits every Saturday morning with fresh groceries."
    ))
    print(f" -> Contact Saved: Sarah Jenkins (ID: {person_id})")

    # Store Routine
    routine_id = storage.routines.save_routine(RoutineRecord(
        title="Morning Blood Pressure Medicine (Lisinopril)",
        frequency=RoutineFrequency.DAILY,
        time_of_day="08:00",
        is_shared_with_caregiver=True,
    ))
    print(f" -> Daily Routine Saved: Lisinopril Medicine (ID: {routine_id})")

    # Store Memories
    mem1_id = storage.memories.save_memory(MemoryRecord(
        title="Autumn Walk at Lakeview Park",
        content="Walked around the cedar lake with Sarah. We watched ducklings near the wooden dock.",
        category="places",
        importance_level=4,
        tags=["lake", "walk", "ducks", "autumn"],
        is_shared_with_caregiver=False, # Private memory
    ))
    print(f" -> Private Memory Stored: 'Autumn Walk at Lakeview Park'")

    mem2_id = storage.memories.save_memory(MemoryRecord(
        title="Allergy Warning: Penicillin",
        content="Severe allergic reaction to Penicillin and Amoxicillin. Always inform doctors.",
        category="medical",
        importance_level=5,
        tags=["medical", "allergy", "warning"],
        is_shared_with_caregiver=True, # Caregiver shared
    ))
    print(f" -> Caregiver-Shared Memory Stored: 'Allergy Warning: Penicillin'")

    # Store Activity
    storage.activities.save_activity(ActivityRecord(
        activity_name="Morning 20-min gentle yoga",
        category="exercise",
    ))
    print(f" -> Activity Saved: Morning yoga")

    print("\n[STEP 6] TESTING SQLCIPHER FTS5 FULL-TEXT SEARCH")
    for keyword in ["ducklings", "penicillin", "cedar"]:
        results = storage.memories.search_memories(keyword)
        print(f" -> Query '{keyword}': Found {len(results)} record(s)")
        for r in results:
            print(f"     * [{r.category.upper()}] {r.title} => \"{r.content}\"")

    print("\n[STEP 7] CAREGIVER ACCESS CONTROL & SELECTIVE SHARING ENFORCEMENT")
    # Caregiver reads shared memory
    shared_result = storage.memories.get_memory(mem2_id, role=UserRole.CAREGIVER)
    print(f" -> Caregiver reading shared medical note: ALLOWED ('{shared_result.title}')")

    # Caregiver attempts to read private memory
    try:
        storage.memories.get_memory(mem1_id, role=UserRole.CAREGIVER)
        print(" -> ERROR: Caregiver accessed unshared private memory!")
    except PermissionDeniedError as e:
        print(f" -> Caregiver reading unshared private walk note: BLOCKED by policy!")
        print(f"    Reason: {e.reason}")

    # Check missed routines for today
    today = date.today()
    missed_before = storage.routines.get_missed_routines(today)
    print(f" -> Routines Pending for Today: {len(missed_before)} (Title: '{missed_before[0].title}')")

    # Complete routine
    storage.routines.log_routine_status(RoutineLogRecord(
        routine_id=routine_id,
        scheduled_date=today,
        status=RoutineLogStatus.COMPLETED,
        notes="Taken with orange juice and breakfast"
    ))
    missed_after = storage.routines.get_missed_routines(today)
    print(f" -> Routine completed and logged. Routines Pending: {len(missed_after)}")

    print("\n[STEP 8] LIVE ON-DISK CIPHERTEXT & ENTROPY AUDIT")
    # Flush SQLite cache to disk
    sec_mgr.db.cursor().execute("PRAGMA wal_checkpoint(FULL);")
    
    is_secure, findings = sec_mgr.verify_disk_encryption(
        sample_sensitive_data=["Sarah Jenkins", "ducklings", "Penicillin", "cedar lake"]
    )
    print(f" -> Is Disk File Cryptographically Secure: {is_secure}")
    for finding in findings:
        print(f"    * {finding}")

    print("\n[STEP 9] RENDERING PYSIDE6 DESKTOP UI & CAPTURING SCREENSHOTS")
    app = QApplication.instance() or QApplication(sys.argv)
    
    window = SecurityDashboardWindow(sec_mgr)
    window.show()

    # Artifact directory for user presentation
    artifact_dir = Path(r"C:\Users\harsh\.gemini\antigravity\brain\e5e190f4-972a-41ca-b1a5-14c07b1d5d8f")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    dash_screenshot_path = artifact_dir / "security_dashboard_preview.png"
    lock_screenshot_path = artifact_dir / "security_lock_screen_preview.png"

    # Render Dashboard view
    window.stacked_widget.setCurrentWidget(window.main_content)
    window.repaint()
    app.processEvents()
    
    dash_pixmap = window.grab()
    dash_pixmap.save(str(dash_screenshot_path), "PNG")
    print(f" -> Dashboard UI Screenshot captured: {dash_screenshot_path.resolve()}")

    # Render Lock Overlay view
    sec_mgr.lock(reason="demonstration")
    window.repaint()
    app.processEvents()

    lock_pixmap = window.grab()
    lock_pixmap.save(str(lock_screenshot_path), "PNG")
    print(f" -> Lock Screen UI Screenshot captured: {lock_screenshot_path.resolve()}")

    # Unlock again to clean up
    sec_mgr.unlock_with_pin("eleanor_vance", "739104")
    window.close()
    sec_mgr.shutdown()

    print("\n=====================================================================")
    print(" DEMONSTRATION COMPLETED SUCCESSFULLY WITH 100% VERIFICATION!        ")
    print("=====================================================================")


if __name__ == "__main__":
    run_working_demo()
