# Architecture Design Document
## Local-First Privacy & Security Module for AI Personal Memory Companion

---

## 1. Executive Summary

The **Local Privacy & Security Module** provides the encrypted storage, operating-system-backed cryptographic key protection, multi-factor user authentication, session security, and access control for the AI-powered Personal Memory Companion application.

The module is architected around **local-first privacy**:
- 100% of sensitive memories, contacts, places, routines, activities, and AI conversations reside on the user's local disk.
- Zero telemetry, zero analytics, zero cloud databases, and zero unprompted outbound network sockets.
- The cryptographic foundation is transparently usable by other companion modules via high-level, typed Python domain repositories.

---

## 2. Layered Architecture

```mermaid
graph TD
    subgraph Layer 1: Desktop User Interface
        UI_Dash["Security Dashboard Window"]
        UI_Lock["Lock Screen Overlay"]
        UI_Setup["Setup & Onboarding Dialog"]
        UI_Auth["PIN & Biometric Auth Dialog"]
    end

    subgraph Layer 2: Core Security Facade
        SecMgr["SecurityManager"]
        AuthMgr["AuthenticationManager"]
        LockMgr["ApplicationLockManager"]
        SessMgr["SessionManager"]
        PermMgr["PermissionManager"]
    end

    subgraph Layer 3: Storage & Cryptography
        SecStorage["SecureStorage Facade"]
        Repo_Mem["MemoryRepository (FTS5)"]
        Repo_Peo["PeopleRepository"]
        Repo_Rout["RoutineRepository"]
        Repo_Act["ActivityRepository"]
        KeyMgr["KeyManager (CSPRNG & Rotation)"]
        EncMgr["EncryptionManager (Entropy Audit)"]
        DBMgr["DatabaseManager (SQLCipher 4.12)"]
    end

    subgraph Layer 4: Platform Adapters
        Factory["PlatformFactory (DI Registry)"]
        Win_Adapters["Windows Adapter (DPAPI + Windows Hello)"]
        Lin_Adapters["Linux Adapter (Secret Service + fprintd)"]
        Mac_Adapters["macOS Adapter (Keychain + Touch ID)"]
    end

    Layer 1 --> Layer 2
    Layer 2 --> Layer 3
    Layer 3 --> Layer 4
```

### Layer 1: Desktop User Interface (PySide6)
- **Welcome / Setup Dialog**: First-time user onboarding, name, PIN creation & confirmation, biometrics opt-in.
- **Authentication Dialog**: Masked PIN input, large touch-friendly buttons, Windows Hello prompt button, rate-limit countdown.
- **Lock Overlay Widget**: Completely obscures all background application windows and controls until freshly authenticated.
- **Security Dashboard**: Live cipher version, database size, key storage backend, auto-lock controls, audit log table, and live disk encryption verification.

### Layer 2: Core Security Facade
- **`SecurityManager`**: Single orchestrator that initializes platform keys, opens the encrypted database, manages session states, and handles application shutdown.
- **`AuthenticationManager`**: Enforces Argon2id salted PIN verification, biometric delegation, and writes immutable audit logs.
- **`ApplicationLockManager`**: Tracks user activity, enforces inactivity timeouts, reacts to window minimize/focus loss, and invalidates sessions.
- **`PermissionManager`**: Central authorization engine verifying role-based permissions (`owner`, `caregiver`, `accountability_partner`, `guest`) and selective sharing constraints.

### Layer 3: Database & Cryptography
- **`DatabaseManager`**: Wraps SQLCipher 4.12 connection lifecycle, configuring 4096-byte pages, 256,000 PBKDF2 iterations, HMAC-SHA512 integrity checks, and foreign keys.
- **`KeyManager`**: Generates 256-bit CSPRNG keys, retrieves keys from OS secure storage, executes atomic database re-keying (`PRAGMA rekey`), and exports AES-256-GCM recovery packages.
- **`SecureStorage` & Domain Repositories**: Clean typed interfaces for Memories, People, Routines, and Activities with SQLite FTS5 full-text search.

### Layer 4: Cross-Platform Adapters
- Decouples core logic from OS binaries using abstract interfaces (`BiometricProvider`, `SecureKeyStorage`).
- **Windows**: Windows DPAPI (`crypt32.dll`) + Windows Hello WinRT (`UserConsentVerifier`).
- **Linux**: Secret Service / mode 0600 file + fprintd PAM.
- **macOS**: macOS Keychain (`security`) + Touch ID (`LocalAuthentication`).

---

## 3. Threat Modeling & Security Boundaries

| Threat / Attacker Vector | Mitigation Strategy |
| :--- | :--- |
| **Physical Theft of Laptop / Disk** | SQLCipher AES-256 database encryption with high Shannon entropy (7.999/8.000). Plaintext records are completely invisible in raw binary disk storage. |
| **Direct SQLite File Inspection** | Plaintext SQLite magic header (`SQLite format 3`) is absent. Unencrypted SQLite tools reject the file as corrupted or non-database. |
| **Ciphertext Tampering / Bit Flipping** | SQLCipher per-page HMAC-SHA512 integrity verification. Any modified byte fails page decryption immediately. |
| **Brute Force PIN Attacks** | Salting with Argon2id (OWASP parameters: 64MB memory cost, 3 iterations). Exponential backoff and account lockout after repeated failures. |
| **Memory Dump / Shoulder Surfing** | PIN plaintext is never stored or logged. Application lock immediately covers all screens and clears active session tokens. |
| **Caregiver Overreach** | Strict selective sharing: Caregivers can only view records explicitly flagged with `is_shared_with_caregiver=True`. |
| **Hardware Biometric Spoofing** | Delegates 100% to OS biometric subsystems (Windows Hello / Touch ID). No fingerprint images or templates are ever collected, read, or stored by this package. |

---

## 4. Key Lifecycle Flow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant App as Application UI
    participant SecMgr as SecurityManager
    participant KeyStorage as OS Secure Storage (DPAPI/Keychain)
    participant DBMgr as DatabaseManager (SQLCipher)

    User->>App: Launch Application
    App->>SecMgr: initialize()
    SecMgr->>KeyStorage: retrieve_key("VaultKey")
    alt First Time Launch
        KeyStorage-->>SecMgr: None
        SecMgr->>SecMgr: Generate 256-bit CSPRNG Key
        SecMgr->>KeyStorage: store_key("VaultKey", key)
    else Subsequent Launch
        KeyStorage-->>SecMgr: 256-bit Master Key
    end
    SecMgr->>DBMgr: connect(key)
    DBMgr->>DBMgr: PRAGMA key = "x'...'"; PRAGMA cipher_page_size=4096;
    DBMgr->>DBMgr: SELECT count(*) FROM sqlite_master;
    DBMgr-->>SecMgr: Database Decrypted & Verified
    SecMgr-->>App: Ready (State: LOCKED)
    App->>User: Display Authentication Screen
```
