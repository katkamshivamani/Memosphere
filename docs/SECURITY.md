# Security Policy & Cryptographic Specifications
## Local-First Privacy & Security Module

---

## 1. Cryptographic Specifications

This module enforces industry-standard cryptographic algorithms. Custom cryptographic implementations are strictly forbidden.

| Component | Standard / Algorithm | Parameters / Configuration |
| :--- | :--- | :--- |
| **Database Encryption** | SQLCipher AES-256-CBC | Page size: 4096 bytes<br>KDF: PBKDF2_HMAC_SHA512 (256,000 iterations)<br>HMAC: HMAC-SHA512 per page |
| **PIN Hashing & Verification** | Argon2id (`argon2-cffi`) | Iterations (time_cost): 3<br>Memory (memory_cost): 65,536 KiB (64 MiB)<br>Parallelism: 4 threads<br>Salt length: 16 bytes CSPRNG<br>Hash length: 32 bytes |
| **Key Generation** | CSPRNG | `secrets.token_bytes(32)` (256-bit entropy) |
| **Recovery Package** | AES-256-GCM (`cryptography`) | Key Derivation: Argon2id (salt=16 bytes, memory=64MB, time=3)<br>Nonce: 12 bytes CSPRNG<br>Auth Tag: 16 bytes GCM |
| **Windows Key Storage** | Windows DPAPI | `CryptProtectData` user-scoped with `CRYPTPROTECT_UI_FORBIDDEN` |
| **Linux Key Storage** | Secret Service / POSIX 0600 | Mode 0700 keystore directory, Mode 0600 keyfile (owner-only) |
| **macOS Key Storage** | macOS Keychain | `security add-generic-password` user keychain |

---

## 2. Authentication Gates vs. OS Key Protection

### Operating System Key Storage (DPAPI / Keychain / Secret Service)
- **Role**: Protects the 256-bit database master encryption key at rest when written to disk.
- **Guarantee**: The key material is encrypted by the OS using cryptographic credentials tied to the current OS login account. Other local user accounts or unauthenticated disk mounts cannot decrypt the file.
- **Important Security Distinction**: Storing a key in DPAPI or Keychain does *not* automatically enforce biometric or PIN verification before every access. The application's **Authentication Gate (`AuthenticationManager`)** enforces mandatory PIN or biometric verification before the application window is unlocked and sensitive domain records are released.

### What Happens If the OS Account Is Compromised?
- If an attacker gains full administrative access to an unlocked Windows/macOS/Linux user session, they could execute processes that invoke DPAPI or Keychain APIs under that user context.
- **Defense in Depth**:
  1. The vault master key is never written in plaintext configuration files.
  2. The application automatically locks when minimized, when focus is lost (if configured), or after 5 minutes of inactivity.
  3. When locked, in-memory session tokens are destroyed, and sensitive PySide6 controls are cleared and covered by an overlay.
  4. Database closure can be triggered on lock to require fresh master key release.

---

## 3. Offline-First Privacy Principles

1. **Local-Only Persistence**: All personal information, memories, routines, and audio/text interactions remain exclusively on the user's computer.
2. **Zero Telemetry**: No tracking, analytics, diagnostic crash uploads, remote logging, or silent cloud synchronization.
3. **No Network Sockets**: The security and storage module makes zero network connections. Unit test `test_offline_operation_zero_network_traffic` verifies that all operations succeed when all network sockets are blocked.
4. **External AI API Isolation**: If conversational companion features utilize an external LLM API, that integration is independent of this module and must never bypass access control or transmit raw encrypted vault contents.

---

## 4. Rate Limiting and Brute Force Defense

- PIN attempts are tracked per user profile.
- After **5 consecutive failed attempts**, the account enters exponential backoff:
  $$\text{Delay} = \min(2.0 \times 2^{(\text{failures} - 5)},\, 60.0)\text{ seconds}$$
- During the lockout duration, all verification calls are rejected with `PINLockedError` indicating the remaining wait time.
- Successful verification resets the failure counter to zero.

---

## 5. Security Audit Logging

All security-sensitive operations are recorded into the encrypted `audit_events` table inside the SQLCipher database:
- `AUTH_SUCCESS` / `AUTH_FAILURE`
- `BIOMETRIC_SUCCESS` / `BIOMETRIC_FAILURE`
- `PIN_CHANGED`
- `APP_LOCKED` / `APP_UNLOCKED`
- `KEY_ROTATED`
- `PERMISSION_DENIED`
- `DATABASE_BACKUP`

Audit events contain UTC timestamps, actor IDs, module names, and action details without ever logging plaintext passwords, PINs, or raw encryption keys.
