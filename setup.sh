#!/bin/bash
# Email Courier — one-command setup
set -e

echo "📧 Email Courier Setup"
echo "======================"

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3 required. Install: brew install python3"
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
pip3 install aiogram pyyaml --quiet

# Check Claude CLI (optional, for AI classification)
if [ -f ~/.local/bin/claude ]; then
    echo "✅ Claude CLI found — AI classification enabled"
else
    echo "⚠️  Claude CLI not found — rule-based classification only"
    echo "   Install Claude Code for AI: https://claude.ai/download"
fi

# Copy config templates
if [ ! -f config.yaml ]; then
    cp config.example.yaml config.yaml
    echo "📝 Created config.yaml — edit it with your Telegram bot token and settings"
else
    echo "✅ config.yaml exists"
fi

if [ ! -f passwords.yaml ]; then
    cp passwords.example.yaml passwords.yaml
    echo "🔑 Created passwords.yaml — edit it with your IMAP credentials"
else
    echo "✅ passwords.yaml exists"
fi

# Init database
echo "🗄️  Initializing database..."
python3 scripts/init_db.py

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit config.yaml — set your Telegram bot_token and chat_id"
echo "  2. Edit passwords.yaml — add your email accounts and IMAP app passwords"
echo "  3. Run: nohup python3 scripts/bot_daemon.py > bot.log 2>&1 &"
echo ""
echo "Get bot_token: message @BotFather on Telegram, /newbot"
echo "Get chat_id:   message @userinfobot on Telegram"
echo "Get app passwords:"
echo "  Gmail:  Settings → Security → 2FA → App passwords"
echo "  Yahoo:  Account → Security → Generate app password"
echo "  Mail.ru: Settings → Security → App passwords"
