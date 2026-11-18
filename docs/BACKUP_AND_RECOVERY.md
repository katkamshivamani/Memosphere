# Backup, Disaster Recovery & Key Rotation Strategy
## Local Privacy & Security Module

---

## 1. Overview

Because the personal memory companion stores sensitive life history, medical routines, and personal reflections exclusively on the user's local computer, a robust backup and recovery strategy is essential.

This document details:
1. Master Key Recovery Packages (AES-256-GCM + Argon2id).
2. Key Rotation via SQLCipher `PRAGMA rekey`.
3. Encrypted Database File Backups.
4. Disaster Recovery Procedure (OS reinstall, new device).

---

## 2. Master Key Recovery Package

The master encryption key is generated using 256 bits of cryptographic randomness (`secrets.token_bytes(32)`) and protected by the operating system's secure key storage (DPAPI on Windows, Keychain on macOS, Secret Service on Linux).

If a user re-installs their operating system or moves to a new computer, the OS-specific key storage from the old installation is no longer accessible. To prevent permanent loss of memories, users can export an **Encrypted Recovery Package**.

### Cryptographic Format of Recovery Package
The exported file (`*.enc.key`) is encrypted using **AES-256-GCM** derived from an emergency passphrase chosen by the user:

```text
+-----------------------+-----------------------+----------------------------------+
| Salt (16 bytes)       | Nonce (12 bytes)      | Ciphertext + Auth Tag (48 bytes) |
| Generated via CSPRNG  | Generated via CSPRNG  | AES-256-GCM with AAD string      |
+-----------------------+-----------------------+----------------------------------+
```

1. **Key Derivation**: Argon2id (3 iterations, 64MB memory, 4 lanes, 16-byte random salt).
2. **Authenticated Encryption**: AES-GCM (12-byte random nonce, 16-byte authentication tag).
3. **Associated Authenticated Data (AAD)**: `b"MEMORY_COMPANION_RECOVERY_V1"`.

### Exporting via Code
```python
from local_security.core.security_manager import SecurityManager

sec_mgr = SecurityManager()
sec_mgr.initialize()

vault_key = sec_mgr.key_manager.retrieve_vault_key(sec_mgr.config.key_identifier)
recovery_blob = sec_mgr.key_manager.export_recovery_package(vault_key, "MySuperSecretPassphrase2026!")

# Save to USB drive or secure offline location
with open("memory_vault_recovery.enc.key", "wb") as f:
    f.write(recovery_blob)
```

### Restoring via Code
```python
with open("memory_vault_recovery.enc.key", "rb") as f:
    recovery_blob = f.read()

restored_key = sec_mgr.key_manager.import_recovery_package(recovery_blob, "MySuperSecretPassphrase2026!")

# Re-inject key into local OS secure storage
sec_mgr.key_storage.store_key(sec_mgr.config.key_identifier, restored_key)
```

---

## 3. Database Key Rotation

Cryptographic best practices recommend periodic key rotation or immediate rotation if compromise is suspected.

SQLCipher provides atomic in-place page re-encryption via `PRAGMA rekey`.

### Rotation Workflow
1. Verify user is authenticated with active session.
2. Generate new 256-bit CSPRNG key.
3. Call `db_manager.rekey(new_key)` inside active connection:
   - SQLCipher decrypts every database page using the old key and re-encrypts it with the new key in a single atomic transaction.
   - If the transaction is interrupted (e.g. power failure), SQLite rollback journal preserves the old key without file corruption.
4. Once `PRAGMA rekey` succeeds, update the OS secure key storage (DPAPI/Keychain) with the new key.
5. Record a `KEY_ROTATED` event in the audit log.

### Code Example
```python
sec_mgr.rotate_encryption_key()
print("Database pages re-encrypted and OS key storage updated.")
```

---

## 4. Disaster Recovery Scenarios

| Scenario | Impact | Recovery Action |
| :--- | :--- | :--- |
| **Forgotten PIN** | User cannot authenticate through UI | If OS user account is active, use Master Recovery Passphrase to reset PIN via `auth_manager.change_pin()` or re-initialize user profile. |
| **OS Account Reset / Reinstall** | OS key storage (DPAPI/Keychain) is wiped | Place the encrypted database file in the data folder, import the exported recovery package with the emergency passphrase, and re-bind to the new OS user account. |
| **New Computer Hardware** | New PC, fresh installation | Copy `memory_vault.enc.db` and the exported `*.enc.key` to the new PC. Run import workflow to decrypt the master key and bind to the new PC's DPAPI/Keychain. |
| **Ciphertext Tampering / Bad Sector** | SQLCipher HMAC verification fails | SQLCipher rejects corrupted pages with `DecryptionError`. Restore latest local encrypted backup file. |
