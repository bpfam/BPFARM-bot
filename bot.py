# =====================================================
# bot.py — BPFARM BOT (python-telegram-bot v21+)
# UI pulita: 1 messaggio "pannello" sempre editato (no spam)
# Foto iniziale separata (senza bottoni) + Menù con callback
# Paginazione per testi lunghi (◀ Menù ▶) in un solo messaggio
# Sezione 📍🇮🇹 Point Attivi | Backup | Admin | Anti-conflict | Webhook guard
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
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import telegram.error as tgerr

VERSION = "2.2-single-panel"

# ===== LOGGING =====
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bpfarm-bot")

# ===== CONFIG (Render ENV) =====
BOT_TOKEN   = os.environ.get("BOT_TOKEN")
DB_FILE     = os.environ.get("DB_FILE", "./data/users.db")
BACKUP_DIR  = os.environ.get("BACKUP_DIR", "./backup")
BACKUP_TIME = os.environ.get("BACKUP_TIME", "03:00")  # UTC su Render

ADMIN_ID_ENV = os.environ.get("ADMIN_ID")
ADMIN_ID = int(ADMIN_ID_ENV) if ADMIN_ID_ENV and ADMIN_ID_ENV.isdigit() else None

# Start: foto + caption breve
PHOTO_URL = os.environ.get(
    "PHOTO_URL",
    "https://i.postimg.cc/WbpGbTBH/5-F5-DFE41-C80-D-4-FC2-B4-F6-D105844664B3.jpg",
)
CAPTION_MAIN = os.environ.get(
    "CAPTION_MAIN",
    "🏆 *Benvenuto nel bot ufficiale di BPFARM!*\n"
    "⚡ Serietà e rispetto sono la nostra identità.\n"
    "💪 Qui si cresce con impegno e determinazione."
)

# ===== TESTI PAGINE (da ENV) =====
DEFAULT_MAIN = (
    "Scegli una sezione:\n"
    "• 🇪🇸 *Shiip-Spagna* — informazioni, regole, spedizioni\n"
    "• 🎇 *Recensioni* — feedback e testimonianze\n"
    "• 📲 *Info-Contatti* — contatti, help, note\n"
    "• 📍🇮🇹 *Point Attivi* — sedi e punti attivi"
)
DEFAULT_SHIP  = "🇪🇸 *Shiip-Spagna*\n\nScrivi qui info su spedizioni, regole, tempi, costi, FAQ…"
DEFAULT_REVIEW= "🎇 *Recensioni*\n\n⭐️ “Servizio top!”\n⭐️ “Sempre precisi e veloci!”"
DEFAULT_INFO  = "📲 *Info & Contatti*\n\n👤 Admin: @tuo_username\n🕒 Lun–Sab, 09:00–19:00"
DEFAULT_POINT = "📍🇮🇹 *Point Attivi*\n\n• Roma\n• Milano\n• Napoli\n• Torino"

def _normalize_env_text(v: str | None, default: str) -> str:
    if not v:
        return default
    v = v.replace("\\n", "\n")
    if v.startswith("file://"):
        try:
            with open(v[7:], "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Errore lettura {v}: {e}")
    return v

def _load_pages_from_env():
    return {
        "main":        _normalize_env_text(os.environ.get("PAGE_MAIN"),        DEFAULT_MAIN),
        "shipspagna":  _normalize_env_text(os.environ.get("PAGE_SHIPSPAGNA"),  DEFAULT_SHIP),
        "recensioni":  _normalize_env_text(os.environ.get("PAGE_RECENSIONI"),  DEFAULT_REVIEW),
        "infocontatti":_normalize_env_text(os.environ.get("PAGE_INFO"),        DEFAULT_INFO),
        "pointattivi": _normalize_env_text(os.environ.get("PAGE_POINTATTIVI"), DEFAULT_POINT),
    }

PAGES = _load_pages_from_env()

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

# ===== UTILS UI =====
PANEL_LIMIT = 3900  # margine sotto 4096

def _chunk_text(text: str, limit: int = PANEL_LIMIT):
    if len(text) <= limit:
        return [text]
    parts, cur, cur_len = [], [], 0
    for line in text.splitlines(True):
        if cur_len + len(line) > limit:
            parts.append("".join(cur)); cur, cur_len = [line], len(line)
        else:
            cur.append(line); cur_len += len(line)
    if cur: parts.append("".join(cur))
    return parts

def _kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Menù", callback_data="goto:main:0")],
        [
            InlineKeyboardButton("🇪🇸 Shiip-Spagna", callback_data="goto:shipspagna:0"),
            InlineKeyboardButton("🎇 Recensioni",    callback_data="goto:recensioni:0"),
        ],
        [
            InlineKeyboardButton("📲 Info-Contatti",  callback_data="goto:infocontatti:0"),
            InlineKeyboardButton("📍🇮🇹 Point Attivi", callback_data="goto:pointattivi:0"),
        ],
    ])

def _kb_section(key: str, page: int, total: int) -> InlineKeyboardMarkup:
    # Navigazione in 1 messaggio: ◀ | Menù | ▶
    left  = InlineKeyboardButton("◀︎", callback_data=f"goto:{key}:{max(page-1,0)}") if page > 0 else None
    right = InlineKeyboardButton("▶︎", callback_data=f"goto:{key}:{min(page+1,total-1)}") if page < total-1 else None
    row = []
    if left: row.append(left)
    row.append(InlineKeyboardButton("📖 Menù", callback_data="goto:main:0"))
    if right: row.append(right)
    return InlineKeyboardMarkup([row])

def _render_keyboard(key: str, page: int, total: int) -> InlineKeyboardMarkup:
    return _kb_main() if key == "main" else _kb_section(key, page, total)

# ====== PANNELLO UNICO: salviamo message_id da editare sempre ======
PANEL_KEY = "panel_msg_id"

async def _ensure_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Restituisce (chat_id, message_id) del pannello da editare.
    Se non esiste, lo crea con il main.
    """
    chat_id = update.effective_chat.id
    msg_id = context.user_data.get(PANEL_KEY)

    if msg_id:
        return chat_id, msg_id

    # crea pannello iniziale (main, pagina 0)
    text = PAGES["main"]
    chunks = _chunk_text(text)
    kb = _render_keyboard("main", 0, len(chunks))
    sent = await context.bot.send_message(chat_id=chat_id, text=chunks[0], reply_markup=kb, parse_mode="Markdown", disable_web_page_preview=True)
    context.user_data[PANEL_KEY] = sent.message_id
    # se ci sono altre pagine, l'utente potrà navigarle con ▶︎
    return chat_id, sent.message_id

async def _edit_panel(context, chat_id: int, msg_id: int, text: str, kb: InlineKeyboardMarkup):
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=msg_id,
        text=text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=kb,
    )

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        add_user(user.id, user.username, user.first_name, user.last_name)

    # 1) Foto senza bottoni (non si edita, resta pulita)
    try:
        await update.message.reply_photo(photo=PHOTO_URL, caption=CAPTION_MAIN, parse_mode="Markdown")
    except Exception:
        pass

    # 2) Crea/mostra PANNELLO unico (testo + bottoni) che poi editeremo sempre
    await _ensure_panel(update, context)

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    # garantisce che abbiamo il pannello da editare
    chat_id, panel_id = await _ensure_panel(update, context)

    data = q.data or ""
    # formato: goto:<key>:<pageindex>
    if not data.startswith("goto:"):
        return
    _, key, page_s = data.split(":", 2)
    try:
        page_idx = int(page_s)
    except:
        page_idx = 0

    text_full = PAGES.get(key, "Pagina non trovata.")
    chunks = _chunk_text(text_full)
    page_idx = max(0, min(page_idx, len(chunks)-1))
    kb = _render_keyboard(key, page_idx, len(chunks))

    # EDIT sempre lo stesso messaggio (il pannello), mai nuovi messaggi
    await _edit_panel(context, chat_id, panel_id, chunks[page_idx], kb)

# ===== COMANDI VARI =====
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start – Foto + pannello navigabile (no spam)\n"
        "/ping – Test\n"
        "/utenti – Numero utenti\n"
        "/status – Stato bot\n"
        "/ultimo_backup – Invia ultimo backup\n\n"
        "Admin: /backup /test_backup /list /export /broadcast"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong!")

async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"👥 Utenti registrati: {count_users()}")

def _parse_backup_time(hhmm: str) -> dtime:
    try:
        h, m = map(int, hhmm.split(":")); return dtime(hour=h, minute=m)
    except: return dtime(hour=3, minute=0)

def _next_backup_utc() -> datetime:
    run_t = _parse_backup_time(BACKUP_TIME)
    now = datetime.now(timezone.utc)
    candidate = datetime.combine(date.today(), run_t, tzinfo=timezone.utc)
    return candidate if candidate > now else candidate + timedelta(days=1)

def _last_backup_file() -> Path | None:
    p = Path(BACKUP_DIR); 
    if not p.exists(): return None
    files = sorted(p.glob("*.db"), reverse=True)
    return files[0] if files else None

def _is_admin(user_id: int) -> bool:
    return ADMIN_ID is not None and user_id == ADMIN_ID

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(timezone.utc); nxt = _next_backup_utc(); last = _last_backup_file()
    msg = (
        f"🔎 **Stato bot**\n"
        f"• Versione: {VERSION}\n"
        f"• Ora (UTC): {now:%Y-%m-%d %H:%M}\n"
        f"• Prossimo backup: {nxt:%Y-%m-%d %H:%M}\n"
        f"• Utenti: {count_users()}\n"
        f"• Ultimo backup: {last.name if last else 'nessuno'}"
    )
    await update.message.reply_text(msg, disable_web_page_preview=True)

# ===== BACKUP =====
async def backup_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dst = Path(BACKUP_DIR) / f"backup_{ts}.db"
        shutil.copy2(DB_FILE, dst)
        logger.info(f"💾 Backup creato: {dst}")
        if ADMIN_ID:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"✅ Backup giornaliero: {dst.name}")
    except Exception as e:
        logger.exception("Errore backup"); 
        if ADMIN_ID: await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Errore backup: {e}")

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Solo admin."); return
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = Path(BACKUP_DIR) / f"manual_{ts}.db"
        shutil.copy2(DB_FILE, dst)
        await update.message.reply_document(InputFile(str(dst)), caption="💾 Backup manuale completato.")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore durante il backup: {e}")

async def ultimo_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = Path(BACKUP_DIR)
    if not p.exists():
        await update.message.reply_text("Nessun backup trovato."); return
    files = sorted(p.glob("*.db"), reverse=True)
    if not files:
        await update.message.reply_text("Nessun backup disponibile."); return
    await update.message.reply_document(InputFile(str(files[0])), caption=f"📦 Ultimo backup: {files[0].name}")

async def test_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Solo admin."); return
    await update.message.reply_text("⏳ Avvio backup di test…"); await backup_job(context); await update.message.reply_text("✅ Test completato.")

# ===== ADMIN: LIST / EXPORT / BROADCAST =====
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Solo admin."); return
    users = get_all_users()
    if not users:
        await update.message.reply_text("📋 Nessun utente."); return
    header = f"📋 Elenco utenti ({len(users)})\n"; chunk = header
    for i, u in enumerate(users, start=1):
        uname = f"@{u['username']}" if u['username'] else "-"
        line = f"{i}. {uname} ({u['user_id']})\n"
        if len(chunk)+len(line) > 3500: await update.message.reply_text(chunk); chunk = ""
        chunk += line
    if chunk: await update.message.reply_text(chunk)

async def export_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Solo admin."); return
    users = get_all_users()
    Path("./exports").mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = Path("./exports") / f"users_{ts}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["user_id","username","first_name","last_name","joined"])
        for u in users: w.writerow([u["user_id"],u["username"] or "",u["first_name"] or "",u["last_name"] or "",u["joined"] or ""])
    await update.message.reply_document(InputFile(str(csv_path)), caption=f"📤 Export utenti ({len(users)})")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Solo admin."); return
    text = " ".join(context.args).strip() if context.args else ""
    if not text and update.message and update.message.reply_to_message:
        text = (update.message.reply_to_message.text or "").strip()
    if not text:
        await update.message.reply_text("ℹ️ Usa: /broadcast <testo> — oppure rispondi a un messaggio con /broadcast"); return
    users = get_all_users(); 
    if not users: await update.message.reply_text("❕ Nessun utente."); return
    ok=fail=0; await update.message.reply_text(f"📣 Invio a {len(users)} utenti…")
    for u in users:
        try: await context.bot.send_message(chat_id=u["user_id"], text=text); ok += 1
        except Exception: fail += 1
        await aio.sleep(0.05)
    await update.message.reply_text(f"✅ Inviati: {ok}\n❌ Errori: {fail}")

# ===== WEBHOOK GUARD =====
async def webhook_guard(context: ContextTypes.DEFAULT_TYPE):
    try:
        info = await context.bot.get_webhook_info()
        if info and info.url:
            logger.warning(f"🛡️ Webhook inatteso: {info.url} — rimuovo.")
            await context.bot.delete_webhook(drop_pending_updates=True)
            logger.info("🛡️ Webhook rimosso.")
    except Exception as e:
        logger.debug(f"Guardiano webhook: {e}")

# ===== ANTI-CONFLICT =====
def anti_conflict_prepare(app):
    loop = aio.get_event_loop()
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
    logger.info("🔧 Webhook rimosso + pending updates droppati.")
    for i in range(6):
        try:
            loop.run_until_complete(app.bot.get_updates(timeout=1))
            logger.info("✅ Slot polling acquisito."); return
        except tgerr.Conflict as e:
            wait=10; logger.warning(f"⚠️ Conflict ({i+1}/6): {e}. Riprovo tra {wait}s…")
            loop.run_until_complete(aio.sleep(wait))
        except Exception as e:
            logger.warning(f"ℹ️ Retry get_updates… ({e})"); loop.run_until_complete(aio.sleep(3))

# ===== MAIN =====
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    anti_conflict_prepare(app)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("ultimo_backup", ultimo_backup))

    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("test_backup", test_backup))
    app.add_handler(CommandHandler("list", list_users))
    app.add_handler(CommandHandler("export", export_users))
    app.add_handler(CommandHandler("broadcast", broadcast))

    app.add_handler(CallbackQueryHandler(on_callback))

    hhmm = _parse_backup_time(BACKUP_TIME)
    app.job_queue.run_repeating(webhook_guard, interval=600, first=60, name="webhook_guard")
    app.job_queue.run_daily(backup_job, time=hhmm, days=(0,1,2,3,4,5,6), name="daily_db_backup")

    logger.info("🚀 Bot avviato.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()