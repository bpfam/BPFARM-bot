# bot.py – Telegram Bot compatibile con python-telegram-bot v20.7
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ========= CONFIG =========
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_FILE = os.environ.get("DB_FILE", "/data/users.db")

# ========= DATABASE =========
def init_db():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_user(user):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO users (id, username, first_name, created_at)
        VALUES (?, ?, ?, ?)
    """, (user.id, user.username, user.first_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def count_users():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    (n,) = cur.fetchone()
    conn.close()
    return n or 0

# ========= HANDLERS =========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(update.effective_user)

    message_text = (
        "💨 Yo! Benvenuto nel bot ufficiale!\n"
        "📖 Menu, info e contatti qui sotto 👇\n"
        "💬 Scrivici su Telegram se hai domande!"
    )

    keyboard = [
        [
            InlineKeyboardButton("📖 Menu", callback_data="menu"),
            InlineKeyboardButton("💥 Recensioni", callback_data="recensioni"),
        ],
        [
            InlineKeyboardButton("📱 Contatti", callback_data="contatti"),
            InlineKeyboardButton("Ship shop 💎", callback_data="shop"),
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo="https://i.postimg.cc/hPgZxyhz/5-F5-DFE41-C80D-4FC2-B4F6-D1058440-B1.jpg",
        caption=message_text,
        parse_mode=constants.ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )
async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    n = count_users()
    await update.message.reply_text(f"👥 Utenti registrati: {n}")



async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start – Benvenuto\n"
        "/utenti – Numero utenti\n"
        "/help – Aiuto"
    )

# ========= MAIN =========
def main():
    if not BOT_TOKEN:
        print("❌ ERRORE: Nessun token trovato nelle variabili d'ambiente.")
        return

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("help", help_cmd))

    print("✅ Bot avviato con successo! In ascolto (polling)...")
    app.run_polling()

if __name__ == "__main__":
    init_db()
    main()
    