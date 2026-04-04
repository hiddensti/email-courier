#!/usr/bin/env python3
"""
Email Courier Telegram daemon.
Single process: Telegram bot + email check loop + digest scheduler.
"""
import asyncio
import logging
import sys
import os
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.enums import ParseMode

import db_ops
from html import escape

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_DIR, "config.yaml")

with open(CONFIG_PATH) as f:
    _cfg = yaml.safe_load(f)

BOT_TOKEN = _cfg["telegram"]["bot_token"]
ALLOWED_CHAT_ID = int(_cfg["telegram"]["chat_id"])

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("email-courier")


def check_user(chat_id: int) -> bool:
    return chat_id == ALLOWED_CHAT_ID


# ============ BUTTON HANDLERS ============

@dp.callback_query(F.data.startswith("full:"))
async def on_full_text(callback: CallbackQuery):
    if not check_user(callback.message.chat.id):
        return
    msg_id = int(callback.data.split(":")[1])
    conn = db_ops.get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT m.sender, m.subject, m.snippet, m.body_plain,
               c.summary_ru, c.suggested_action
        FROM messages m LEFT JOIN classifications c ON c.message_id = m.id
        WHERE m.id = ?
    """, (msg_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        await callback.answer("Not found")
        return
    body = row["body_plain"] or row["snippet"] or "(no body)"
    text = f"📄 <b>Full text</b>\n\n<b>From:</b> {escape(str(row['sender']))}\n<b>Subject:</b> {escape(str(row['subject']))}\n\n{escape(str(body[:3000]))}"
    await callback.message.reply(text, parse_mode=ParseMode.HTML)
    await callback.answer()


@dp.callback_query(F.data.startswith("ask:"))
async def on_ask(callback: CallbackQuery):
    if not check_user(callback.message.chat.id):
        return
    msg_id = int(callback.data.split(":")[1])
    conn = db_ops.get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT m.sender, m.subject, m.snippet, m.body_plain,
               c.summary_ru, c.reason, c.suggested_action, c.dates_json, c.amounts_json
        FROM messages m LEFT JOIN classifications c ON c.message_id = m.id
        WHERE m.id = ?
    """, (msg_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        await callback.answer("Not found")
        return
    body = (row['body_plain'] or row['snippet'] or '')[:500]
    text = f"❓ <b>Details #{msg_id}</b>\n\n<b>From:</b> {escape(str(row['sender']))}\n<b>Subject:</b> {escape(str(row['subject']))}\n\n<b>Summary:</b> {escape(str(row['summary_ru'] or ''))}\n<b>Reason:</b> {escape(str(row['reason'] or ''))}\n<b>Action:</b> {escape(str(row['suggested_action'] or ''))}\n<b>Dates:</b> {row['dates_json'] or 'none'}\n<b>Amounts:</b> {row['amounts_json'] or 'none'}\n\n<pre>{escape(body)}</pre>"
    await callback.message.reply(text, parse_mode=ParseMode.HTML)
    await callback.answer()


@dp.callback_query(F.data.startswith("done:"))
async def on_done(callback: CallbackQuery):
    if not check_user(callback.message.chat.id):
        return
    db_ops.mark_done(int(callback.data.split(":")[1]))
    await callback.answer("✅ Done")


@dp.callback_query(F.data.startswith("vip:"))
async def on_vip(callback: CallbackQuery):
    if not check_user(callback.message.chat.id):
        return
    msg_id = int(callback.data.split(":")[1])
    conn = db_ops.get_conn()
    c = conn.cursor()
    c.execute("SELECT sender FROM messages WHERE id=?", (msg_id,))
    row = c.fetchone()
    conn.close()
    if row:
        sender = row["sender"]
        email_addr = sender.split("<")[1].split(">")[0] if "<" in sender else sender
        db_ops.add_sender_rule(email_addr, "vip", source="user_feedback")
        await callback.answer(f"⚡ {email_addr} added to VIP")
    else:
        await callback.answer("Not found")


@dp.callback_query(F.data.startswith("mute:"))
async def on_mute(callback: CallbackQuery):
    if not check_user(callback.message.chat.id):
        return
    msg_id = int(callback.data.split(":")[1])
    conn = db_ops.get_conn()
    c = conn.cursor()
    c.execute("SELECT sender FROM messages WHERE id=?", (msg_id,))
    row = c.fetchone()
    conn.close()
    if row:
        sender = row["sender"]
        email_addr = sender.split("<")[1].split(">")[0] if "<" in sender else sender
        db_ops.add_sender_rule(email_addr, "mute", source="user_feedback")
        await callback.answer(f"🔇 {email_addr} muted")
    else:
        await callback.answer("Not found")


@dp.callback_query(F.data.startswith("skip_type:"))
async def on_skip_type(callback: CallbackQuery):
    if not check_user(callback.message.chat.id):
        return
    msg_id = int(callback.data.split(":")[1])
    conn = db_ops.get_conn()
    c = conn.cursor()
    c.execute("SELECT m.sender, m.subject, c.summary_ru FROM messages m LEFT JOIN classifications c ON c.message_id = m.id WHERE m.id=?", (msg_id,))
    row = c.fetchone()
    conn.close()
    if row:
        sender = row["sender"]
        email_addr = sender.split("<")[1].split(">")[0] if "<" in sender else sender
        domain = email_addr.split("@")[1] if "@" in email_addr else email_addr
        db_ops.save_user_preference(msg_id, email_addr, domain, row["subject"], row["summary_ru"] or row["subject"], "ignore")
        await callback.answer(f"🔕 AI learned: skip these")
    else:
        await callback.answer("Not found")


@dp.callback_query(F.data.startswith("keep_type:"))
async def on_keep_type(callback: CallbackQuery):
    if not check_user(callback.message.chat.id):
        return
    msg_id = int(callback.data.split(":")[1])
    conn = db_ops.get_conn()
    c = conn.cursor()
    c.execute("SELECT m.sender, m.subject, c.summary_ru FROM messages m LEFT JOIN classifications c ON c.message_id = m.id WHERE m.id=?", (msg_id,))
    row = c.fetchone()
    conn.close()
    if row:
        sender = row["sender"]
        email_addr = sender.split("<")[1].split(">")[0] if "<" in sender else sender
        domain = email_addr.split("@")[1] if "@" in email_addr else email_addr
        db_ops.save_user_preference(msg_id, email_addr, domain, row["subject"], row["summary_ru"] or row["subject"], "important")
        await callback.answer(f"✅ AI learned: always show these")
    else:
        await callback.answer("Not found")


# ============ COMMANDS ============

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if not check_user(message.chat.id):
        return
    stats = db_ops.get_stats()
    text = f"📊 <b>Stats</b>\n\nTotal emails: {stats['total']}\nDelivered today: {stats['delivered_today']}\n\n🔴 Critical: {stats['by_priority'].get('critical', 0)}\n⚡ Action: {stats['by_priority'].get('action_today', 0)}\n📋 Review: {stats['by_priority'].get('review', 0)}\n🗑 Ignore: {stats['by_priority'].get('ignore', 0)}"
    await message.reply(text, parse_mode=ParseMode.HTML)


@dp.message(Command("health"))
async def cmd_health(message: Message):
    if not check_user(message.chat.id):
        return
    last = db_ops.get_state("last_email_check", "never")
    await message.reply(f"🏥 <b>Health</b>\n\nLast check: {last}\nStatus: ✅ Online", parse_mode=ParseMode.HTML)


# ============ EMAIL CHECK LOOP ============

CHECK_INTERVAL = 300

async def email_check_loop():
    await asyncio.sleep(10)
    log.info(f"Email check loop started (every {CHECK_INTERVAL}s)")

    digest_hours = _cfg.get("digest", {}).get("schedule", ["06:00", "18:00"])
    digest_hour_ints = [int(t.split(":")[0]) for t in digest_hours]
    last_digest_hour = None

    while True:
        try:
            import subprocess
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_check.py")
            result = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=120)
            if result.stdout:
                log.info(f"Check: {result.stdout.strip().split(chr(10))[-1]}")
            if result.stderr:
                log.error(f"Check error: {result.stderr[:200]}")

            from datetime import datetime
            from zoneinfo import ZoneInfo
            tz = _cfg.get("digest", {}).get("timezone", "UTC")
            now = datetime.now(ZoneInfo(tz))
            current_hour = now.hour

            if current_hour in digest_hour_ints and current_hour != last_digest_hour:
                last_digest_hour = current_hour
                digest_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_digest.py")
                subprocess.run([sys.executable, digest_script], capture_output=True, text=True, timeout=60)
                log.info("Digest sent")

        except Exception as e:
            log.error(f"Check loop error: {e}")

        await asyncio.sleep(CHECK_INTERVAL)


async def main():
    log.info("Email Courier daemon starting...")
    asyncio.create_task(email_check_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    import time
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            break
        except Exception as e:
            log.error(f"Bot crashed: {e}, restarting in 10s...")
            time.sleep(10)
