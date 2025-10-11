# bot.py
# python-telegram-bot v20+

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ========= CONFIG =========
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # export BOT_TOKEN="..."
DB_FILE = str(Path(__file__).with_name("users.db"))

# ========= DATABASE =========
def init_db():
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
    """, (user.id, user.username, user.first_name, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def count_users():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    (n,) = cur.fetchone()
    conn.close()
    return n

# ========= HANDLERS =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    # salva nel DB
    add_user(user)
    print(f"✅ Utente salvato: id={user.id}, username={user.username}")

    # testo messaggio
    message_text = (
        "💨 Yo! Benvenuto nel bot ufficiale.\n"
        "📖 Menu, info e contatti qui sotto.\n"
        "💬 Scrivici su Telegram se hai bisogno."
    )

    # tastiera con link (metti i tuoi URL reali)
    keyboard = [
        [InlineKeyboardButton("📖 Menu", url="https://example.com/menu"),
         InlineKeyboardButton("💥 Recensioni", url="https://example.com/reviews")],
        [InlineKeyboardButton("📱 Info-bot", url="https://t.me/tuocanale"),
         InlineKeyboardButton("🇪🇸 Ship", url="https://example.com/ship")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # invia foto + caption + bottoni
    await context.bot.send_photo(
        chat_id=chat_id,
        photo="https://i.postimg.cc/LJNHDxxxx/cover.jpg",  # <-- sostituisci con la tua immagine
        caption=message_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    n = count_users()
    await update.message.reply_text(f"👥 Utenti salvati: {n}")

# ========= MAIN =========
def main():
    if not BOT_TOKEN:
        print("❌ ERRORE: Nessun token trovato. Imposta la variabile d'ambiente BOT_TOKEN.")
        return

    init_db()  # crea tabella se non esiste

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("utenti", utenti))

    print("✅ Bot avviato con successo!")
    app.run_polling()

if __name__ == "__main__":
    main()