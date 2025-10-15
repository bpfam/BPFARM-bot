# =====================================================
# bot.py — BPFAM BOT (v21+)
# Safe Polling + Webhook guard + Admin + Backup
# =====================================================

import os
import sqlite3
import logging
import shutil
import asyncio as aio
import time as pytime
import csv
from datetime import datetime, timezone, time as dtime, timedelta
from pathlib import Path
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import telegram.error as tgerr

VERSION = "1.7-bot2-safe"

# ===== LOGGING =====
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bpfam-bot")

# ===== ENV =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_FILE = os.environ.get("DB_FILE", "./data/users_bot2.db")
BACKUP_DIR = os.environ.get("BACKUP_DIR", "./backup_bot2")
BACKUP_TIME = os.environ.get("BACKUP_TIME", "03:00")

ADMIN_ID_ENV = os.environ.get("ADMIN_ID", "8033084779")
try:
    ADMIN_ID = int(ADMIN_ID_ENV)
except Exception:
    ADMIN_ID = None

WELCOME_TITLE = os.environ.get("WELCOME_TITLE", "🇮🇹🇪🇸🇺🇸🇲🇦 BPFAM-UFFICIALE420🌐")
WELCOME_PHOTO_URL = os.environ.get("WELCOME_PHOTO_URL")
BUTTON_TEXT = os.environ.get("BUTTON_TEXT", "Accesso e menù 📋")
BUTTON_URL  = os.environ.get("BUTTON_URL",  "https://t.me/Bpfarmbot")

# ===== STATE =====
task_lock = aio.Lock()
startup_ts = pytime.time()

# ===== DB =====
def init_db():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            joined_utc TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_user_if_new(user):
    if not user: return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE user_id=?", (user.id,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users VALUES (?,?,?,?,?)",
            (user.id, user.username or "", user.first_name or "", user.last_name or "",
             datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
    conn.close()

def get_user_count():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    n = cur.fetchone()[0]
    conn.close()
    return int(n)

def fetch_all_users():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT user_id,username,first_name,last_name,joined_utc FROM users ORDER BY joined_utc DESC")
    rows = cur.fetchall()
    conn.close()
    return rows

def backup_database():
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = Path(BACKUP_DIR) / f"users_backup_{ts}.sqlite3"
    shutil.copy2(DB_FILE, dest)
    return dest

# ===== UTILS =====
def is_admin(update: Update) -> bool:
    u = update.effective_user
    return bool(u and ADMIN_ID and u.id == ADMIN_ID)

def human_uptime():
    secs = int(pytime.time() - startup_ts)
    return str(timedelta(seconds=secs))

def parse_backup_time():
    try:
        h, m = BACKUP_TIME.strip().split(":")
        return dtime(int(h), int(m))
    except Exception:
        return dtime(3, 0)

async def daily_backup_loop(app):
    await app.wait_until_ready()
    while True:
        bt = parse_backup_time()
        now = datetime.now()
        tgt = datetime.combine(now.date(), bt)
        if tgt <= now:
            tgt += timedelta(days=1)
        await aio.sleep((tgt - now).total_seconds())
        try:
            async with task_lock:
                if Path(DB_FILE).exists():
                    dest = backup_database()
                    logger.info(f"[BACKUP] creato: {dest}")
        except Exception as e:
            logger.exception(f"[BACKUP] errore: {e}")

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user_if_new(update.effective_user)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(BUTTON_TEXT, url=BUTTON_URL)]])
    caption = (
        f"{WELCOME_TITLE}\n\n"
        "🏆 Benvenuto nel bot ufficiale di BPFARM!\n\n"
        "⚡ Serietà e rispetto sono la nostra identità.\n"
        "💪 Qui si cresce con impegno e determinazione."
    )
    msg = update.effective_message
    if WELCOME_PHOTO_URL:
        try:
            await msg.reply_photo(photo=WELCOME_PHOTO_URL, caption=caption, reply_markup=keyboard)
            return
        except Exception as e:
            logger.warning(f"[WELCOME] foto non inviata: {e}")
    await msg.reply_text(caption, reply_markup=keyboard)

async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    await update.effective_message.reply_text(f"👥 Utenti totali: {get_user_count()}")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    lines = ["user_id,username,first_name,last_name,joined_utc"]
    for r in fetch_all_users():
        lines.append(",".join([str(r[0]), r[1] or "", r[2] or "", r[3] or "", r[4] or ""]))
    buf = BytesIO("\n".join(lines).encode("utf-8"))
    await update.effective_message.reply_document(
        document=InputFile(buf, filename="users_list.txt"),
        caption=f"Lista utenti ({len(lines)-1} righe)"
    )

async def export_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    import csv as _csv
    buf = BytesIO()
    w = _csv.writer(buf)
    w.writerow(["user_id","username","first_name","last_name","joined_utc"])
    for r in fetch_all_users():
        w.writerow([r[0], r[1] or "", r[2] or "", r[3] or "", r[4] or ""])
    buf.seek(0)
    await update.effective_message.reply_document(
        document=InputFile(buf, filename="users_export.csv"),
        caption="Export CSV completato"
    )

async def backup_db_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    async with task_lock:
        if not Path(DB_FILE).exists():
            await update.effective_message.reply_text("DB non trovato.")
            return
        dest = backup_database()
        await update.effective_message.reply_document(
            document=InputFile(open(dest, "rb"), filename=dest.name),
            caption=f"Backup creato: {dest.name}"
        )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    text = " ".join(context.args) if context.args else (
        update.effective_message.reply_to_message.text if update.effective_message.reply_to_message else None
    )
    if not text:
        await update.effective_message.reply_text("Uso: /broadcast <messaggio> (o rispondi a un messaggio)")
        return
    async with task_lock:
        ok = ko = 0
        for uid, *_ in fetch_all_users():
            try:
                await context.bot.send_message(uid, text)
                ok += 1
                await aio.sleep(0.05)
            except Exception:
                ko += 1
        await update.effective_message.reply_text(f"Broadcast finito ✅\nInviati: {ok}\nFalliti: {ko}")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    tok = BOT_TOKEN or ""
    masked = f"{tok[:6]}…{tok[-6:]}" if len(tok) > 12 else "n/a"
    await update.effective_message.reply_text(
        "🛰️ STATUS\n"
        f"Versione: {VERSION}\n"
        f"Uptime: {human_uptime()}\n"
        f"Utenti: {get_user_count()}\n"
        f"DB: {DB_FILE}\n"
        f"Backup dir: {BACKUP_DIR}\n"
        f"Backup time: {BACKUP_TIME}\n"
        f"Token: {masked}\n"
    )

# ===== MAIN (SAFE) =====
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN mancante nelle ENV")

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("list", list_users))
    app.add_handler(CommandHandler("export", export_csv))
    app.add_handler(CommandHandler("backup_db", backup_db_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("status", status))

    app.create_task(daily_backup_loop(app))

    async def _startup(_app):
        # 1) Forza lo spegnimento di QUALSIASI webhook attivo su questo token
        try:
            await _app.bot.delete_webhook(drop_pending_updates=True)
            logger.info("[GUARD] webhook rimosso e pending updates droppati")
        except Exception as e:
            logger.warning(f"[GUARD] delete_webhook fallito: {e}")

        # 2) Log sicuro del token (prime/ultime cifre) per verifiche su Render
        tok = BOT_TOKEN
        masked = f"{tok[:6]}…{tok[-6:]}" if len(tok) > 12 else "n/a"
        logger.info(f"[START] Avvio polling con token={masked}")

    app.post_init = _startup  # eseguito prima dell’avvio

    logger.info("Avvio polling SAFE…")
    app.run_polling(
        close_loop=False,
        drop_pending_updates=True,     # 2) niente update vecchi
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == "__main__":
    main()