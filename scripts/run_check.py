#!/usr/bin/env python3
"""
Email check script.
Fetches all IMAP mailboxes, applies rules, classifies with AI, sends Telegram alerts.
"""
import sys
import os
import re
import json
import yaml
import subprocess
from datetime import datetime, timezone
from html import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_ops
import telegram
from check_imap import check_all

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_DIR, "config.yaml")
CLAUDE_CLI = os.path.expanduser("~/.local/bin/claude")


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def is_quiet_hours(config):
    try:
        from zoneinfo import ZoneInfo
        tz = config.get("quiet_hours", {})
        timezone_str = config.get("digest", {}).get("timezone", "UTC")
        now = datetime.now(ZoneInfo(timezone_str))
        start = tz.get("start", 22)
        end = tz.get("end", 6)
        return now.hour >= start or now.hour < end
    except Exception:
        return False


def extract_domain(sender):
    match = re.search(r'@([\w.-]+)', sender)
    return match.group(1).lower() if match else ""


def extract_email(sender):
    match = re.search(r'<([^>]+)>', sender)
    return match.group(1).lower() if match else sender.lower()


def classify_by_rules(sender, subject, snippet, config):
    filters = config.get("filters", {})
    domain = extract_domain(sender)
    email_addr = extract_email(sender)
    text = f"{subject} {snippet}".lower()

    for d in filters.get("hard_skip_domains", []):
        if domain.endswith(d):
            return ("ignore", f"Hard-skipped domain: {d}", "rules")

    for s in filters.get("hard_skip_senders", []):
        if s.lower() in email_addr:
            return ("ignore", f"Hard-skipped sender: {s}", "rules")

    for v in filters.get("vip_senders", []):
        if v.lower() in email_addr or v.lower() in domain:
            return ("critical", f"VIP sender: {v}", "rules")

    db_rules = db_ops.get_sender_rules()
    for rule in db_rules:
        pattern = rule["sender_pattern"].lower()
        if pattern in email_addr or pattern in domain:
            return (rule["rule_type"], f"User rule: {pattern}", "rules")

    for rule in filters.get("sender_rules", []):
        if rule["sender"].lower() in email_addr or rule["sender"].lower() in domain:
            return (rule["action"], f"Sender rule: {rule['sender']}", "rules")

    for d in filters.get("never_skip_domains", []):
        if domain.endswith(d):
            for kw in ["urgent", "action required", "overdue", "deadline",
                        "payment due", "security alert", "emergency"]:
                if kw in text:
                    return ("critical", f"Never-skip domain {d} + urgent keyword '{kw}'", "rules")
            return ("review", f"Never-skip domain {d} — needs AI classification", "rules")

    for kw in filters.get("never_skip_keywords", []):
        if kw.lower() in text:
            return ("action_today", f"Never-skip keyword: {kw}", "rules")

    urgent_keywords = ["urgent", "emergency", "asap", "critical", "action required"]
    for kw in urgent_keywords:
        if kw in text:
            return ("action_today", f"Urgent keyword: {kw}", "rules")

    security_keywords = ["password reset", "new sign-in", "new device",
                         "security alert", "verify your"]
    for kw in security_keywords:
        if kw in text:
            return ("action_today", f"Security keyword: {kw}", "rules")

    return ("review", "No specific rules matched — default to review", "rules")


def classify_with_ai(msg_id, sender, subject, snippet, mailbox_name, config):
    context_hint = ""
    for mb in config.get("mailboxes", []):
        if mb["name"] == mailbox_name:
            context_hint = mb.get("context_hint", "")
            break

    domain = extract_domain(sender)
    prefs = db_ops.get_user_preferences(sender_domain=domain)
    prefs_text = ""
    if prefs:
        examples = []
        for p in prefs:
            decision = "IGNORE" if p["user_decision"] == "ignore" else "SHOW"
            examples.append(f"  - '{p['example_subject']}' -> {decision}")
        prefs_text = f"\nUser preferences for {domain}:\n" + "\n".join(examples)

    prompt = f"""You are an email classifier. Analyze and respond ONLY with valid JSON (no markdown).

Mailbox context: {context_hint}
{prefs_text}
Email:
- From: {sender}
- Subject: {subject}
- Body: {snippet[:800]}

Respond with JSON:
- "priority": "critical" | "action_today" | "review" | "ignore"
- "summary_ru": brief summary (1-2 sentences)
- "reason": why this priority
- "suggested_action": what to do (empty if ignore)
- "dates": array of important dates or []
- "amounts": array of money amounts or []"""

    try:
        result = subprocess.run(
            [CLAUDE_CLI, "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "LANG": "en_US.UTF-8"}
        )
        if result.returncode != 0:
            return None

        try:
            cli_output = json.loads(result.stdout)
            ai_text = cli_output.get("result", result.stdout)
        except json.JSONDecodeError:
            ai_text = result.stdout

        ai_text = ai_text.strip()
        ai_text = re.sub(r'^```(?:json)?\s*', '', ai_text)
        ai_text = re.sub(r'\s*```$', '', ai_text)

        try:
            data = json.loads(ai_text)
        except json.JSONDecodeError:
            json_match = re.search(r'\{[^{}]*"priority"[^{}]*\}', ai_text, re.DOTALL)
            if json_match:
                ai_text = json_match.group(0)
            data = json.loads(ai_text)

        priority = data.get("priority", "review")
        if priority not in ("critical", "action_today", "review", "ignore"):
            priority = "review"

        return (priority, data.get("summary_ru", subject), data.get("reason", "AI"),
                data.get("suggested_action", ""), data.get("dates", []), data.get("amounts", []))
    except Exception as e:
        print(f"  [AI] Error: {e}")
        return None


def ai_reclassify(needs_ai, config):
    if not needs_ai or not os.path.exists(CLAUDE_CLI):
        return

    upgraded = 0
    for email_item in needs_ai:
        ai_result = classify_with_ai(
            email_item["id"], email_item["sender"], email_item["subject"],
            email_item.get("snippet", ""), email_item["mailbox"], config
        )
        if not ai_result:
            continue

        priority, summary_ru, reason, suggested_action, dates, amounts = ai_result
        db_ops.save_classification(email_item["id"], priority, summary_ru, reason,
                                   suggested_action, 0.9, "ai", dates, amounts)

        if priority in ("critical", "action_today") and email_item["priority"] not in ("critical", "action_today") and not is_quiet_hours(config):
            sender_short = email_item["sender"].split("<")[0].strip() if "<" in email_item["sender"] else email_item["sender"]
            tg_msg_id = telegram.send_alert(
                email_item["id"], email_item["mailbox"], escape(str(sender_short)),
                escape(str(email_item["subject"])), priority,
                escape(str(summary_ru)), escape(str(reason)), escape(str(suggested_action))
            )
            if tg_msg_id:
                db_ops.save_delivery(email_item["id"], "instant", tg_msg_id)
                upgraded += 1

    print(f"  [AI] Classified {len(needs_ai)}, {upgraded} upgraded to instant")


def process_email(email_data, config):
    msg_id = db_ops.save_message(
        mailbox=email_data["mailbox"], provider_message_id=email_data["message_id"],
        thread_id=None, sender=email_data["sender"], recipients=email_data.get("to", ""),
        subject=email_data["subject"], snippet=email_data["snippet"],
        received_at=email_data["received_at"], body_plain=email_data.get("body_plain", "")
    )
    if not msg_id:
        return None

    priority, reason, classified_by = classify_by_rules(
        email_data["sender"], email_data["subject"], email_data["snippet"], config
    )

    db_ops.save_classification(msg_id, priority, email_data["subject"], reason, "", 0.8, classified_by)

    if priority in ("critical", "action_today") and not is_quiet_hours(config):
        sender_short = email_data["sender"].split("<")[0].strip() if "<" in email_data["sender"] else email_data["sender"]
        tg_msg_id = telegram.send_alert(
            msg_id, email_data["mailbox"], escape(str(sender_short)),
            escape(str(email_data["subject"])), priority,
            escape(str(email_data["subject"])), escape(str(reason)), ""
        )
        if tg_msg_id:
            db_ops.save_delivery(msg_id, "instant", tg_msg_id)
            return f"ALERT: [{priority}] {email_data['subject'][:50]}"

    return f"[{priority}] {email_data['subject'][:50]}"


def main():
    config = load_config()
    new_emails = check_all()
    alerts = 0
    processed = 0

    for email_data in new_emails:
        result = process_email(email_data, config)
        if result:
            processed += 1
            if result.startswith("ALERT"):
                alerts += 1
            print(f"  {result}")

    db_ops.set_state("last_email_check", datetime.now(timezone.utc).isoformat())

    conn = db_ops.get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT m.id, m.mailbox, m.sender, m.subject, m.snippet, c.priority, c.reason
        FROM messages m JOIN classifications c ON c.message_id = m.id
        WHERE c.classified_by = 'rules' AND c.priority = 'review'
        AND datetime(m.fetched_at) > datetime('now', '-1 hour')
    """)
    needs_ai = [dict(r) for r in c.fetchall()]
    conn.close()

    print(f"Done. New: {len(new_emails)}, Processed: {processed}, Alerts: {alerts}")

    if needs_ai:
        print(f"\n[AI] Classifying {len(needs_ai)} emails...")
        ai_reclassify(needs_ai, config)


if __name__ == "__main__":
    main()
