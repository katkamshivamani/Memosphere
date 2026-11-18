# API Reference
## Local Privacy & Security Module

---

## 1. `SecurityManager`

The primary orchestrator and entry point for host applications.

```python
from local_security.core.security_manager import SecurityManager
from local_security.core.configuration import SecurityConfig

sec_mgr = SecurityManager(config=None)
```

### Methods

#### `initialize() -> None`
Initializes OS secure key storage, retrieves or generates the 256-bit vault key, connects and verifies the SQLCipher encrypted database, applies pending migrations, and starts the background inactivity monitor.

#### `unlock_with_pin(username_or_id: str, pin: str) -> ActiveSession`
Verifies user PIN against stored Argon2id hash with rate-limiting. On success, unlocks the application, creates an active authenticated session, and returns the session object.

#### `unlock_with_biometrics(username_or_id: str) -> ActiveSession`
Prompts OS biometric verification (Windows Hello / Touch ID). On verification, unlocks the application and returns an active session.

#### `lock(reason: str = "manual") -> None`
Immediately locks the application, destroys the active session token, and notifies registered state listeners.

#### `rotate_encryption_key() -> None`
Generates a new 256-bit key, re-encrypts all database pages atomically via SQLCipher `PRAGMA rekey`, and updates OS secure key storage.

#### `verify_disk_encryption(sample_sensitive_data: list[str] | None = None) -> tuple[bool, list[str]]`
Audits the physical database file on disk, measuring Shannon entropy, verifying absence of SQLite plaintext magic headers, and ensuring forbidden plaintext strings are not present.

#### `shutdown() -> None`
Safely terminates idle monitoring threads, invalidates active sessions, closes the database connection, and clears in-memory keys.

---

## 2. `SecureStorage` (Shared Storage API)

Unified storage interface providing both generic CRUD and dedicated domain repositories.

```python
storage = sec_mgr.storage
```

### Generic Methods

#### `save_record(module: str, record_type: str, data: dict, role: UserRole = UserRole.OWNER) -> str`
Saves a new record into the specified module (`"memories"`, `"people"`, `"places"`, `"items"`, `"routines"`, `"activities"`). Returns the generated record ID.

#### `get_record(module: str, record_id: str, role: UserRole = UserRole.OWNER) -> dict | None`
Retrieves a record by ID, converting to a dictionary representation. Enforces role-based permissions and caregiver sharing rules.

#### `update_record(module: str, record_id: str, data: dict, role: UserRole = UserRole.OWNER) -> dict`
Updates fields of an existing record.

#### `delete_record(module: str, record_id: str, role: UserRole = UserRole.OWNER) -> bool`
Deletes a record by ID.

#### `search_records(module: str, query: str, role: UserRole = UserRole.OWNER) -> list[dict]`
Performs full-text search across module records.

---

## 3. Domain Repositories

### `MemoryRepository` (`storage.memories`)
- `save_memory(memory: MemoryRecord, role=UserRole.OWNER) -> str`: Inserts encrypted memory.
- `get_memory(memory_id: str, role=UserRole.OWNER) -> MemoryRecord | None`: Retrieves memory.
- `search_memories(query: str, category=None, role=UserRole.OWNER, limit=20) -> list[MemoryRecord]`: Full-text search using SQLCipher FTS5 virtual table.
- `update_memory(memory_id: str, updates: dict, role=UserRole.OWNER) -> MemoryRecord`: Updates fields.
- `delete_memory(memory_id: str, role=UserRole.OWNER) -> bool`: Deletes memory and syncs FTS5.
- `get_memories_for_caregiver(limit=50) -> list[MemoryRecord]`: Returns only memories marked `is_shared_with_caregiver=True`.

### `PeopleRepository` (`storage.people`)
- `save_person(person: PersonRecord, role=UserRole.OWNER) -> str`: Saves contact/person.
- `get_person(person_id: str, role=UserRole.OWNER) -> PersonRecord | None`: Retrieves person.
- `search_people(query: str, role=UserRole.OWNER, limit=20) -> list[PersonRecord]`: Searches people.
- `save_relationship(rel: RelationshipRecord, role=UserRole.OWNER) -> str`: Records interpersonal relationship.
- `get_relationships(person_id: str, role=UserRole.OWNER) -> list[RelationshipRecord]`: Retrieves relationships.

### `RoutineRepository` (`storage.routines`)
- `save_routine(routine: RoutineRecord, role=UserRole.OWNER) -> str`: Saves routine or habit.
- `get_routine(routine_id: str, role=UserRole.OWNER) -> RoutineRecord | None`: Retrieves routine.
- `update_routine(routine_id: str, updates: dict, role=UserRole.OWNER) -> RoutineRecord`: Updates routine.
- `delete_routine(routine_id: str, role=UserRole.OWNER) -> bool`: Deletes routine.
- `log_routine_status(log: RoutineLogRecord, role=UserRole.OWNER) -> str`: Logs completion/missed status.
- `get_routine_logs(routine_id: str, role=UserRole.OWNER, limit=30) -> list[RoutineLogRecord]`: History logs.
- `get_missed_routines(for_date: date, role=UserRole.OWNER) -> list[RoutineRecord]`: Identifies active routines lacking a completion log for `for_date`.
- `get_routines_for_caregiver() -> list[RoutineRecord]`: Returns routines shared with caregivers.

### `ActivityRepository` (`storage.activities`)
- `save_activity(activity: ActivityRecord, role=UserRole.OWNER) -> str`: Logs an activity.
- `get_activity_history(limit=50, role=UserRole.OWNER, category=None) -> list[ActivityRecord]`: Activity log.
- `get_weekly_consistency_summary(role=UserRole.OWNER) -> dict`: Returns 7-day adherence metrics and category breakdown.

---

## 4. `PermissionManager`

```python
from local_security.access_control.permission_manager import PermissionManager
from local_security.models.permissions import SecurityModule, SecurityAction
from local_security.models.users import UserRole

perms = PermissionManager()
perms.check_access(
    module=SecurityModule.ROUTINES,
    action=SecurityAction.READ,
    role=UserRole.CAREGIVER,
    is_shared_with_caregiver=True,
)
```

Raises `PermissionDeniedError` if access is unauthorized.

---

## 5. Core Exceptions Hierarchy

```text
SecurityError
 ├── ConfigurationError
 ├── AuthenticationError
 │    ├── InvalidCredentialsError
 │    ├── PINLockedError (has retry_after_seconds)
 │    ├── HardwareUnavailableError
 │    └── BiometricVerificationFailedError
 ├── KeyManagementError
 │    └── KeyNotFoundError
 ├── DatabaseError
 │    ├── DecryptionError
 │    ├── SchemaMigrationError
 │    └── RecordNotFoundError
 ├── SessionError
 │    └── SessionExpiredError
 ├── ApplicationLockedError
 └── PermissionDeniedError (has module, action, reason)
```
