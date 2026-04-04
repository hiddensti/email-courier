#!/usr/bin/env python3
"""Universal IMAP email checker. Works with Gmail, Yahoo, Mail.ru, Outlook, etc."""
import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta
import re
import sys
import os
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_ops

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORDS_FILE = os.path.join(PROJECT_DIR, "passwords.yaml")


def strip_html(text):
    """Remove HTML tags and decode entities to get clean text."""
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&#\d+;', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def load_mailboxes():
    """Load mailbox credentials from passwords.yaml."""
    if not os.path.exists(PASSWORDS_FILE):
        print(f"ERROR: {PASSWORDS_FILE} not found. Copy passwords.example.yaml and fill in your credentials.")
        sys.exit(1)
    with open(PASSWORDS_FILE) as f:
        data = yaml.safe_load(f)
    return data.get("mailboxes", [])


MAILBOXES = load_mailboxes()


def decode_str(s):
    if s is None:
        return ""
    parts = decode_header(s)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result)


def check_mailbox(mb):
    """Check one IMAP mailbox. Returns list of new email dicts."""
    name = mb["name"]
    try:
        mail = imaplib.IMAP4_SSL(mb["server"], mb.get("port", 993))
        mail.login(mb["email"], mb["password"])
        mail.select("INBOX")
    except Exception as e:
        print(f"[{name}] Connection error: {e}")
        return []

    since = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
    status, msg_ids = mail.search(None, f'(SINCE {since})')

    if status != "OK" or not msg_ids[0]:
        print(f"[{name}] No new emails")
        mail.logout()
        return []

    ids = msg_ids[0].split()
    print(f"[{name}] Found {len(ids)} emails since {since}")

    new_emails = []
    for mid in ids[-50:]:
        status, data = mail.fetch(mid, "(RFC822)")
        if status != "OK":
            continue

        msg = email.message_from_bytes(data[0][1])
        message_id = msg.get("Message-ID", f"{name.lower()}-{mid.decode()}")
        sender = decode_str(msg.get("From", ""))
        subject = decode_str(msg.get("Subject", ""))
        date_str = msg.get("Date", "")
        to = decode_str(msg.get("To", ""))

        try:
            received_at = parsedate_to_datetime(date_str).astimezone(timezone.utc).isoformat()
        except:
            received_at = datetime.now(timezone.utc).isoformat()

        snippet = ""
        html_body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    decoded = payload.decode(charset, errors="replace")
                except:
                    continue
                if ct == "text/plain" and not snippet:
                    snippet = decoded[:500]
                elif ct == "text/html" and not html_body:
                    html_body = decoded[:2000]
        else:
            try:
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    html_body = decoded[:2000]
                else:
                    snippet = decoded[:500]
            except:
                pass

        if not snippet and html_body:
            snippet = strip_html(html_body)[:500]

        if db_ops.is_duplicate(name, message_id, sender, subject, received_at):
            continue

        body_full = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        charset = part.get_content_charset() or "utf-8"
                        body_full = payload.decode(charset, errors="replace")[:5000]
                        break
                    except:
                        continue
        else:
            try:
                payload = msg.get_payload(decode=True)
                charset = msg.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    body_full = strip_html(decoded)[:5000]
                else:
                    body_full = decoded[:5000]
            except:
                pass

        new_emails.append({
            "mailbox": name,
            "message_id": message_id,
            "sender": sender,
            "subject": subject,
            "snippet": snippet.strip(),
            "body_plain": body_full.strip(),
            "received_at": received_at,
            "to": to,
        })

    try:
        mail.logout()
    except:
        pass
    return new_emails


def check_all():
    """Check all IMAP mailboxes. Returns combined list of new emails."""
    all_new = []
    for mb in MAILBOXES:
        all_new.extend(check_mailbox(mb))
    return all_new


if __name__ == "__main__":
    emails = check_all()
    if emails:
        for e in emails:
            print(f"  [{e['mailbox']}] [{e['received_at'][:10]}] {e['sender'][:40]} — {e['subject'][:60]}")
    else:
        print("No new emails across all IMAP mailboxes")
