# bot.py — BPFARM bot con backup giornaliero + notifica admin + /ultimo_backup
# Compatibile con python-telegram-bot v21+
import os
import csv
import sqlite3
import logging
import shutil
from io import StringIO, BytesIO
from datetime import datetime, timezone, time as dtime
from pathlib import Path

from zoneinfo import ZoneInfo  # Python 3.9+

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

# ===== CONFIG =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_FILE = os.environ.get("DB_FILE", "./data/users.db")
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "./data/backups"))

# Admin (necessario per comandi sensibili e notifiche)
ADMIN_ID_ENV = os.environ.get("ADMIN_ID")
ADMIN_ID = int(ADMIN_ID_ENV) if ADMIN_ID_ENV and ADMIN_ID_ENV.isdigit() else None

# Pianificazione backup
BACKUP_TIME = os.environ.get("BACKUP_TIME", "03:00")       # HH:MM 24h — es. "02:30"
BACKUP_TZ = os.environ.get("BACKUP_TZ", "Europe/Rome")     # es. "UTC", "Europe/Rome"

# Immagine e pulsanti
WELCOME_PHOTO_URL = os.environ.get(
    "WELCOME_PHOTO_URL",
    "https://i.postimg.cc/0QSgSydz/5-F5-DFE41-C80-D-4-FC2-B4-F6-D1058440-B1.jpg",
)
BTN_MENU_LABEL     = os.environ.get("BTN_MENU_LABEL", "📖 Menù")
BTN_SPAIN_LABEL    = os.environ.get("BTN_SPAIN_LABEL", "🇪🇸 Shiip-Spagna")
BTN_REVIEWS_LABEL  = os.environ.get("BTN_REVIEWS_LABEL", "🎇 Recensioni")
BTN_CONTACTS_LABEL = os.environ.get("BTN_CONTACTS_LABEL", "📲 Info-Contatti")

MENU_URL     = os.environ.get("MENU_URL", "https://t.me/+w3_ePB2hmVwxNmNk")
SPAIN_URL    = os.environ.get("SPAIN_URL", "https://t.me/+oNfKAtrBMYA1MmRk")
REV_URL      = os.environ.get("RECENSIONI_URL", "https://t.me/+fIQWowFYHWZjZWU0")
CONTACTS_URL = os.environ.get("CONTATTI_URL", "https://t.me/+dBuWJRY9sH0xMGE0")

# ===== DATABASE =====
def ensure_users_table():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            joined_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_user_if_needed(tg_user):
    ensure_users_table()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, joined_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        tg_user.id,
        tg_user.username,
        tg_user.first_name,
        tg_user.last_name,
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    ))
    conn.commit()
    conn.close()

def get_user_count():
    ensure_users_table()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    (count,) = cur.fetchone()
    conn.close()
    return count

# ===== UTILS =====
def is_admin(user_id: int) -> bool:
    return True if ADMIN_ID is None else (user_id == ADMIN_ID)

async def require_admin(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    if not is_admin(user.id):
        await update.effective_message.reply_text("❌ Solo l'admin può usare questo comando.")
        logger.warning("Accesso negato a user_id=%s", user.id)
        return False
    return True

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

# ===== UI / START =====
def menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(BTN_MENU_LABEL, url=MENU_URL),
         InlineKeyboardButton(BTN_REVIEWS_LABEL, url=REV_URL)],
        [InlineKeyboardButton(BTN_CONTACTS_LABEL, url=CONTACTS_URL),
         InlineKeyboardButton(BTN_SPAIN_LABEL, url=SPAIN_URL)],
    ]
    return InlineKeyboardMarkup(rows)

WELCOME_TEXT = (
    "🏆 *Benvenuto nel bot ufficiale di BPFAM!*\n\n"
    "⚡ Serietà e rispetto sono la nostra identità.\n"
    "💪 Qui si cresce con impegno e determinazione."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        add_user_if_needed(update.effective_user)
    kb = menu_keyboard()
    try:
        if WELCOME_PHOTO_URL:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=WELCOME_PHOTO_URL,
                caption=WELCOME_TEXT,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        else:
            await update.effective_message.reply_text(WELCOME_TEXT, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        logger.exception("Errore /start: %s", e)
        await update.effective_message.reply_text("👋 Benvenuto! Usa i pulsanti qui sotto.", reply_markup=kb)

# ===== COMANDI =====
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "ℹ️ Comandi:\n"
        "/start — benvenuto + menu\n"
        "/utenti — totale utenti\n"
        "/backup_db — invia DB (admin)\n"
        "/ultimo_backup — invia l'ultimo backup (admin)\n"
        "/whoami — il tuo user_id\n"
        "/ping — test\n"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("🏓 Pong!")

async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = get_user_count()
    await update.effective_message.reply_text(f"👥 Utenti salvati: {count}")

# ===== BACKUP: job giornaliero + comandi =====
def _parse_backup_time(hhmm: str) -> dtime:
    try:
        hh, mm = hhmm.split(":")
        return dtime(hour=int(hh), minute=int(mm))
    except Exception:
        logger.warning("BACKUP_TIME non valido (%s), uso 03:00", hhmm)
        return dtime(hour=3, minute=0)

async def backup_job(context: ContextTypes.DEFAULT_TYPE):
    """Job giornaliero: copia users.db in ./data/backups/users_YYYYMMDD.db e notifica l'admin."""
    ensure_users_table()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    db_path = Path(DB_FILE)
    if not db_path.exists():
        logger.error("Backup saltato: database non trovato (%s).", db_path)
        # Notifica admin se esiste
        if ADMIN_ID is not None:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"⚠️ Backup saltato: DB non trovato: `{db_path}`",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
        return

    timestamp = datetime.now().strftime("%Y%m%d")
    backup_path = BACKUP_DIR / f"users_{timestamp}.db"

    try:
        shutil.copyfile(db_path, backup_path)
        size = backup_path.stat().st_size
        logger.info("💾 Backup creato: %s (%d B)", backup_path, size)

        # Notifica admin
        if ADMIN_ID is not None:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"✅ Backup giornaliero creato: `{backup_path.name}` ({size} B)\nUsa /ultimo_backup per scaricarlo.",
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.warning("Impossibile inviare notifica admin: %s", e)
    except Exception as e:
        logger.error("Errore durante il backup: %s", e)
        if ADMIN_ID is not None:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"❌ Errore durante il backup: `{e}`",
                    parse_mode="Markdown",
                )
            except Exception:
                pass

async def backup_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia manualmente il file users.db"""
    if not await require_admin(update):
        return
    db_path = Path(DB_FILE)
    if not db_path.exists():
        await update.effective_message.reply_text("❌ Database non trovato.")
        return
    await update.effective_message.reply_document(
        document=InputFile(str(db_path)),
        filename="users.db",
        caption="🗂️ Backup manuale del database."
    )

async def ultimo_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia l'ultimo backup giornaliero disponibile"""
    if not await require_admin(update):
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backups = sorted(BACKUP_DIR.glob("users_*.db"), reverse=True)
    if not backups:
        await update.effective_message.reply_text("⚠️ Nessun backup giornaliero trovato.")
        return
    latest = backups[0]
    await update.effective_message.reply_document(
        document=InputFile(str(latest)),
        filename=latest.name,
        caption=f"📦 Ultimo backup giornaliero: {latest.name}"
    )
    logger.info("Ultimo backup inviato: %s", latest)

# ===== MAIN =====
def main():
    if not BOT_TOKEN:
        raise SystemExit("❌ Imposta BOT_TOKEN nelle variabili d'ambiente.")

    ensure_users_table()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Pulisce eventuali update pendenti
    import asyncio as _asyncio
    _asyncio.get_event_loop().run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))

    # Comandi
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("backup_db", backup_db))
    app.add_handler(CommandHandler("ultimo_backup", ultimo_backup))

    # Pianificazione backup giornaliero
    tz = ZoneInfo(BACKUP_TZ)
    hhmm = _parse_backup_time(BACKUP_TIME)
    app.job_queue.run_daily(
        backup_job,
        time=hhmm,
        days=(0, 1, 2, 3, 4, 5, 6),  # tutti i giorni
        name="daily_db_backup",
        timezone=tz,
    )
    logger.info("🕐 Backup giornaliero pianificato alle %s (%s).", BACKUP_TIME, BACKUP_TZ)

    logger.info("🚀 Bot avviato.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()