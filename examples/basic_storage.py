"""
Example 1: Basic Storage and FTS5 Full-Text Search.
Demonstrates initializing the secure storage module, saving domain records,
and querying with full-text search.
"""
from pathlib import Path

from local_security.core.configuration import SecurityConfig
from local_security.core.security_manager import SecurityManager
from local_security.models.records import (
    MemoryRecord,
)


def main():
    print("--- 1. Initializing Security Manager ---")
    config = SecurityConfig(
        app_data_dir=Path("./example_data"),
        database_filename="example_vault.enc.db",
        key_identifier="ExampleMemoryVaultKey",
    )
    sec_mgr = SecurityManager(config)
    sec_mgr.initialize()

    print(f"Connected to SQLCipher: {sec_mgr.db.get_cipher_version()}")

    print("\n--- 2. Setting up Owner Account ---")
    if not sec_mgr.auth.is_setup_completed():
        sec_mgr.auth.setup_initial_user(
            username="eleanor",
            display_name="Eleanor Vance",
            pin="948201",
            confirm_pin="948201",
            enable_biometrics=True,
        )
        print("Owner profile and PIN hash created.")

    print("\n--- 3. Unlocking Session ---")
    session = sec_mgr.unlock_with_pin("eleanor", "948201")
    print(f"Authenticated session created for '{session.username}' (Session ID: {session.session_id[:8]}...)")

    print("\n--- 4. Storing Encrypted Memories ---")
    mem_id1 = sec_mgr.storage.memories.save_memory(MemoryRecord(
        title="Walk with Granddaughter Lily",
        content="We went to the botanical garden and Lily loved the yellow sunflowers.",
        category="family",
        importance_level=5,
        tags=["family", "botanical garden", "lily"],
        is_shared_with_caregiver=True,
    ))
    print(f"Saved memory 1: {mem_id1}")

    mem_id2 = sec_mgr.storage.memories.save_memory(MemoryRecord(
        title="Heart Medication Reminder",
        content="Take one tablet of Lisinopril every morning at 8:00 AM with food.",
        category="medical",
        importance_level=5,
        tags=["health", "medication", "heart"],
        is_shared_with_caregiver=True,
    ))
    print(f"Saved memory 2: {mem_id2}")

    print("\n--- 5. Executing FTS5 Full-Text Search ---")
    query = "sunflowers"
    results = sec_mgr.storage.memories.search_memories(query)
    print(f"FTS5 Query for '{query}' found {len(results)} match(es):")
    for r in results:
        print(f"  • [{r.category.upper()}] {r.title}: {r.content}")

    print("\n--- 6. Verifying Disk Ciphertext ---")
    is_secure, findings = sec_mgr.verify_disk_encryption(sample_sensitive_data=["botanical garden", "Lisinopril"])
    print(f"On-Disk Encryption Verified: {is_secure}")
    for f in findings:
        print(f"  • {f}")

    sec_mgr.shutdown()
    print("\nVault safely closed.")


if __name__ == "__main__":
    main()
