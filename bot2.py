# =====================================================
# bot2.py — BPFAM1 BOT (PTB v21+)
# - Polling stabile (senza conflitti / loop error)
# - Webhook guard
# - Solo immagine + titolo + pulsanti (no testo extra)
# - DB utenti + comandi admin
# - Backup giornaliero con JobQueue
# - Anti-share: blocco inoltro/salvataggio e blocco invii non-admin
# - /restore_db: ripristino DB via reply a file .db
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
    MessageHandler,
    filters,
)
import telegram.error as tgerr

VERSION = "2.5-antishare-restore"

# ---------- LOG ----------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("bpfam1")

# ---------- ENV ----------
BOT_TOKEN    = os.environ.get("BOT_TOKEN")
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

# ---------- HANDLERS PUBBLICI ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user_if_new(update.effective_user)

    caption = f"{WELCOME_TITLE}"
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(BUTTON_TEXT, url=BUTTON_URL)]]
    )

    try:
        await update.effective_message.reply_photo(
            photo=WELCOME_PHOTO_URL,
            caption=caption,
            reply_markup=keyboard,
            protect_content=True,            # <-- anti-forward/salvataggio
        )
    except tgerr.BadRequest:
        await update.effective_message.reply_text(
            caption,
            reply_markup=keyboard,
            protect_content=True,            # <-- anti-forward/salvataggio
        )

# ---------- ANTI-SHARE / BLOCCO INVII NON-ADMIN ----------
async def block_non_admin_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elimina qualsiasi messaggio inviato da non-admin (testo, foto, video, sticker, contatti, ecc.)."""
    user = update.effective_user
    if not user or user.id == ADMIN_ID:
        return
    chat = update.effective_chat
    msg  = update.effective_message
    try:
        await context.bot.delete_message(chat_id=chat.id, message_id=msg.id)
    except Exception:
        pass

# ---------- ADMIN ----------
async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.effective_message.reply_text(f"👥 Utenti totali: {count_users()}", protect_content=True)

async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    csv_path = Path(BACKUP_DIR) / f"users_export_{ts}.csv"
    export_users_csv(csv_path)
    await update.effective_message.reply_document(
        document=InputFile(csv_path, filename=csv_path.name),
        caption="Export CSV completato ✅",
        protect_content=True,
    )

async def backup_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not Path(DB_FILE).exists():
        await update.effective_message.reply_text("DB non trovato.", protect_content=True)
        return
    dest = backup_database()
    await update.effective_message.reply_document(
        document=InputFile(open(dest, "rb"), filename=dest.name),
        caption=f"Backup creato: {dest.name}",
        protect_content=True,
    )

# ---------- /restore_db ----------
async def restore_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ripristina il DB da un file .db inviato come documento e richiamato via reply."""
    if update.effective_user.id != ADMIN_ID: return

    msg = update.effective_message
    if not msg or not msg.reply_to_message or not msg.reply_to_message.document:
        await update.effective_message.reply_text(
            "📦 Per ripristinare:\n"
            "1) Invia un file **.db** al bot (come *documento*)\n"
            "2) Fai **Rispondi** a quel messaggio e invia `/restore_db`",
            protect_content=True,
        )
        return

    doc = msg.reply_to_message.document
    if not (doc.file_name and doc.file_name.endswith(".db")):
        await update.effective_message.reply_text(
            "❌ Il file deve avere estensione **.db**",
            protect_content=True,
        )
        return

    # Scarica in tmp
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        tmp_path = Path(BACKUP_DIR) / f"restore_tmp_{doc.file_unique_id}.db"
        tgfile = await doc.get_file()
        await tgfile.download_to_drive(custom_path=str(tmp_path))
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Errore download file: {e}", protect_content=True)
        return

    # Copia di sicurezza
    try:
        safety_copy = Path(BACKUP_DIR) / f"pre_restore_{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak"
        if Path(DB_FILE).exists():
            shutil.copy2(DB_FILE, safety_copy)
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Errore copia di sicurezza: {e}", protect_content=True)
        try:
            if tmp_path.exists(): tmp_path.unlink()
        except Exception:
            pass
        return

    # Sostituzione DB
    try:
        Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tmp_path, DB_FILE)
        await update.effective_message.reply_text("✅ Database ripristinato. Usa /utenti per verificare.", protect_content=True)
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Errore ripristino DB: {e}", protect_content=True)
    finally:
        try:
            if tmp_path.exists(): tmp_path.unlink()
        except Exception:
            pass

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

    # Comandi pubblici / admin
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CommandHandler("backup_db", backup_now))
    app.add_handler(CommandHandler("restore_db", restore_db))   # <-- nuovo

    # Anti-share: blocca TUTTO ciò che non è comando dai non-admin
    app.add_handler(MessageHandler(~filters.COMMAND, block_non_admin_messages))

    async def _post_init(application):
        # Webhook guard
        try:
            await application.bot.delete_webhook(drop_pending_updates=True)
            log.info("[GUARD] webhook rimosso + pending updates droppati")
        except Exception as e:
            log.warning(f"[GUARD] delete_webhook fallito: {e}")

        # Job backup giornaliero
        bt = parse_backup_time(BACKUP_TIME)
        application.job_queue.run_daily(backup_job, time=bt, name="daily_backup")
        log.info(f"[JOB] backup giornaliero schedulato alle {bt.strftime('%H:%M')}")

    app.post_init = _post_init

    log.info(f"🚀 Avvio BPFAM1 BOT v{VERSION}")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()