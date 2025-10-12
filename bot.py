# bot.py – Telegram Bot (python-telegram-bot v21+)
import os
import sqlite3
import datetime  # per orario job
from datetime import datetime as dt  # per timestamp utenti
from pathlib import Path
import logging
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    JobQueue,  # <-- usiamo JobQueue esplicitamente
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

# Owner per comandi di backup
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))  # imposta il tuo user id Telegram
TIMEZONE = os.environ.get("TZ", "Europe/Rome")

# Immagine opzionale di benvenuto (usa un link diretto .jpg/.png)
PHOTO_URL = os.environ.get(
    "PHOTO_URL",
    "https://i.postimg.cc/hPgZxyhz/5-F5-DFE41-C80D-4-FC2-B4-F6-D1058440-B1.jpg",
)

# ======== BACKUP UTILS ========
from backup_utils import make_db_backup, export_users_csv

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
        (user.id, user.username, user.first_name, dt.utcnow().isoformat()),
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

# ======== HANDLERS PUBBLICI ========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    add_user(update.effective_user)
    message_text = (
        "🏆 *Benvenuto nel bot ufficiale di BPFAM!*\n\n"
        "⚡ Serietà e rispetto sono la nostra identità.\n"
        "💪 Qui si cresce con impegno e determinazione."
    )
    keyboard = [
        [
            InlineKeyboardButton("📖 Menu", url="https://t.me/+w3_ePB2hmVwxNmNk"),
            InlineKeyboardButton("💥 Recensioni", url="https://t.me/+fIQWowFYHWZjZWU0"),
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
        "/backup — Invia backup database (owner)\n"
        "/export_users — Esporta utenti in CSV (owner)\n"
        "/help — Aiuto"
    )

# ======== HANDLERS BACKUP (solo owner) ========
async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else 0
    if OWNER_ID and user_id != OWNER_ID:
        return await update.effective_message.reply_text("Solo l'owner può usare questo comando.")
    try:
        zip_path = make_db_backup()
        await update.effective_message.reply_document(
            document=open(zip_path, "rb"),
            filename=os.path.basename(zip_path),
            caption="Backup database eseguito ✅"
        )
    except Exception as e:
        await update.effective_message.reply_text(f"Errore backup: {e}")

async def export_users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else 0
    if OWNER_ID and user_id != OWNER_ID:
        return await update.effective_message.reply_text("Solo l'owner può usare questo comando.")
    try:
        csv_path = export_users_csv()
        await update.effective_message.reply_document(
            document=open(csv_path, "rb"),
            filename=os.path.basename(csv_path),
            caption="Export utenti (CSV) ✅"
        )
    except Exception as e:
        await update.effective_message.reply_text(f"Errore export: {e}")

# ======== MAIN ========
def main() -> None:
    if not BOT_TOKEN:
        logger.error("❌ ERRORE: Variabile d'ambiente BOT_TOKEN mancante")
        return

    init_db()

    # Costruiamo l'app
    builder = ApplicationBuilder().token(BOT_TOKEN)
    app = builder.build()

    # ✅ FIX job_queue: creazione manuale se mancante
    if not getattr(app, "job_queue", None):
        jq = JobQueue()
        jq.set_application(app)
        jq.initialize()        # prepara la coda
        app.job_queue = jq     # assegna all'app

    # Comandi pubblici
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("info", info_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    # Comandi owner
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("export_users", export_users_cmd))

    # ---- Backup automatico giornaliero alle 03:00 Europe/Rome ----
    async def scheduled_backup(context: ContextTypes.DEFAULT_TYPE):
        try:
            zip_path = make_db_backup()
            if OWNER_ID:
                await context.bot.send_document(
                    chat_id=OWNER_ID,
                    document=open(zip_path, "rb"),
                    filename=os.path.basename(zip_path),
                    caption="Backup automatico notturno ✅"
                )
        except Exception as e:
            if OWNER_ID:
                await context.bot.send_message(chat_id=OWNER_ID, text=f"Errore backup automatico: {e}")

    app.job_queue.run_daily(
        scheduled_backup,
        time=datetime.time(hour=3, minute=0, tzinfo=ZoneInfo(TIMEZONE)),
        name="daily_db_backup"
    )
    # ---------------------------------------------------------------

    logger.info("✅ Bot avviato con successo!")
    # run_polling avvierà anche la JobQueue se non già avviata
    app.run_polling()

if __name__ == "__main__":
    main()