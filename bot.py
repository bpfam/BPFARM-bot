# bot.py — BPFARM (python-telegram-bot v21+) con protezione anti-conflict
import os
import sqlite3
import logging
import shutil
import asyncio as aio
import time as pytime
from datetime import datetime, timezone, time as dtime
from pathlib import Path

from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import telegram.error as tgerr


# ========== LOGGING ==========
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bpfarm-bot")


# ========== CONFIG ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_FILE = os.environ.get("DB_FILE", "./data/users.db")
BACKUP_DIR = os.environ.get("BACKUP_DIR", "./backup")
BACKUP_TIME = os.environ.get("BACKUP_TIME", "03:00")  # HH:MM (ora del server: UTC su Render)

ADMIN_ID_ENV = os.environ.get("ADMIN_ID")
ADMIN_ID = int(ADMIN_ID_ENV) if ADMIN_ID_ENV and ADMIN_ID_ENV.isdigit() else None

# Immagine di benvenuto (link diretto .jpg/.png)
PHOTO_URL = os.environ.get(
    "PHOTO_URL",
    "https://i.postimg.cc/WbpGbTBH/5-F5-DFE41-C80-D-4-FC2-B4-F6-D105844664B3.jpg",
)


# ========== DATABASE ==========
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


# ========== COMANDI ==========
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


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Comandi disponibili:\n"
        "/start – Benvenuto con menu\n"
        "/help – Questo aiuto\n"
        "/utenti – Numero utenti registrati\n"
        "/backup – Backup manuale (solo admin)\n"
        "/ultimo_backup – Invia l’ultimo file di backup\n"
        "/test_backup – Esegue ora il job di backup (solo admin)"
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong!")


async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM utenti")
    count = cur.fetchone()[0]
    conn.close()
    await update.message.reply_text(f"👥 Utenti registrati: {count}")


# ========== BACKUP ==========
def _parse_backup_time(hhmm: str) -> dtime:
    try:
        h, m = map(int, hhmm.split(":"))
        return dtime(hour=h, minute=m)
    except Exception:
        return dtime(hour=3, minute=0)


async def backup_job(context: ContextTypes.DEFAULT_TYPE):
    """Backup automatico con notifica admin."""
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"backup_{ts}.db")
        shutil.copy2(DB_FILE, backup_path)
        logger.info(f"💾 Backup creato: {backup_path}")
        if ADMIN_ID:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"✅ Backup giornaliero completato.\n🕒 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n📦 {Path(backup_path).name}",
            )
    except Exception as e:
        logger.exception("Errore nel backup automatico")
        if ADMIN_ID:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Errore nel backup: {e}")


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ADMIN_ID and update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Solo l’amministratore può eseguire questa operazione.")
        return
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"manual_backup_{ts}.db")
        shutil.copy2(DB_FILE, backup_path)
        await update.message.reply_document(InputFile(backup_path), caption="💾 Backup manuale completato.")
        logger.info(f"💾 Backup manuale eseguito: {backup_path}")
    except Exception as e:
        logger.exception("Errore backup manuale")
        await update.message.reply_text(f"❌ Errore durante il backup manuale: {e}")


async def ultimo_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(BACKUP_DIR):
        await update.message.reply_text("Nessun backup trovato.")
        return
    files = sorted(Path(BACKUP_DIR).glob("*.db"), reverse=True)
    if not files:
        await update.message.reply_text("Nessun backup disponibile.")
        return
    ultimo = files[0]
    await update.message.reply_document(InputFile(ultimo), caption=f"📦 Ultimo backup: {ultimo.name}")


async def test_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if ADMIN_ID and update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Solo l’amministratore può eseguire questa operazione.")
        return
    await update.message.reply_text("⏳ Avvio backup di test…")
    await backup_job(context)
    await update.message.reply_text("✅ Test completato. Controlla messaggio all’admin e cartella backup.")


# ========== ANTI-CONFLICT ==========
def anti_conflict_prepare(app):
    """
    1) Elimina sempre il webhook e droppa gli update pendenti.
    2) Prova ad acquisire lo slot di polling; se trova Conflict, attende e ritenta.
    """
    loop = aio.get_event_loop()
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
    logger.info("🔧 Webhook rimosso + pending updates droppati.")

    for i in range(6):  # ~1 minuto di tentativi
        try:
            loop.run_until_complete(app.bot.get_updates(timeout=1))
            logger.info("✅ Slot di polling acquisito.")
            return
        except tgerr.Conflict as e:
            wait = 10
            logger.warning(f"⚠️ Conflict (tentativo {i+1}/6): {e}. Riprovo tra {wait}s…")
            loop.run_until_complete(aio.sleep(wait))
        except Exception as e:
            logger.warning(f"ℹ️ Attendo e riprovo get_updates… ({e})")
            loop.run_until_complete(aio.sleep(3))


# ========== MAIN ==========
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Anti-conflict all'avvio
    anti_conflict_prepare(app)

    # Comandi
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("ultimo_backup", ultimo_backup))
    app.add_handler(CommandHandler("test_backup", test_backup))

    # Schedula backup giornaliero (orario del server)
    hhmm = _parse_backup_time(BACKUP_TIME)
    app.job_queue.run_daily(backup_job, time=hhmm, days=(0, 1, 2, 3, 4, 5, 6), name="daily_db_backup")

    logger.info("🕒 Backup giornaliero pianificato (timezone server).")

    # Avvio con retry automatico se dovesse ricapitare un Conflict
    while True:
        try:
            logger.info("🚀 Bot avviato (polling).")
            app.run_polling(allowed_updates=Update.ALL_TYPES)
            break
        except tgerr.Conflict as e:
            logger.warning(f"⚠️ Conflict durante il polling: {e}. Pulisco webhook e riavvio tra 15s…")
            loop = aio.get_event_loop()
            loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
            pytime.sleep(15)
            continue


if __name__ == "__main__":
    main()