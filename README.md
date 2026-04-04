# Email Courier

Smart email notification system. Checks multiple mailboxes via IMAP, classifies emails by priority using rules + AI, sends alerts to Telegram.

## What it does

- Checks all your email accounts every 5 minutes
- 2-stage classification: **rules** (instant) then **Claude AI** (smart)
- Sends Telegram alerts with action buttons for urgent emails
- Sends digest summaries at scheduled times
- Learns from your feedback via Telegram buttons

## Features

- **Multiple mailboxes** — Gmail, Yahoo, Outlook, Mail.ru, any IMAP
- **Smart classification** — critical / action_today / review / ignore
- **Telegram buttons** — VIP sender, Mute sender, Skip these, Always show
- **AI learns** — your button presses teach the AI your preferences
- **Quiet hours** — no alerts at night, accumulated for morning digest
- **Full text** — read entire email from Telegram
- **Search** — `/search keyword` to find emails
- **Stats** — `/stats` for classification breakdown

## Quick start

```bash
# Clone
git clone https://github.com/hiddensti/email-courier.git
cd email-courier

# Setup (installs deps, creates config files)
chmod +x setup.sh && ./setup.sh

# Edit your settings
nano config.yaml        # Telegram bot token, filters, schedule
nano passwords.yaml     # Email accounts and IMAP passwords

# Run
nohup python3 scripts/bot_daemon.py > bot.log 2>&1 &
```

## Setup details

### 1. Create Telegram bot
1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy the token → paste in `config.yaml` → `bot_token`
3. Message [@userinfobot](https://t.me/userinfobot) → copy your chat ID → paste in `config.yaml` → `chat_id`

### 2. Get IMAP app passwords

| Provider | Where |
|----------|-------|
| Gmail | Settings → Security → 2-Step → App passwords |
| Yahoo | Account → Security → Generate app password |
| Outlook | Account → Security → App passwords |
| Mail.ru | Settings → Security → App passwords |

Put credentials in `passwords.yaml` (not tracked by git).

### 3. Configure filters

Edit `config.yaml`:
- `hard_skip_domains` — always ignore (spam)
- `never_skip_domains` — always process (bank, tax, etc.)
- `vip_senders` — always instant alert
- `never_skip_keywords` — trigger on words like "invoice", "deadline"

### 4. AI classification (optional)

If you have [Claude Code](https://claude.ai/download) installed, emails classified as "review" by rules will be analyzed by Claude AI for smarter prioritization. Without it, rule-based classification still works.

## Telegram commands

| Command | What it does |
|---------|-------------|
| `/stats` | Classification breakdown |
| `/health` | Last check time, status |
| `/digest` | Force send digest now |
| `/search keyword` | Search emails |
| `/rules` | Show active sender rules |

## Architecture

```
bot_daemon.py — single process
  ├── Telegram bot (aiogram, long-polling)
  ├── Email check loop (every 5 min)
  │   ├── check_imap.py — fetch from all IMAP mailboxes
  │   └── run_check.py — rules → AI → alerts
  └── Digest scheduler (configurable times)
      └── run_digest.py — format and send digest

db/email_bot.db — SQLite
  ├── messages — all fetched emails
  ├── classifications — priority, AI summary
  ├── deliveries — what was sent to Telegram
  ├── sender_rules — VIP/mute from buttons
  └── user_preferences — AI learning examples
```

## Requirements

- Python 3.9+
- macOS or Linux
- Claude Code CLI (optional, for AI classification)

## License

MIT
