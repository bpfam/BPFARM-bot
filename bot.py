# bot.py — BPFARM bot completo (python-telegram-bot v21+) con auto-protezione da conflitti
import os
import sqlite3
import logging
import shutil
import asyncio as _asyncio
import time as _time
from datetime import datetime, timezone, time as dtime
from pathlib import Path

from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import telegram.error as tgerr

# ===== LOGGING =====
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bpfarm-bot")

# ===== CONFIG =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_FILE = os.environ.get("DB_FILE", "./data/users.db")
ADMIN_ID_ENV = os.environ.get("ADMIN_ID")
ADMIN_ID = int(ADMIN_ID_ENV) if ADMIN_ID_ENV and ADMIN_ID_ENV.isdigit() else None
BACKUP_DIR = os.environ.get("BACKUP_DIR", "./backup")
BACKUP_TIME = os.environ.get("BACKUP_TIME", "03:00")  # HH:MM — orario server (UTC su Render)

PHOTO_URL = os.environ.get(
    "PHOTO_URL",
    "https://i.postimg.cc/WbpGbTBH/5-F5-DFE41-C80-D-4-FC2-B4-F6-D105844664B3.jpg",
)

# ===== DATABASE =====
def init_db():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS utenti (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            data_registrazione TEXT
        )
    """)
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
            (user.id, user.username, user.first_name, user.last_name, datetime.now(timezone.utc).isoformat()),
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
    markup = InlineKeyboardMarkup(keyboard)
    caption = (
        "🏆 Benvenuto nel bot ufficiale di BPFARM!\n\n"
        "⚡ Serietà e rispetto sono la nostra identità.\n"
        "💪 Qui si cresce con impegno e determinazione."
    )
    try:
        await update.message.reply_photo(photo=PHOTO_URL, caption=caption, reply_markup=markup)
    except Exception:
        await update.message.reply_text("👋 Benvenuto! Scegli un’opzione dal menu qui sotto:", reply_markup=markup)

async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM utenti")
    count = cur.fetchone()[0]
    conn.close()
    await update.message.reply_text(f"👥 Utenti registrati: {count}")

# ===== BACKUP =====
def _parse_backup_time(time_str: str) -> dtime:
    try:
        h, m = map(int, time_str.split(":"))
        return dtime(hour=h, minute=m)
    except Exception:
        return dtime(hour=3, minute=0)

async def backup_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"backup_{ts}.db")
        shutil.copy2(DB_FILE, backup_path)
        logger.info(f"💾 Backup creato: {backup_path}")
        if ADMIN_ID:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"✅ Backup completato: {backup_path}")
    except Exception as e:
        logger.exception("Errore backup automatico")
        if ADMIN_ID:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Errore backup: {e}")

# ===== ANTI-CONFLICT CHECK =====
def check_and_clean_webhook(bot):
    loop = _asyncio.get_event_loop()
    try:
        logger.info("🔧 Controllo conflitti Telegram…")
        loop.run_until_complete(bot.delete_webhook(drop_pending_updates=True))
        loop.run_until_complete(bot.get_updates(timeout=1))
        logger.info("✅ Nessun conflitto rilevato, avvio sicuro.")
    except tgerr.Conflict:
        logger.warning(
            "⚠️ ATTENZIONE: Telegram segnala un conflitto!\n"
            "👉 Potrebbe esserci un'altra istanza del bot in esecuzione.\n"
            "Provo a eliminare il webhook e ripulire…"
        )
        loop.run_until_complete(bot.delete_webhook(drop_pending_updates=True))
        _time.sleep(5)
        try:
            loop.run_until_complete(bot.get_updates(timeout=1))
            logger.info("✅ Conflitto risolto automaticamente.")
        except tgerr.Conflict:
            logger.error(
                "🚨 Conflitto persistente! "
                "Vai su BotFather → /mybots → @Bpfarmbot → Bot Settings → Delete Webhook "
                "oppure rigenera il token e riavvia Render."
            )

# ===== MAIN =====
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Anti-conflict automatico
    check_and_clean_webhook(app.bot)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("utenti", utenti))

    # Backup giornaliero
    hhmm = _parse_backup_time(BACKUP_TIME)
    app.job_queue.run_daily(backup_job, time=hhmm, days=(0, 1, 2, 3, 4, 5, 6))

    logger.info("🚀 Avvio bot BPFARM...")
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except tgerr.Conflict:
        logger.error("❌ Conflict rilevato: un'altra istanza del bot è già attiva.")
        logger.error("➡️ Soluzione: revoca il token da BotFather o cancella il webhook, poi riavvia Render.")
    except Exception as e:
        logger.exception(f"Errore in esecuzione: {e}")

if __name__ == "__main__":
    main()