# =====================================================
# bot2.py — BPFAM1 BOT (PTB v21+)
# - Polling stabile (nessun conflict/loop error)
# - Webhook guard all'avvio
# - Welcome con immagine + bottone
# - DB utenti + comandi admin
# - Backup giornaliero tramite JobQueue (no asyncio manuale)
# =====================================================

import os
import sqlite3
import logging
import shutil
from datetime import datetime, time as dtime
from pathlib import Path

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    JobQueue,
)
import telegram.error as tgerr

VERSION = "2.3-jobqueue"

# ---------- LOG ----------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("bpfam1")

# ---------- ENV ----------
BOT_TOKEN    = os.environ.get("BOT_TOKEN")              # token @Bpfam1bot
ADMIN_ID     = int(os.environ.get("ADMIN_ID", "8033084779"))

DB_FILE      = os.environ.get("DB_FILE", "./data/users_bot2.db")
BACKUP_DIR   = os.environ.get("BACKUP_DIR", "./backup_bot2")
BACKUP_TIME  = os.environ.get("BACKUP_TIME", "03:00")   # HH:MM locale

WELCOME_PHOTO_URL = os.environ.get(
    "WELCOME_PHOTO_URL",
    "https://i.postimg.cc/hPgZxyhz/5-F5-DFE41-C80D-4-FC2-B4-F6-D1058440-B1.jpg",
)
WELCOME_TITLE = os.environ.get(
    "WELCOME_TITLE",
    "🇮🇹🇪🇸🇺🇸🇲🇦 BPFAM-UFFICIALE420🌐",
)
BUTTON_TEXT = os.environ.get("BUTTON_TEXT", "Accesso e menù 📋")
BUTTON_URL  = os.environ.get("BUTTON_URL",  "https://t.me/Bpfarmbot")

# ---------- DB ----------
def init_db():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name  TEXT,
            joined_utc TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_user_if_new(u):
    if not u: return
    conn = sqlite3.connect(DB_FILE)
    cur  = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE user_id=?", (u.id,))
    ok = cur.fetchone()
    if not ok:
        cur.execute(
            "INSERT INTO users VALUES (?,?,?,?,?)",
            (u.id, u.username or "", u.first_name or "", u.last_name or "",
             datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
    conn.close()

def count_users() -> int:
    conn = sqlite3.connect(DB_FILE); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    n = int(cur.fetchone()[0]); conn.close()
    return n

def export_users_csv(path: Path):
    conn = sqlite3.connect(DB_FILE); cur = conn.cursor()
    cur.execute("SELECT user_id,username,first_name,last_name,joined_utc FROM users ORDER BY joined_utc DESC")
    rows = cur.fetchall(); conn.close()

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id","username","first_name","last_name","joined_utc"])
        w.writerows(rows)

def backup_database() -> Path:
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = Path(BACKUP_DIR) / f"users_backup_{ts}.sqlite3"
    shutil.copy2(DB_FILE, dest)
    return dest

# ---------- HANDLERS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user_if_new(update.effective_user)

    caption = (
        f"{WELCOME_TITLE}\n\n"
        "🏆 Benvenuto nel bot ufficiale di BPFARM!\n"
        "⚡ Serietà e rispetto sono la nostra identità.\n"
        "💪 Qui si cresce con impegno e determinazione."
    )
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(BUTTON_TEXT, url=BUTTON_URL)]]
    )

    try:
        await update.effective_message.reply_photo(
            photo=WELCOME_PHOTO_URL,
            caption=caption,
            reply_markup=keyboard,
        )
    except tgerr.BadRequest:
        await update.effective_message.reply_text(caption, reply_markup=keyboard)

async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.effective_message.reply_text(f"👥 Utenti totali: {count_users()}")

async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    csv_path = Path(BACKUP_DIR) / f"users_export_{ts}.csv"
    export_users_csv(csv_path)
    await update.effective_message.reply_document(
        document=InputFile(csv_path, filename=csv_path.name),
        caption="Export CSV completato ✅",
    )

async def backup_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not Path(DB_FILE).exists():
        await update.effective_message.reply_text("DB non trovato.")
        return
    dest = backup_database()
    await update.effective_message.reply_document(
        document=InputFile(open(dest, "rb"), filename=dest.name),
        caption=f"Backup creato: {dest.name}",
    )

# ---------- JOBS ----------
async def backup_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        if Path(DB_FILE).exists():
            dest = backup_database()
            log.info(f"[JOB BACKUP] creato {dest}")
        else:
            log.warning("[JOB BACKUP] DB non trovato")
    except Exception as e:
        log.exception(f"[JOB BACKUP] errore: {e}")

def parse_backup_time(txt: str) -> dtime:
    try:
        h, m = txt.strip().split(":")
        return dtime(int(h), int(m))
    except Exception:
        return dtime(3, 0)

# ---------- MAIN ----------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN mancante nelle ENV")

    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CommandHandler("backup_db", backup_now))

    # Post-init: togli webhook e attiva backup giornaliero
    async def _post_init(application):
        # Webhook guard
        try:
            await application.bot.delete_webhook(drop_pending_updates=True)
            log.info("[GUARD] webhook rimosso + pending updates droppati")
        except Exception as e:
            log.warning(f"[GUARD] delete_webhook fallito: {e}")

        # JobQueue (nessun asyncio manuale)
        bt = parse_backup_time(BACKUP_TIME)
        application.job_queue.run_daily(backup_job, time=bt, name="daily_backup")
        log.info(f"[JOB] backup giornaliero schedulato alle {bt.strftime('%H:%M')}")

    app.post_init = _post_init

    log.info(f"🚀 Avvio BPFAM1 BOT v{VERSION}")
    # run_polling gestisce internamente il loop: NIENTE asyncio.run / get_event_loop
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()