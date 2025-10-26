# =====================================================
# BPFARM BOT – v3.6 (python-telegram-bot v21+)
# ✅ Compatibile con Render (/data persistente)
# ✅ Auto-restore DB se mancante
# ✅ /restore_db (ripristino da file .db via reply)
# ✅ Anti-conflict (webhook guard + polling unico)
# ✅ Backup giornaliero automatico + manuale
# =====================================================

import os
import csv
import shutil
import logging
import sqlite3
import asyncio as aio
from pathlib import Path
from datetime import datetime, timezone, timedelta, date, time as dtime

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
import telegram.error as tgerr

VERSION = "3.6-render-autorestore"

# ---------------- LOG ----------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("bpfarm-bot")

# ---------------- ENV ----------------
def _txt(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    if not v:
        return default
    v = v.replace("\\n", "\n")
    if v.startswith("file://"):
        try:
            with open(v[7:], "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            log.warning(f"Impossibile leggere {key}: {e}")
    return v

BOT_TOKEN   = os.environ.get("BOT_TOKEN", "")
ADMIN_ID    = int(os.environ.get("ADMIN_ID", "0") or "0") or None

# ✅ Percorsi compatibili Render
DB_FILE     = os.environ.get("DB_FILE", "/data/users.db")
BACKUP_DIR  = os.environ.get("BACKUP_DIR", "/data/backups")
BACKUP_TIME = os.environ.get("BACKUP_TIME", "03:00")  # UTC

PHOTO_URL   = _txt("PHOTO_URL",
                   "https://i.postimg.cc/WbpGbTBH/5-F5-DFE41-C80-D-4-FC2-B4-F6-D105844664B3.jpg")
CAPTION_MAIN = _txt("CAPTION_MAIN",
                    "🏆 *Benvenuto nel bot ufficiale di BPFARM!*\n"
                    "⚡ Serietà e rispetto sono la nostra identità.\n"
                    "💪 Qui si cresce con impegno e determinazione.")

INFO_BANNER_URL = _txt("INFO_BANNER_URL",
                       "https://i.postimg.cc/m2JvXFcH/9-B509-E52-0-D6-A-4-B2-E-8-DE2-68-F81-B0-E9868.png")

PAGE_MAIN        = _txt("PAGE_MAIN", "")
PAGE_MENU        = _txt("PAGE_MENU", "📖 *Menù*\n\nScrivi qui il tuo menù completo.")
PAGE_SHIPSPAGNA  = _txt("PAGE_SHIPSPAGNA", "🇪🇸 *Ship-Spagna*\n\nInfo e regole spedizioni.")
PAGE_RECENSIONI  = _txt("PAGE_RECENSIONI", "🎇 *Recensioni*\n\n⭐️ “Ottimo servizio!”")
PAGE_POINTATTIVI = _txt("PAGE_POINTATTIVI", "📍🇮🇹 *Point Attivi*\n\n• Roma\n• Milano")

PAGE_CONTACTS_TEXT = _txt("PAGE_CONTACTS_TEXT", "💎 *BPFAM CONTATTI UFFICIALI* 💎")
PAGE_INFO_MENU     = _txt("PAGE_INFO_MENU", "ℹ️ *Info — Centro informativo BPFAM*")
PAGE_INFO_DELIVERY = _txt("PAGE_INFO_DELIVERY", "🚚 *Info Delivery*\n(Testo non impostato)")
PAGE_INFO_MEETUP   = _txt("PAGE_INFO_MEETUP", "🤝 *Info Meet-Up*\n(Testo non impostato)")
PAGE_INFO_POINT    = _txt("PAGE_INFO_POINT", "📍🇮🇹 *Info Point*\n(Testo non impostato)")

# ---------------- DB ----------------
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
    conn.commit(); conn.close()

def auto_restore_if_missing():
    """Se manca il DB, tenta il ripristino automatico dall'ultimo backup."""
    db = Path(DB_FILE)
    bdir = Path(BACKUP_DIR)
    if db.exists() or not bdir.exists():
        return
    backups = sorted(bdir.glob("*.db"), reverse=True)
    if backups:
        shutil.copy2(backups[0], db)
        log.info(f"Auto-restore DB da {backups[0].name}")

def add_user(u):
    if not u: return
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""INSERT OR IGNORE INTO users
                   (user_id, username, first_name, last_name, joined)
                   VALUES (?, ?, ?, ?, ?)""",
                (u.id, u.username, u.first_name, u.last_name,
                 datetime.now(timezone.utc).isoformat()))
    conn.commit(); conn.close()

def count_users() -> int:
    conn = sqlite3.connect(DB_FILE); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    n = cur.fetchone()[0]; conn.close(); return n

def get_all_users():
    conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, first_name, last_name, joined FROM users ORDER BY joined ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close(); return rows

# ---------------- UTILS ----------------
def is_admin(uid: int) -> bool:
    return ADMIN_ID is not None and uid == ADMIN_ID

def parse_hhmm(hhmm: str) -> dtime:
    try:
        h, m = map(int, hhmm.split(":")); return dtime(hour=h, minute=m)
    except Exception:
        return dtime(hour=3, minute=0)

def next_backup_utc() -> datetime:
    run_t = parse_hhmm(BACKUP_TIME)
    now = datetime.now(timezone.utc)
    cand = datetime.combine(date.today(), run_t, tzinfo=timezone.utc)
    return cand if cand > now else cand + timedelta(days=1)

def last_backup_file() -> Path|None:
    p = Path(BACKUP_DIR)
    if not p.exists(): return None
    files = sorted(p.glob("*.db"), reverse=True)
    return files[0] if files else None

# ---------------- KEYBOARDS ----------------
def kb_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Menù", callback_data="sec:menu")],
        [InlineKeyboardButton("SHIIP🇮🇹📦🇪🇺", callback_data="sec:ship"),
         InlineKeyboardButton("🎇 Recensioni", callback_data="sec:recs")],
        [InlineKeyboardButton("📲 Info-Contatti", callback_data="info:root"),
         InlineKeyboardButton("📍🇮🇹 Point Attivi", callback_data="sec:points")],
    ])

def kb_back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="home")]])

def kb_info_root() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Contatti", callback_data="contacts:open"),
         InlineKeyboardButton("ℹ️ Info", callback_data="info:menu")],
        [InlineKeyboardButton("🔙 Back", callback_data="home")]
    ])

def kb_info_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚚 Info Delivery", callback_data="info:delivery")],
        [InlineKeyboardButton("🤝 Info Meet-Up", callback_data="info:meetup")],
        [InlineKeyboardButton("📍🇮🇹 Info Point", callback_data="info:point")],
        [InlineKeyboardButton("🔙 Back", callback_data="info:root")]
    ])

# ---------------- HANDLERS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user(update.effective_user)
    try:
        await update.message.reply_photo(
            photo=PHOTO_URL, caption=CAPTION_MAIN,
            parse_mode="Markdown", protect_content=True
        )
    except Exception:
        await update.message.reply_text(
            CAPTION_MAIN, parse_mode="Markdown",
            disable_web_page_preview=True, protect_content=True
        )
    await update.message.reply_text(PAGE_MAIN or "\u2063", parse_mode="Markdown",
                                    disable_web_page_preview=True,
                                    reply_markup=kb_home(), protect_content=True)

async def cb_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q: return
    await q.answer()
    d = q.data
    chat_id = q.message.chat_id
    if d == "home":
        await q.message.edit_text(PAGE_MAIN, parse_mode="Markdown", reply_markup=kb_home()); return
    if d == "sec:menu":
        await q.message.edit_text(PAGE_MENU, parse_mode="Markdown", reply_markup=kb_back_home()); return
    if d == "sec:ship":
        await q.message.edit_text(PAGE_SHIPSPAGNA, parse_mode="Markdown", reply_markup=kb_back_home()); return
    if d == "sec:recs":
        await q.message.edit_text(PAGE_RECENSIONI, parse_mode="Markdown", reply_markup=kb_back_home()); return
    if d == "sec:points":
        await q.message.edit_text(PAGE_POINTATTIVI, parse_mode="Markdown", reply_markup=kb_back_home()); return
    if d == "info:root":
        await q.message.edit_caption(caption="ℹ️ Info BPFAM", reply_markup=kb_info_root()); return
    if d == "contacts:open":
        await q.message.edit_text(PAGE_CONTACTS_TEXT, parse_mode="Markdown",
                                  reply_markup=kb_back_home()); return
    if d == "info:menu":
        await q.message.edit_text(PAGE_INFO_MENU, parse_mode="Markdown",
                                  reply_markup=kb_info_menu()); return
    if d == "info:delivery":
        await q.message.edit_text(PAGE_INFO_DELIVERY, parse_mode="Markdown",
                                  reply_markup=kb_info_menu()); return
    if d == "info:meetup":
        await q.message.edit_text(PAGE_INFO_MEETUP, parse_mode="Markdown",
                                  reply_markup=kb_info_menu()); return
    if d == "info:point":
        await q.message.edit_text(PAGE_INFO_POINT, parse_mode="Markdown",
                                  reply_markup=kb_info_menu()); return

# ---------------- ADMIN ----------------
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    now_utc = datetime.now(timezone.utc)
    nxt = next_backup_utc()
    last = last_backup_file()
    await update.message.reply_text(
        f"🟢 BPFARM BOT v{VERSION}\n"
        f"• Ora server (UTC): {now_utc:%Y-%m-%d %H:%M:%S}\n"
        f"• Prossimo backup: {nxt:%Y-%m-%d %H:%M}\n"
        f"• Utenti registrati: {count_users()}\n"
        f"• Ultimo backup: {(last.name if last else 'nessuno')}",
        protect_content=True
    )

async def backup_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = Path(BACKUP_DIR) / f"backup_{ts}.db"
        shutil.copy2(DB_FILE, out)
        log.info(f"Backup completato: {out}")
    except Exception as e:
        log.exception("Errore backup giornaliero: %s", e)

async def restore_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = update.effective_message
    if not msg or not msg.reply_to_message or not msg.reply_to_message.document:
        await update.message.reply_text("📦 Rispondi a un file .db con /restore_db"); return
    doc = msg.reply_to_message.document
    if not doc.file_name.endswith(".db"):
        await update.message.reply_text("❌ Il file deve terminare con .db"); return
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    tmp = Path(BACKUP_DIR) / f"restore_{doc.file_unique_id}.db"
    file = await doc.get_file()
    await file.download_to_drive(custom_path=str(tmp))
    shutil.copy2(tmp, DB_FILE)
    tmp.unlink(missing_ok=True)
    await update.message.reply_text("✅ Database ripristinato con successo!")

# ---------------- ANTI-CONFLICT ----------------
def anti_conflict_prepare(app):
    loop = aio.get_event_loop()
    try:
        loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
        log.info("Webhook rimosso, polling libero.")
    except Exception as e:
        log.warning(f"delete_webhook err: {e}")

# ---------------- MAIN ----------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN mancante")

    auto_restore_if_missing()
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    anti_conflict_prepare(app)

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(cb_router))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("restore_db", restore_db))

    hhmm = parse_hhmm(BACKUP_TIME)
    now = datetime.now(timezone.utc)
    first_run = datetime.combine(now.date(), hhmm, tzinfo=timezone.utc)
    if first_run <= now:
        first_run += timedelta(days=1)
    app.job_queue.run_repeating(backup_job, interval=86400, first=first_run, name="daily_backup")

    log.info(f"🚀 BPFARM BOT avviato — v{VERSION}")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()