#!/usr/bin/env python3
"""Telegram message sender for Email Courier."""
import json
import subprocess
import sys
import os
import yaml

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_DIR, "config.yaml")

def load_telegram_config():
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    return cfg["telegram"]["bot_token"], cfg["telegram"]["chat_id"]

BOT_TOKEN, CHAT_ID = load_telegram_config()
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send(text, parse_mode="HTML", buttons=None):
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if buttons:
        payload["reply_markup"] = json.dumps({"inline_keyboard": buttons})
    if len(payload["text"]) > 4000:
        payload["text"] = payload["text"][:3997] + "..."
    try:
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", f"{API}/sendMessage",
             "-H", "Content-Type: application/json",
             "-d", json.dumps(payload)],
            capture_output=True, text=True, timeout=30
        )
        resp = json.loads(result.stdout)
        if resp.get("ok"):
            return resp["result"]["message_id"]
        else:
            print(f"Telegram error: {resp}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"Telegram send failed: {e}", file=sys.stderr)
        return None

def send_alert(msg_id, mailbox, sender, subject, priority, summary_ru, reason, suggested_action):
    emoji = "🔴" if priority == "critical" else "⚡"
    text = f"""{emoji} <b>{priority.upper()} | {mailbox}</b>
From: {sender}
Subject: {subject}

<b>Summary:</b> {summary_ru}
<b>Reason:</b> {reason}
<b>Action:</b> {suggested_action}"""

    buttons = [
        [
            {"text": "📄 Full text", "callback_data": f"full:{msg_id}"},
            {"text": "❓ Details", "callback_data": f"ask:{msg_id}"},
            {"text": "✅ Done", "callback_data": f"done:{msg_id}"},
        ],
        [
            {"text": "🔕 Skip these", "callback_data": f"skip_type:{msg_id}"},
            {"text": "✅ Always these", "callback_data": f"keep_type:{msg_id}"},
        ],
        [
            {"text": "⚡ VIP sender", "callback_data": f"vip:{msg_id}"},
            {"text": "🔇 Mute sender", "callback_data": f"mute:{msg_id}"},
        ],
    ]
    return send(text, buttons=buttons)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        msg_id = send(" ".join(sys.argv[1:]))
        print(f"Sent, message_id={msg_id}" if msg_id else "Failed")
    else:
        print("Usage: telegram.py <message>")
