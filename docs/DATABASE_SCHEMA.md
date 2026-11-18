# Database Schema & Data Dictionary
## SQLCipher Encrypted Relational Database Architecture

---

## 1. Overview

The database is built on **SQLCipher 4.12.0** utilizing a strict relational schema with foreign key enforcement (`PRAGMA foreign_keys = ON;`), indexes for frequent queries, UTC ISO-8601 timestamps, and FTS5 full-text search indexing for conversational memory retrieval.

---

## 2. Table Specifications

### `users`
Stores user identity, roles, and salted Argon2id PIN hashes.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `TEXT` | `PRIMARY KEY` | UUIDv4 identifier |
| `username` | `TEXT` | `UNIQUE NOT NULL` | Unique account name |
| `display_name` | `TEXT` | `NOT NULL` | Human-readable user name |
| `role` | `TEXT` | `NOT NULL DEFAULT 'owner'` | `owner`, `caregiver`, `accountability_partner`, `guest` |
| `pin_hash` | `TEXT` | `NULLABLE` | Salted Argon2id hash string |
| `biometrics_enabled`| `INTEGER`| `NOT NULL DEFAULT 0` | 1 if OS biometrics opted-in |
| `created_at` | `TEXT` | `NOT NULL` | ISO-8601 UTC timestamp |
| `updated_at` | `TEXT` | `NOT NULL` | ISO-8601 UTC timestamp |
| `last_authenticated_at` | `TEXT` | `NULLABLE` | Timestamp of last successful unlock |

---

### `people` & `relationships`
Stores memory companion contacts, relatives, caregivers, and their relational links.

```sql
CREATE TABLE people (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    nickname TEXT,
    relationship_to_user TEXT,
    phone TEXT,
    email TEXT,
    notes TEXT,
    avatar_path TEXT,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE relationships (
    id TEXT PRIMARY KEY,
    person_a_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    person_b_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL
);
```

---

### `places` & `items`
Stores spatial information and item finder locations.

```sql
CREATE TABLE places (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT,
    category TEXT,
    description TEXT,
    latitude REAL,
    longitude REAL,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE items (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    usual_location TEXT,
    current_location TEXT,
    category TEXT,
    description TEXT,
    image_path TEXT,
    last_seen_at TEXT,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

---

### `memories` & `memories_fts` (FTS5)
Core repository of personal experiences, reflections, and medical preferences with full-text indexing.

```sql
CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    importance_level INTEGER NOT NULL DEFAULT 1,
    tags_json TEXT DEFAULT '[]',
    people_mentioned_json TEXT DEFAULT '[]',
    places_mentioned_json TEXT DEFAULT '[]',
    is_shared_with_caregiver INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- FTS5 Virtual Table for Fast Content Matching
CREATE VIRTUAL TABLE memories_fts USING fts5(
    content_id UNINDEXED,
    title,
    content,
    category,
    tokenize='porter unicode61'
);

-- Triggers to maintain sync automatically
CREATE TRIGGER trg_memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(content_id, title, content, category)
    VALUES (new.id, new.title, new.content, new.category);
END;

CREATE TRIGGER trg_memories_ad AFTER DELETE ON memories BEGIN
    DELETE FROM memories_fts WHERE content_id = old.id;
END;

CREATE TRIGGER trg_memories_au AFTER UPDATE ON memories BEGIN
    DELETE FROM memories_fts WHERE content_id = old.id;
    INSERT INTO memories_fts(content_id, title, content, category)
    VALUES (new.id, new.title, new.content, new.category);
END;
```

---

### `routines` & `routine_logs`
Habit tracking, medication routines, and caregiver monitoring.

```sql
CREATE TABLE routines (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    frequency TEXT NOT NULL DEFAULT 'daily',
    time_of_day TEXT,
    is_shared_with_caregiver INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE routine_logs (
    id TEXT PRIMARY KEY,
    routine_id TEXT NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
    scheduled_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    notes TEXT,
    logged_at TEXT NOT NULL,
    is_shared_with_caregiver INTEGER NOT NULL DEFAULT 0
);
```

---

### `activities`
Logs daily events, walks, meals, and social visits.

```sql
CREATE TABLE activities (
    id TEXT PRIMARY KEY,
    activity_name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'daily',
    started_at TEXT NOT NULL,
    ended_at TEXT,
    notes TEXT,
    is_shared_with_caregiver INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
```

---

### `conversations`
Local encrypted history of dialogues between user and companion AI.

```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    sender TEXT NOT NULL,
    message_text TEXT NOT NULL,
    confidence_score REAL,
    sentiment TEXT,
    intent TEXT,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
```

---

### `audit_events`
Immutable security and access audit log.

```sql
CREATE TABLE audit_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    actor_id TEXT,
    module TEXT,
    action TEXT,
    details_json TEXT DEFAULT '{}',
    ip_or_host TEXT DEFAULT 'localhost'
);
```
