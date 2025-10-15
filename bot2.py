# =====================================================
# bot2.py — BPFAM1 BOT (python-telegram-bot v21+)
# Versione definitiva: backup + admin + immagine + no loop error
# =====================================================

import os
import sqlite3
import logging
import shutil
import asyncio as aio
import csv
from datetime import datetime
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import telegram.error as tgerr

VERSION = "2.1-BPFAM1"

# ===== LOGGING =====
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bpfam1-bot")

# ===== CONFIG =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_FILE = os.environ.get("DB_FILE", "./data/users.db")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8033084779"))
BACKUP_DIR = os.environ.get("BACKUP_DIR", "./backup")

# Immagine di benvenuto
WELCOME_PHOTO_URL = os.environ.get(
    "WELCOME_PHOTO_URL",
    "https://i.postimg.cc/hPgZxyhz/5-F5-DFE41-C80D-4-FC2-B4-F6-D1058440-B1.jpg",
)

# ===== DATABASE =====
def init_db():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            joined TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.commit()
    conn.close()

# ===== UTILITY =====
async def add_user(update: Update):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    user = update.effective_user
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
        (user.id, user.username, user.first_name, user.last_name),
    )
    conn.commit()
    conn.close()

# ===== START COMMAND =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await add_user(update)

    keyboard = [
        [InlineKeyboardButton("📋 Accesso e menù", url="https://t.me/Bpfarmbot")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    caption = (
        "🇮🇹🇪🇸🇺🇸🇲🇦 𝐁𝐏𝐅𝐀𝐌 - 𝐔𝐅𝐅𝐈𝐂𝐈𝐀𝐋𝐄𝟒𝟐𝟎 🌐\n\n"
        "Benvenuto nel bot ufficiale di BPFAM!\n"
        "Serietà e rispetto 🔥 Qui si cresce con impegno e determinazione 💪"
    )

    try:
        await update.message.reply_photo(
            photo=WELCOME_PHOTO_URL,
            caption=caption,
            reply_markup=reply_markup,
        )
    except tgerr.BadRequest:
        await update.message.reply_text(caption, reply_markup=reply_markup)

# ===== ADMIN COMMANDS =====
async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    conn.close()
    await update.message.reply_text(f"👥 Utenti totali: {count}")

async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users")
    users = cur.fetchall()
    conn.close()

    csv_path = Path(BACKUP_DIR) / f"users_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id", "username", "first_name", "last_name", "joined"])
        writer.writerows(users)

    await update.message.reply_document(InputFile(csv_path), filename=csv_path.name)

# ===== BACKUP LOOP =====
async def daily_backup_loop():
    while True:
        try:
            now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_name = f"users_backup_{now}.db"
            Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
            shutil.copy(DB_FILE, Path(BACKUP_DIR) / backup_name)
            logger.info(f"[BACKUP] Database salvato ({backup_name})")
        except Exception as e:
            logger.error(f"[BACKUP ERROR] {e}")
        await aio.sleep(86400)  # ogni 24 ore

# ===== MAIN =====
async def main():
    init_db()
    logger.info(f"🚀 Avvio BPFAM1 BOT v{VERSION}")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Comandi
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("export", export))

    # Avvia il bot e poi il backup in parallelo
    async with app:
        aio.create_task(daily_backup_loop())
        await app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    aio.run(main())