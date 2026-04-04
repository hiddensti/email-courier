#!/usr/bin/env python3
"""Initialize SQLite database for Email Courier."""
import sqlite3
import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "db", "email_bot.db")

def init():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mailbox TEXT NOT NULL,
        provider_message_id TEXT NOT NULL,
        thread_id TEXT,
        sender TEXT NOT NULL,
        recipients TEXT,
        subject TEXT,
        snippet TEXT,
        body_plain TEXT,
        content_hash TEXT,
        has_attachments INTEGER DEFAULT 0,
        attachment_types TEXT,
        received_at TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        processing_status TEXT DEFAULT 'new',
        UNIQUE(mailbox, provider_message_id)
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS classifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL REFERENCES messages(id),
        priority TEXT NOT NULL,
        summary_ru TEXT,
        reason TEXT,
        suggested_action TEXT,
        confidence REAL,
        dates_json TEXT,
        amounts_json TEXT,
        classified_at TEXT NOT NULL,
        classified_by TEXT NOT NULL,
        UNIQUE(message_id)
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS deliveries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL REFERENCES messages(id),
        delivery_type TEXT NOT NULL,
        telegram_message_id INTEGER,
        delivered_at TEXT NOT NULL,
        delivery_status TEXT DEFAULT 'sent'
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS sender_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_pattern TEXT NOT NULL,
        subject_pattern TEXT,
        rule_type TEXT NOT NULL,
        created_at TEXT NOT NULL,
        source TEXT DEFAULT 'config'
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS user_preferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER REFERENCES messages(id),
        sender_email TEXT,
        sender_domain TEXT,
        example_subject TEXT,
        example_summary TEXT,
        user_decision TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS bot_state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")

    c.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
        subject, summary_ru, sender, content=''
    )""")

    conn.commit()
    conn.close()
    print(f"Database initialized: {DB_PATH}")

if __name__ == "__main__":
    init()
