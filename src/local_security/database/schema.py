"""
Relational Database Schema definition and DDL statements with SQLCipher & FTS5 support.
"""

INITIAL_SCHEMA_VERSION = 1

TABLES_DDL = [
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        applied_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        display_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'owner',
        pin_hash TEXT,
        biometrics_enabled INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        last_authenticated_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS people (
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
    """,
    """
    CREATE TABLE IF NOT EXISTS relationships (
        id TEXT PRIMARY KEY,
        person_a_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
        person_b_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
        relationship_type TEXT NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS places (
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
    """,
    """
    CREATE TABLE IF NOT EXISTS items (
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
    """,
    """
    CREATE TABLE IF NOT EXISTS memories (
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
    """,
    """
    CREATE TABLE IF NOT EXISTS activities (
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
    """,
    """
    CREATE TABLE IF NOT EXISTS routines (
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
    """,
    """
    CREATE TABLE IF NOT EXISTS routine_logs (
        id TEXT PRIMARY KEY,
        routine_id TEXT NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
        scheduled_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'completed',
        notes TEXT,
        logged_at TEXT NOT NULL,
        is_shared_with_caregiver INTEGER NOT NULL DEFAULT 0
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS conversations (
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
    """,
    """
    CREATE TABLE IF NOT EXISTS permissions (
        id TEXT PRIMARY KEY,
        role TEXT NOT NULL,
        module TEXT NOT NULL,
        allowed_actions_json TEXT NOT NULL,
        shareable_only INTEGER NOT NULL DEFAULT 0,
        description TEXT,
        UNIQUE(role, module)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS security_settings (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_events (
        id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        actor_id TEXT,
        module TEXT,
        action TEXT,
        details_json TEXT DEFAULT '{}',
        ip_or_host TEXT DEFAULT 'localhost'
    );
    """,
]

INDEXES_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_people_name ON people(name);",
    "CREATE INDEX IF NOT EXISTS idx_places_name ON places(name);",
    "CREATE INDEX IF NOT EXISTS idx_items_name ON items(name);",
    "CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);",
    "CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);",
    "CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_memories_caregiver ON memories(is_shared_with_caregiver);",
    "CREATE INDEX IF NOT EXISTS idx_activities_started ON activities(started_at);",
    "CREATE INDEX IF NOT EXISTS idx_routines_active ON routines(is_active);",
    "CREATE INDEX IF NOT EXISTS idx_routine_logs_routine ON routine_logs(routine_id, scheduled_date);",
    "CREATE INDEX IF NOT EXISTS idx_conversations_conv_id ON conversations(conversation_id);",
    "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_events(event_type);",
]

FTS5_DDL = [
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
        content_id UNINDEXED,
        title,
        content,
        category,
        tokenize='porter unicode61'
    );
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_memories_ai AFTER INSERT ON memories BEGIN
        INSERT INTO memories_fts(content_id, title, content, category)
        VALUES (new.id, new.title, new.content, new.category);
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_memories_ad AFTER DELETE ON memories BEGIN
        DELETE FROM memories_fts WHERE content_id = old.id;
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_memories_au AFTER UPDATE ON memories BEGIN
        DELETE FROM memories_fts WHERE content_id = old.id;
        INSERT INTO memories_fts(content_id, title, content, category)
        VALUES (new.id, new.title, new.content, new.category);
    END;
    """,
]
