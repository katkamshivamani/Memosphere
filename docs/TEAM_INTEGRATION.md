# Team Integration Guide
## Connecting Companion Modules to Local-First Privacy & Security

---

## 1. Introduction for Peer Developers

You are building one of the core features of the AI-powered Personal Memory Companion:
- **Module A: Universal Personal Knowledge Base**
- **Module B: Conversational AI Companion**
- **Module C: Permission-Based Monitoring Dashboard**

**Good news**: You do **not** need to know SQLCipher internals, manage encryption keys, interface with Windows Hello / DPAPI / Keychain, or implement password hashing.

The `SecureStorage` and `SecurityManager` interfaces handle 100% of the cryptographic lifecycle, storage encryption, and access control behind clean, typed Python APIs.

---

## 2. Basic Setup & Storage Access

To access the encrypted vault, import `SecurityManager`:

```python
from local_security.core.security_manager import SecurityManager

# Access the initialized security manager from the app container
sec_mgr = SecurityManager()
sec_mgr.initialize()

# The unified storage interface
storage = sec_mgr.storage
```

---

## 3. Module A: Universal Personal Knowledge Base

### Storing People & Contacts
```python
from local_security.models.records import PersonRecord

person_id = storage.people.save_person(PersonRecord(
    name="Sarah Jenkins",
    nickname="Aunt Sarah",
    relationship_to_user="Sister",
    phone="555-0199",
    notes="Loves gardening and strawberry tea."
))

# Retrieve person by ID
sarah = storage.people.get_person(person_id)
print(f"Contact: {sarah.name} ({sarah.relationship_to_user})")

# Search contacts
matches = storage.people.search_people("Sarah")
```

### Storing Memories with FTS5 Indexing
```python
from local_security.models.records import MemoryRecord

mem_id = storage.memories.save_memory(MemoryRecord(
    title="Summer Picnic at Lake Washington",
    content="Sarah and I rented a paddleboat and ate peach pie on the grassy pier.",
    category="family",
    importance_level=4,
    tags=["summer", "picnic", "lake"],
    is_shared_with_caregiver=True,  # Set to True if caregiver can view
))

# Fast full-text search across all encrypted memories
results = storage.memories.search_memories("paddleboat")
for mem in results:
    print(f"Found memory: {mem.title}")
```

### Storing Places and Items
```python
# Save an item location
item_id = storage.save_record(
    module="items",
    record_type="item",
    data={
        "name": "House Keys",
        "usual_location": "Small brass hook near the front door",
        "current_location": "Small brass hook near the front door",
        "category": "keys"
    }
)
```

---

## 4. Module B: Conversational AI Companion

### Retrieving Memory Context for User Questions
When the user speaks or types a natural-language question, search the local encrypted knowledge base before passing prompt context to your local LLM:

```python
def answer_user_memory_question(user_question: str) -> str:
    # 1. Search local memories via FTS5
    relevant_memories = storage.memories.search_memories(user_question, limit=3)
    
    context_chunks = [m.content for m in relevant_memories]
    local_context = "\n".join(context_chunks)
    
    # 2. Provide context to your dialogue model locally
    # Note: Personal memories stay on-device.
    response = generate_local_response(user_question, context=local_context)
    return response
```

### Storing Dialogue History
```python
with sec_mgr.db.transaction() as tx:
    tx.execute(
        """
        INSERT INTO conversations (id, conversation_id, sender, message_text, created_at)
        VALUES (?, ?, ?, ?, ?);
        """,
        (str(uuid.uuid4()), session_id, "user", user_question, datetime.now(timezone.utc).isoformat())
    )
```

---

## 5. Module C: Monitoring & Caregiver Dashboard

### Checking Missed Routines
```python
from datetime import date
from local_security.models.users import UserRole

# Retrieve routines that have NOT been completed today
missed_routines = storage.routines.get_missed_routines(date.today())
for routine in missed_routines:
    print(f"Alert: '{routine.title}' scheduled for {routine.time_of_day} has not been completed!")
```

### Logging Routine Completion
```python
from local_security.models.records import RoutineLogRecord, RoutineLogStatus

storage.routines.log_routine_status(RoutineLogRecord(
    routine_id="routine-uuid",
    scheduled_date=date.today(),
    status=RoutineLogStatus.COMPLETED,
    notes="Taken with breakfast"
))
```

### Caregiver Selective Access Rules
When requesting records on behalf of a caregiver, pass `role=UserRole.CAREGIVER`:

```python
from local_security.models.users import UserRole
from local_security.core.exceptions import PermissionDeniedError

try:
    # Only records marked is_shared_with_caregiver=True are returned
    shared_memories = storage.memories.get_memories_for_caregiver()
    
    # Attempting to fetch a private unshared record raises an explicit exception:
    private_record = storage.memories.get_memory("private-mem-id", role=UserRole.CAREGIVER)
except PermissionDeniedError as e:
    print(f"Blocked by Security Policy: {e.reason}")
```

### Generating 7-Day Consistency Summary
```python
summary = storage.activities.get_weekly_consistency_summary()
print(f"Adherence Score: {summary['consistency_score_percentage']}%")
print(f"Active Days: {summary['days_with_activity']} / 7")
```

---

## 6. Error Handling Best Practices

Always catch domain security exceptions defined in `local_security.core.exceptions`:

| Exception | Cause | Recommended Action |
| :--- | :--- | :--- |
| `PermissionDeniedError` | Actor lacks permissions or record is unshared | Notify user or suppress unauthorized UI controls |
| `SessionExpiredError` | Inactivity timer expired | Prompt user with the lock screen auth dialog |
| `ApplicationLockedError` | Operation attempted while application is locked | Direct user to unlock with PIN or Biometrics |
| `RecordNotFoundError` | Invalid ID supplied | Handle 404/missing entity gracefully |
