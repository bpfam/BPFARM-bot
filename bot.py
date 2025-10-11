# bot.py
# Python-Telegram-Bot v20+

import os
import sqlite3
import logging
from datetime import datetime
from pathlib import Path

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    constants,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ===================== LOGGING =====================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("telegram-bot")

# ===================== CONFIG =====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

# Usa disco persistente su Render (es. /data) oppure
# salva nella cartella del progetto in locale.
DB_FILE = os.environ.get("DB_FILE") or str(Path(__file__).with_name("users.db"))

# ===================== DATABASE =====================
def init_db() -> None:
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            created_at TEXT
        );
        """
    )
    conn.commit()
    conn.close()

def add_user(user) -> None:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO users (id, username, first_name, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            user.id,
            user.username,
            user.first_name,
            datetime.utcnow().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()
    conn.close()

def count_users() -> int:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    (n,) = cur.fetchone()
    conn.close()
    return int(n or 0)

# ===================== HANDLERS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user = update.effective_user

    # Salva nel DB
    add_user(user)
    log.info("✅ Utente salvato: id=%s, username=%s", user.id, user.username)

    # Tastiera con link (sostituisci gli URL con i tuoi)
    keyboard = [
        [
            InlineKeyboardButton("📖 Menu", url="https://tuo-sito.example/menu"),
            InlineKeyboardButton("💥 Recensioni", url="https://tuo-sito.example/reviews"),
        ],
        [
            InlineKeyboardButton("📱 Info-bot", url="https://t.me/tuo_canale"),
            InlineKeyboardButton("🚢 Ship", url="https://tuo-sito.example/ship"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Testo messaggio
    message_text = (
        "💨 Yo! Benvenuto nel bot ufficiale!\n"
        "📖 *Menu, info e contatti* qui sotto.\n"
        "💬 Scrivici su Telegram se hai domande."
    )

    # Foto + caption + bottoni (metti la tua immagine)
    await context.bot.send_photo(
        chat_id=chat_id,
        photo="https://i.postimg.cc/LJNH...sostituisci...jpg",
        caption=message_text,
        parse_mode=constants.ParseMode.MARKDOWN,
        reply_markup=reply_markup,
    )

async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    n = count_users()
    await update.message.reply_text(f"👥 Utenti registrati: *{n}*", parse_mode=constants.ParseMode.MARKDOWN)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Comandi disponibili:\n"
        "/start — Benvenuto + pulsanti\n"
        "/utenti — Numero di utenti salvati\n"
        "/help — Questo messaggio"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("pong 🏓")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Errore non gestito: %s", context.error)

# ===================== MAIN =====================
def main() -> None:
    if not BOT_TOKEN:
        log.error("❌ ERRORE: Variabile d'ambiente BOT_TOKEN mancante.")
        return

    # DB
    init_db()

    # App PTB
    app: Application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ping", ping))

    # Errori
    app.add_error_handler(error_handler)

    log.info("✅ Bot avviato con successo! In ascolto (polling)...")
    # Per Render Background Worker: nessuna porta da esporre
    app.run_polling(drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    main()