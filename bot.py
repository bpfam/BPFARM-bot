# bot.py — BPFARM bot completo (python-telegram-bot v21+)
import os
import csv
import sqlite3
import logging
import shutil
from io import StringIO, BytesIO
from datetime import datetime, timezone
from pathlib import Path

from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ===== LOGGING =====
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bpfarm-bot")

# ===== CONFIG (Render ENV) =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_FILE = os.environ.get("DB_FILE", "./data/users.db")
ADMIN_ID_ENV = os.environ.get("ADMIN_ID")
ADMIN_ID = int(ADMIN_ID_ENV) if ADMIN_ID_ENV and ADMIN_ID_ENV.isdigit() else None
BACKUP_DIR = os.environ.get("BACKUP_DIR", "./backup")
BACKUP_TZ = os.environ.get("BACKUP_TZ", "Etc/UTC")
BACKUP_TIME = os.environ.get("BACKUP_TIME", "03:00")  # formato HH:MM

# ===== DATABASE =====
def init_db():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS utenti (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            data_registrazione TEXT
        )
        """
    )
    conn.commit()
    conn.close()

def salva_utente(update: Update):
    user = update.effective_user
    if not user:
        return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id FROM utenti WHERE id=?", (user.id,))
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO utenti (id, username, first_name, last_name, data_registrazione) VALUES (?, ?, ?, ?, ?)",
            (
                user.id,
                user.username,
                user.first_name,
                user.last_name,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        logger.info(f"Nuovo utente salvato: {user.first_name} ({user.id})")
    conn.close()

# ===== COMANDI =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    salva_utente(update)
    keyboard = [
        [InlineKeyboardButton("📖 Menù", url="https://t.me/+w3_ePB2hmVwxNmNk")],
        [InlineKeyboardButton("🇪🇸 Shiip-Spagna", url="https://t.me/+oNfKAtrBMYA1MmRk")],
        [InlineKeyboardButton("🎇 Recensioni", url="https://t.me/+fIQWowFYHWZjZWU0")],
        [InlineKeyboardButton("📲 Info-Contatti", url="https://t.me/+dBuWJRY9sH0xMGE0")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Benvenuto! Scegli un’opzione dal menu qui sotto:",
        reply_markup=reply_markup,
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Comandi disponibili:\n/start - Avvia il bot\n/utenti - Mostra utenti registrati\n/backup - Esegui backup manuale")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong!")

async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM utenti")
    count = cur.fetchone()[0]
    conn.close()
    await update.message.reply_text(f"👥 Utenti registrati: {count}")

# ===== BACKUP =====
def _parse_backup_time(time_str: str):
    try:
        h, m = map(int, time_str.split(":"))
        from telegram.ext import Time
        return Time(hour=h, minute=m)
    except Exception:
        from telegram.ext import Time
        return Time(hour=3, minute=0)

async def backup_job(context: ContextTypes.DEFAULT_TYPE):
    """Esegue il backup automatico del database."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"backup_{ts}.db")
    shutil.copy2(DB_FILE, backup_path)
    logger.info(f"💾 Backup creato: {backup_path}")

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Esegue backup manuale e invia il file all’admin."""
    if ADMIN_ID and update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Solo l’amministratore può eseguire questa operazione.")
        return
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"manual_backup_{ts}.db")
    shutil.copy2(DB_FILE, backup_path)
    await update.message.reply_document(InputFile(backup_path), caption="💾 Backup manuale completato.")
    logger.info(f"💾 Backup manuale eseguito: {backup_path}")

async def ultimo_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra l’ultimo file di backup."""
    if not os.path.exists(BACKUP_DIR):
        await update.message.reply_text("Nessun backup trovato.")
        return
    files = sorted(Path(BACKUP_DIR).glob("*.db"), reverse=True)
    if not files:
        await update.message.reply_text("Nessun backup disponibile.")
        return
    ultimo = files[0]
    await update.message.reply_document(InputFile(ultimo), caption=f"📦 Ultimo backup: {ultimo.name}")

# ===== MAIN =====
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Pulisce eventuali update pendenti
    import asyncio as _asyncio
    _asyncio.get_event_loop().run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))

    # Comandi
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("ultimo_backup", ultimo_backup))

    # Pianificazione backup giornaliero (fix timezone)
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(BACKUP_TZ)
    except Exception:
        tz = timezone.utc

    logger.info(f"🕒 Timezone backup impostata su: {tz}")

    hhmm = _parse_backup_time(BACKUP_TIME)
    app.job_queue.run_daily(
        backup_job,
        time=hhmm,
        days=(0, 1, 2, 3, 4, 5, 6),  # tutti i giorni
        name="daily_db_backup",
        timezone=tz,
    )

    logger.info("🕒 Backup giornaliero pianificato.")
    logger.info("🚀 Bot avviato.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()