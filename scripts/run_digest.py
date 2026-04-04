#!/usr/bin/env python3
"""Digest script — gathers undelivered emails and sends formatted digest to Telegram."""
import sys
import os
from html import escape
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_ops
import telegram


def format_sender(sender):
    if "<" in sender:
        return sender.split("<")[0].strip().strip('"')
    return sender.split("@")[0] if "@" in sender else sender


def main():
    emails = db_ops.get_undelivered_for_digest()
    if not emails:
        print("No new emails for digest")
        return

    critical = [e for e in emails if e["priority"] == "critical"]
    action = [e for e in emails if e["priority"] == "action_today"]
    review = [e for e in emails if e["priority"] == "review"]

    conn = db_ops.get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*) as cnt FROM classifications c
        LEFT JOIN deliveries d ON d.message_id = c.message_id
        WHERE d.id IS NULL AND c.priority = 'ignore'
    """)
    ignore_count = c.fetchone()["cnt"]
    conn.close()

    total = len(emails)
    now = datetime.now().strftime("%H:%M")
    lines = [f"📬 <b>Digest {now} ({total} new)</b>"]

    if critical:
        lines.append(f"\n🔴 <b>Critical ({len(critical)})</b>")
        for e in critical:
            s = escape(format_sender(e["sender"]))
            subj = escape(e["summary_ru"] or e["subject"])
            lines.append(f"• <b>[{e['mailbox']}]</b> {s} — {subj}")

    if action:
        lines.append(f"\n⚡ <b>Action Today ({len(action)})</b>")
        for e in action:
            s = escape(format_sender(e["sender"]))
            subj = escape(e["summary_ru"] or e["subject"])
            lines.append(f"• <b>[{e['mailbox']}]</b> {s} — {subj}")

    if review:
        lines.append(f"\n📋 <b>Review ({len(review)})</b>")
        for i, e in enumerate(review[:10]):
            s = escape(format_sender(e["sender"]))
            subj = escape(e["summary_ru"] or e["subject"])
            lines.append(f"• <b>[{e['mailbox']}]</b> {s} — {subj}")
        if len(review) > 10:
            lines.append(f"  ... +{len(review) - 10} more")

    if ignore_count:
        lines.append(f"\n🗑 Filtered: {ignore_count}")

    text = "\n".join(lines)
    tg_msg_id = telegram.send(text)
    if tg_msg_id:
        for e in emails:
            db_ops.save_delivery(e["id"], "digest", tg_msg_id)
        print(f"Digest sent! {total} emails")
    else:
        print("Failed to send digest")


if __name__ == "__main__":
    main()
