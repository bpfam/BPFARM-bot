# =====================================================
# bot.py — BPFARM BOT (python-telegram-bot v21+)
# Anti-conflict strong + Webhook guard + Backup giornaliero
# Admin blindati + Pulsanti dinamici (cartelle personalizzate)
# =====================================================

import os
import sqlite3
import logging
import shutil
import asyncio as aio
import time as pytime
import csv
from datetime import datetime, timezone, time as dtime, timedelta, date
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, filters
import telegram.error as tgerr

VERSION = "1.6-admin"

# ===== LOGGING =====
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bpfarm-bot")

# ===== CONFIG =====
BOT_TOKEN   = os.environ.get("BOT_TOKEN")
DB_FILE     = os.environ.get("DB_FILE", "./data/users.db")
BACKUP_DIR  = os.environ.get("BACKUP_DIR", "./backup")
BACKUP_TIME = os.environ.get("BACKUP_TIME", "03:00")
ADMIN_ID    = int(os.environ.get("ADMIN_ID", "8033084779"))

# Immagine di benvenuto
PHOTO_URL = os.environ.get(
    "PHOTO_URL",
    "https://i.postimg.cc/ZRVjp1w5/5-F5-DFE41-C80-D-4-FC2-B4-F6-D105844664-B3.jpg",
)

# ===== PULSANTI DINAMICI =====
def _load_dynamic_buttons():
    buttons = []
    for i in range(1, 13):
        label = os.environ.get(f"BTN{i}_LABEL", "").strip()
        url   = os.environ.get(f"BTN{i}_URL", "").strip()
        if label and url:
            buttons.append((label, url))
    return buttons

DYNAMIC_BUTTONS = _load_dynamic_buttons()

def _user_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for label, url in DYNAMIC_BUTTONS:
        rows.append([InlineKeyboardButton(label, url=url)])  # 1 per riga
    if not rows:
        rows = [[InlineKeyboardButton("📂 Nessuna cartella configurata", url="https://t.me/")]]
    return InlineKeyboardMarkup(rows)

# ===== DATABASE =====
def init_db():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            first_name  TEXT,
            last_name   TEXT,
            joined      TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_user(user_id: int, username: str, first_name: str, last_name: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, joined)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, username, first_name, last_name, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()

def count_users() -> int:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    n = cur.fetchone()[0]
    conn.close()
    return n

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, first_name, last_name, joined FROM users ORDER BY joined ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

# ===== UTILS =====
def _parse_backup_time(hhmm: str) -> dtime:
    try:
        h, m = map(int, hhmm.split(":"))
        return dtime(hour=h, minute=m)
    except Exception:
        return dtime(hour=3, minute=0)

def _next_backup_utc() -> datetime:
    run_t = _parse_backup_time(BACKUP_TIME)
    now = datetime.now(timezone.utc)
    candidate = datetime.combine(date.today(), run_t, tzinfo=timezone.utc)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate

def _last_backup_file() -> Path | None:
    p = Path(BACKUP_DIR)
    if not p.exists():
        return None
    files = sorted(p.glob("*.db"), reverse=True)
    return files[0] if files else None

def _is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

async def _deny_non_admin(update: Update, text="❌ Comando riservato all’amministratore."):
    try:
        if update.message:
            await update.message.reply_text(text)
        elif update.callback_query:
            await update.callback_query.answer(text, show_alert=True)
    except Exception:
        pass

# ===== HANDLERS PUBBLICI =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        add_user(user.id, user.username or "", user.first_name or "", user.last_name or "")

    caption = (
        "🏆 Benvenuto nel bot ufficiale di <b>BPFARM</b>!\n"
        "⚡ Serietà e rispetto sono la nostra identità.\n"
        "💪 Qui si cresce con impegno e determinazione."
    )

    try:
        await update.message.reply_photo(photo=PHOTO_URL, caption=caption, parse_mode="HTML", reply_markup=_user_keyboard())
    except Exception:
        await update.message.reply_text(caption, parse_mode="HTML", reply_markup=_user_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Comandi disponibili:\n"
        "/start – Benvenuto + cartelle\n"
        "/help – Questo aiuto\n"
        "/ping – Test rapido\n"
        "/utenti – Numero utenti registrati\n"
    )
    if _is_admin(update.effective_user.id):
        text += (
            "\nSolo Admin:\n"
            "/status – Stato del bot\n"
            "/backup – Backup manuale\n"
            "/test_backup – Backup ora\n"
            "/ultimo_backup – Invia ultimo backup\n"
            "/list – Elenco utenti\n"
            "/export – CSV utenti\n"
            "/broadcast <testo> – Messaggio a tutti\n"
        )
    await update.message.reply_text(text)

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong! Il bot è attivo.")

async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"👥 Utenti registrati: {count_users()}")

# ===== ADMIN =====
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return await _deny_non_admin(update)
    now_utc = datetime.now(timezone.utc)
    next_bu = _next_backup_utc()
    last = _last_backup_file()
    last_line = f"📦 Ultimo backup: {last.name}" if last else "📦 Ultimo backup: nessuno"
    await update.message.reply_text(
        f"🔎 Stato bot\n• Versione: {VERSION}\n• Ora server (UTC): {now_utc:%Y-%m-%d %H:%M:%S}\n• Prossimo backup (UTC): {next_bu:%Y-%m-%d %H:%M}\n• Utenti: {count_users()}\n{last_line}"
    )

# ===== BACKUP =====
async def backup_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = Path(BACKUP_DIR) / f"backup_{ts}.db"
        shutil.copy2(DB_FILE, backup_path)
        os.chmod(backup_path, 0o600)
        if ADMIN_ID:
            await context.bot.send_document(chat_id=ADMIN_ID, document=InputFile(str(backup_path)))
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"✅ Backup completato: {backup_path.name}")
    except Exception as e:
        logger.error(f"Errore backup: {e}")

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return await _deny_non_admin(update)
    await backup_job(context)
    await update.message.reply_text("💾 Backup manuale completato (inviato all’admin).")

async def ultimo_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return await _deny_non_admin(update)
    last = _last_backup_file()
    if not last:
        return await update.message.reply_text("Nessun backup trovato.")
    await context.bot.send_document(chat_id=ADMIN_ID, document=InputFile(str(last)))
    await update.message.reply_text(f"📦 Ultimo backup inviato all’admin ({last.name}).")

async def test_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return await _deny_non_admin(update)
    await backup_job(context)
    await update.message.reply_text("✅ Backup di test completato.")

# ===== ADMIN: LIST / EXPORT / BROADCAST =====
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return await _deny_non_admin(update)
    users = get_all_users()
    if not users:
        return await update.message.reply_text("📋 Nessun utente registrato.")
    lines = [f"{i+1}. @{u['username'] or '-'} ({u['user_id']})" for i, u in enumerate(users)]
    text = "\n".join(lines)
    await update.message.reply_text(f"📋 Utenti ({len(users)}):\n{text[:3500]}")

async def export_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return await _deny_non_admin(update)
    users = get_all_users()
    Path("./exports").mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    csv_path = Path("./exports") / f"users_export_{ts}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "username", "first_name", "last_name", "joined"])
        for u in users:
            w.writerow([u["user_id"], u["username"] or "", u["first_name"] or "", u["last_name"] or "", u["joined"] or ""])
    os.chmod(csv_path, 0o600)
    await context.bot.send_document(chat_id=ADMIN_ID, document=InputFile(str(csv_path)))
    await update.message.reply_text(f"📤 Export utenti ({len(users)} record) inviato all’amministratore.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return await _deny_non_admin(update)
    text = " ".join(context.args).strip()
    if not text:
        return await update.message.reply_text("ℹ️ Usa: /broadcast <testo>")
    users = get_all_users()
    ok = fail = 0
    await update.message.reply_text(f"📣 Invio a {len(users)} utenti…")
    for u in users:
        try:
            await context.bot.send_message(chat_id=u["user_id"], text=text)
            ok += 1
            await aio.sleep(0.05)
        except Exception:
            fail += 1
    await update.message.reply_text(f"✅ Inviati: {ok} | ❌ Errori: {fail}")

# ===== GUARDIANI =====
async def webhook_guard(context: ContextTypes.DEFAULT_TYPE):
    try:
        info = await context.bot.get_webhook_info()
        if info and info.url:
            await context.bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.debug(f"Webhook guard error: {e}")

def anti_conflict_prepare(app):
    loop = aio.get_event_loop()
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
    logger.info("🔧 Webhook rimosso + pending updates droppati.")
    for i in range(6):
        try:
            loop.run_until_complete(app.bot.get_updates(timeout=1))
            return
        except tgerr.Conflict:
            loop.run_until_complete(aio.sleep(10))
        except Exception:
            loop.run_until_complete(aio.sleep(3))

# ===== MAIN =====
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    anti_conflict_prepare(app)

    # Comandi pubblici
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("utenti", utenti))

    # Admin filtrati
    F = filters.User(user_id=ADMIN_ID)
    app.add_handler(CommandHandler("status", status_command, filters=F))
    app.add_handler(CommandHandler("backup", backup_command, filters=F))
    app.add_handler(CommandHandler("test_backup", test_backup, filters=F))
    app.add_handler(CommandHandler("ultimo_backup", ultimo_backup, filters=F))
    app.add_handler(CommandHandler("list", list_users, filters=F))
    app.add_handler(CommandHandler("export", export_users, filters=F))
    app.add_handler(CommandHandler("broadcast", broadcast, filters=F))

    # Job periodici
    app.job_queue.run_repeating(webhook_guard, interval=600, first=60)
    app.job_queue.run_daily(backup_job, time=_parse_backup_time(BACKUP_TIME))

    logger.info("🚀 Bot avviato (polling mode).")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()