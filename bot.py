# bot.py – Telegram Bot (python-telegram-bot v21+)
import os
import sqlite3
from datetime import datetime
from pathlib import Path
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ======== LOGGING ========
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ======== CONFIG ========
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_FILE = os.environ.get("DB_FILE", "./data/users.db")

# Immagine opzionale di benvenuto (usa un link diretto .jpg/.png)
PHOTO_URL = os.environ.get(
    "PHOTO_URL",
    "https://i.postimg.cc/hPgZxyhz/5-F5-DFE41-C80D-4-FC2-B4-F6-D1058440-B1.jpg",
)

# ======== DATABASE ========
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
        )
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
        (user.id, user.username, user.first_name, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def count_users() -> int:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    (n,) = cur.fetchone()
    conn.close()
    return n or 0


# ======== HANDLERS ========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # salva utente
    add_user(update.effective_user)

    # testo benvenuto
    message_text = (
        "🏆 *Benvenuto nel bot ufficiale di BPFAM!*\n\n"
        "⚡ Serietà e rispetto sono la nostra identità.\n"
        "💪 Qui si cresce con impegno e determinazione."
    )

    # tastiera con link
    keyboard = [
        [
            InlineKeyboardButton("📖 Menu", url="https://t.me/+fIQWowFYHWZjZWU0"),
            InlineKeyboardButton("💥 Recensioni", url="https://t.me/+w3_ePB2hmVwxNmNk"),
        ],
        [
            InlineKeyboardButton("📱 Contatti / Info", url="https://t.me/+dBuWJRY9sH0xMGE0"),
            InlineKeyboardButton("🇪🇸Shiip Spagna", url="https://t.me/+oNfKAtrBMYA1MmRk"),
        ],
        [
            InlineKeyboardButton("🔗 Link", url="https://t.me/tuocontattoqui"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # invio foto + caption se il link è valido, altrimenti solo testo
    if PHOTO_URL and PHOTO_URL.startswith(("http://", "https://")):
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=PHOTO_URL,
            caption=message_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )
    else:
        await update.message.reply_text(
            text=message_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )


async def info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📇 *Contatti*\n"
        "• Telegram: @tuo_username\n"
        "• Email: info@example.com\n"
        "• Orari: 9–18",
        parse_mode=ParseMode.MARKDOWN,
    )


async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    n = count_users()
    await update.message.reply_text(f"👥 Utenti registrati: {n}")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "/start — Benvenuto\n"
        "/utenti — Numero utenti\n"
        "/info — Contatti\n"
        "/help — Aiuto"
    )


# ======== MAIN ========
def main() -> None:
    if not BOT_TOKEN:
        logger.error("❌ ERRORE: Variabile d'ambiente BOT_TOKEN mancante")
        return

    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("info", info_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    logger.info("✅ Bot avviato con successo!")
    app.run_polling()


if __name__ == "__main__":
    main()