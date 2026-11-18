-- memosphere/db/schema.sql
-- SQLite schema for the Circle of Trust module.
-- Run with: sqlite3 memosphere.db < memosphere/db/schema.sql
-- Idempotent: uses IF NOT EXISTS / CREATE TABLE IF NOT EXISTS.

-- Users table – stores trusted contacts and their roles.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trusted contacts table – links a user to a contact with a role.
-- A contact is another trusted person who can receive routine summaries.
CREATE TABLE IF NOT EXISTS trusted_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    contact_name TEXT NOT NULL,
    role TEXT NOT NULL,
    permission_level TEXT NOT NULL DEFAULT 'view',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, contact_name)
);

-- Routines table – the personal routines tracked by the owner.
CREATE TABLE IF NOT EXISTS routines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    frequency TEXT NOT NULL DEFAULT 'daily', -- daily, weekly, monthly
    priority TEXT NOT NULL DEFAULT 'Medium',
    status TEXT NOT NULL DEFAULT 'pending', -- completed, pending, missed
    last_completed DATE,
    due_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Permissions table – granular per‑routine permissions granted to contacts.
CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    routine_id INTEGER NOT NULL,
    contact_id INTEGER NOT NULL,
    permission_level TEXT NOT NULL DEFAULT 'view',
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (routine_id) REFERENCES routines(id) ON DELETE CASCADE,
    FOREIGN KEY (contact_id) REFERENCES trusted_contacts(id) ON DELETE CASCADE,
    UNIQUE (routine_id, contact_id)
);

-- Escalation logs – records when a high‑priority routine goes overdue,
-- preventing duplicate alerts.
CREATE TABLE IF NOT EXISTS escalation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    routine_id INTEGER NOT NULL,
    contact_id INTEGER,
    alerted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    notes TEXT,
    FOREIGN KEY (routine_id) REFERENCES routines(id) ON DELETE CASCADE,
    FOREIGN KEY (contact_id) REFERENCES trusted_contacts(id)
);