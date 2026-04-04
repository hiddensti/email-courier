#!/usr/bin/env python3
"""Database operations for Email Courier."""
import sqlite3
import json
from datetime import datetime, timezone
import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "db", "email_bot.db")

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def is_duplicate(mailbox, provider_message_id, sender=None, subject=None, received_at=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM messages WHERE mailbox=? AND provider_message_id=?",
              (mailbox, provider_message_id))
    if c.fetchone():
        conn.close()
        return True
    if sender and subject and received_at:
        c.execute("""
            SELECT id FROM messages
            WHERE sender=? AND subject=?
            AND abs(julianday(received_at) - julianday(?)) * 24 * 60 < 15
        """, (sender, subject, received_at))
        if c.fetchone():
            conn.close()
            return True
    conn.close()
    return False

def save_message(mailbox, provider_message_id, thread_id, sender, recipients,
                 subject, snippet, received_at, has_attachments=0, body_plain=None):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    try:
        c.execute("""
            INSERT INTO messages (mailbox, provider_message_id, thread_id, sender,
                recipients, subject, snippet, body_plain, received_at, fetched_at, has_attachments)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (mailbox, provider_message_id, thread_id, sender, recipients,
              subject, snippet, body_plain, received_at, now, has_attachments))
        msg_id = c.lastrowid
        conn.commit()
        return msg_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def save_classification(message_id, priority, summary_ru, reason,
                        suggested_action, confidence, classified_by,
                        dates=None, amounts=None):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    try:
        c.execute("""
            INSERT OR REPLACE INTO classifications
            (message_id, priority, summary_ru, reason, suggested_action,
             confidence, dates_json, amounts_json, classified_at, classified_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (message_id, priority, summary_ru, reason, suggested_action,
              confidence, json.dumps(dates or []), json.dumps(amounts or []),
              now, classified_by))
        conn.commit()
        if classified_by == "rules":
            c.execute("""
                INSERT INTO messages_fts(rowid, subject, summary_ru, sender)
                SELECT m.id, m.subject, ?, m.sender FROM messages m WHERE m.id=?
            """, (summary_ru, message_id))
        conn.commit()
    finally:
        conn.close()

def save_delivery(message_id, delivery_type, telegram_message_id):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    c.execute("""
        INSERT INTO deliveries (message_id, delivery_type, telegram_message_id, delivered_at)
        VALUES (?, ?, ?, ?)
    """, (message_id, delivery_type, telegram_message_id, now))
    c.execute("UPDATE messages SET processing_status='delivered' WHERE id=?", (message_id,))
    conn.commit()
    conn.close()

def get_undelivered_for_digest():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT m.id, m.mailbox, m.sender, m.subject, m.snippet,
               c.priority, c.summary_ru, c.reason, c.suggested_action,
               c.dates_json, c.amounts_json
        FROM messages m
        JOIN classifications c ON c.message_id = m.id
        LEFT JOIN deliveries d ON d.message_id = m.id
        WHERE d.id IS NULL
        AND c.priority != 'ignore'
        AND m.processing_status != 'done'
        ORDER BY
            CASE c.priority
                WHEN 'critical' THEN 1
                WHEN 'action_today' THEN 2
                WHEN 'review' THEN 3
            END,
            m.received_at DESC
    """)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_state(key, default=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM bot_state WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row["value"] if row else default

def set_state(key, value):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT OR REPLACE INTO bot_state (key, value, updated_at) VALUES (?, ?, ?)",
              (key, value, now))
    conn.commit()
    conn.close()

def get_sender_rules():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT sender_pattern, subject_pattern, rule_type, source FROM sender_rules")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_sender_rule(sender_pattern, rule_type, subject_pattern=None, source="config"):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    c.execute("DELETE FROM sender_rules WHERE sender_pattern=?", (sender_pattern,))
    c.execute("""
        INSERT INTO sender_rules (sender_pattern, subject_pattern, rule_type, created_at, source)
        VALUES (?, ?, ?, ?, ?)
    """, (sender_pattern, subject_pattern, rule_type, now, source))
    conn.commit()
    conn.close()

def mark_done(message_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE messages SET processing_status='done' WHERE id=?", (message_id,))
    conn.commit()
    conn.close()

def save_user_preference(message_id, sender_email, sender_domain, subject, summary_ru, user_decision):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    c.execute("""
        INSERT INTO user_preferences
        (message_id, sender_email, sender_domain, example_subject, example_summary, user_decision, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (message_id, sender_email, sender_domain, subject, summary_ru, user_decision, now))
    conn.commit()
    conn.close()

def get_user_preferences(sender_domain=None, limit=30):
    conn = get_conn()
    c = conn.cursor()
    if sender_domain:
        c.execute("""
            SELECT sender_email, sender_domain, example_subject, example_summary, user_decision
            FROM user_preferences WHERE sender_domain = ?
            ORDER BY created_at DESC LIMIT ?
        """, (sender_domain, limit))
    else:
        c.execute("""
            SELECT sender_email, sender_domain, example_subject, example_summary, user_decision
            FROM user_preferences ORDER BY created_at DESC LIMIT ?
        """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_stats():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as total FROM messages")
    total = c.fetchone()["total"]
    c.execute("SELECT c.priority, COUNT(*) as cnt FROM classifications c GROUP BY c.priority")
    by_priority = {r["priority"]: r["cnt"] for r in c.fetchall()}
    c.execute("SELECT COUNT(*) as cnt FROM deliveries WHERE DATE(delivered_at)=DATE('now')")
    delivered_today = c.fetchone()["cnt"]
    conn.close()
    return {"total": total, "by_priority": by_priority, "delivered_today": delivered_today}
