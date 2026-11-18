"""
Example 2: Authentication, Biometric Inspection, and App Locking.
Demonstrates PIN verification, checking Windows Hello hardware availability,
inactivity timeouts, and manual locking.
"""
from pathlib import Path

from local_security.core.configuration import LockConfig, SecurityConfig
from local_security.core.exceptions import InvalidCredentialsError, PINLockedError
from local_security.core.security_manager import SecurityManager


def main():
    print("=== Authentication & Lock Lifecycle Demonstration ===")
    config = SecurityConfig(
        app_data_dir=Path("./example_data"),
        database_filename="auth_example_vault.enc.db",
        key_identifier="AuthExampleVaultKey",
        lock=LockConfig(
            inactivity_timeout_seconds=3,  # Short timeout for demo
            max_failed_attempts=3,
            base_backoff_seconds=1.0,
        ),
    )
    sec_mgr = SecurityManager(config)
    sec_mgr.initialize()

    # Setup user
    if not sec_mgr.auth.is_setup_completed():
        sec_mgr.auth.setup_initial_user(
            username="arthur",
            display_name="Arthur Dent",
            pin="424242",
            confirm_pin="424242",
            enable_biometrics=True,
        )
        print("Configured user profile for Arthur.")

    # 1. Biometric Hardware Detection
    print("\n[1] Checking OS Biometric Availability:")
    bio_avail, bio_code, bio_desc = sec_mgr.auth.biometric_authenticator.is_biometric_available()
    print(f"  • Hardware Supported: {bio_avail}")
    print(f"  • Status Code: {bio_code.value}")
    print(f"  • Details: {bio_desc}")

    # 2. PIN Authentication
    print("\n[2] Authenticating with Correct PIN:")
    session = sec_mgr.unlock_with_pin("arthur", "424242")
    print(f"  • Vault Unlocked: {not sec_mgr.is_locked}")
    print(f"  • Active Session: {session.session_id[:12]}...")

    # 3. Manual Lock
    print("\n[3] Triggering Manual Lock:")
    sec_mgr.lock(reason="user_request")
    print(f"  • Vault Locked: {sec_mgr.is_locked}")

    # 4. Failed Attempt & Rate Limiting Demonstration
    print("\n[4] Simulating Failed PIN Attempts & Rate Limiting:")
    for attempt in range(1, 4):
        try:
            print(f"  • Attempt {attempt}: Entering invalid PIN '000001'...")
            sec_mgr.unlock_with_pin("arthur", "000001")
        except InvalidCredentialsError as e:
            print(f"    -> Rejected: {e}")
        except PINLockedError as e:
            print(f"    -> Rate Limited / Locked: {e} (Retry after: {e.retry_after_seconds:.1f}s)")

    sec_mgr.shutdown()
    print("\nDemo completed.")


if __name__ == "__main__":
    main()
