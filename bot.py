# =====================================================
# bot.py — BPFARM BOT (python-telegram-bot v21+)
# UI: 5 bottoni in home (📖 Menù + 4 sezioni) | Sezioni: 🔙 Back
# Navigazione in UN SOLO messaggio (edit in-place)
# ULTRA-BLINDATO:
#  - Solo ADMIN vede/usa: /status /backup /ultimo_backup /test_backup /list /export /broadcast /utenti
#  - Non-admin: nessuna risposta ai comandi sensibili (silenzio)
#  - Notifica all'ADMIN su ogni tentativo non autorizzato (username, id, comando)
# Fix: PAGE_MAIN può essere vuoto | CAPTION_MAIN supporta \n
# Fix robusto: pannello SEMPRE presente dopo /start
# Backup giornaliero | Anti-conflict | Webhook guard
# =====================================================

import os
import sqlite3
import logging
import shutil
import asyncio as aio
import csv
from datetime import datetime, timezone, time as dtime, timedelta, date
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import telegram.error as tgerr

VERSION = "2.8-ultra-locked+panel-fix"

# ===== LOGGING =====
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bpfarm-bot")

# ===== CONFIG (ENV) =====
BOT_TOKEN   = os.environ.get("BOT_TOKEN")
DB_FILE     = os.environ.get("DB_FILE", "./data/users.db")
BACKUP_DIR  = os.environ.get("BACKUP_DIR", "./backup")
BACKUP_TIME = os.environ.get("BACKUP_TIME", "03:00")  # UTC su Render

ADMIN_ID_ENV = os.environ.get("ADMIN_ID")
ADMIN_ID = int(ADMIN_ID_ENV) if ADMIN_ID_ENV and ADMIN_ID_ENV.isdigit() else None

# FOTO + CAPTION (supporto \n da Render)
PHOTO_URL = os.environ.get(
    "PHOTO_URL",
    "https://i.postimg.cc/WbpGbTBH/5-F5-DFE41-C80-D-4-FC2-B4-F6-D105844664B3.jpg",
)
CAPTION_MAIN = os.environ.get(
    "CAPTION_MAIN",
    "🏆 *Benvenuto nel bot ufficiale di BPFARM!*\n⚡ Serietà e rispetto sono la nostra identità.\n💪 Qui si cresce con impegno e determinazione."
)
CAPTION_MAIN = CAPTION_MAIN.replace("\\n", "\n")

# ===== TESTI PAGINE (ENV) =====
def _normalize_env_text(v: str | None, default: str) -> str:
    if v is None:
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
        "main":        _normalize_env_text(os.environ.get("PAGE_MAIN"), ""),
        "menu":        _normalize_env_text(os.environ.get("PAGE_MENU"), "📖 *Menù*\n\nScrivi qui il tuo menù completo."),
        "shipspagna":  _normalize_env_text(os.environ.get("PAGE_SHIPSPAGNA"), "🇪🇸 *Shiip-Spagna*\n\nInfo e regole spedizioni."),
        "recensioni":  _normalize_env_text(os.environ.get("PAGE_RECENSIONI"), "🎇 *Recensioni*\n\n⭐️ “Ottimo servizio!”"),
        "infocontatti":_normalize_env_text(os.environ.get("PAGE_INFO"), "📲 *Info-Contatti*\n\nAdmin: @tuo_username"),
        "pointattivi": _normalize_env_text(os.environ.get("PAGE_POINTATTIVI"), "📍🇮🇹 *Point Attivi*\n\n• Roma\n• Milano"),
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
    conn.commit(); conn.close()

def add_user(user_id: int, username: str, first_name: str, last_name: str):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, joined)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, username, first_name, last_name, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit(); conn.close()

def count_users() -> int:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor(); cur.execute("SELECT COUNT(*) FROM users")
    n = cur.fetchone()[0]; conn.close(); return n

def get_all_users():
    conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, first_name, last_name, joined FROM users ORDER BY joined ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close(); return rows

# ===== UTILS / SECURITY =====
def _is_admin(user_id: int) -> bool:
    return ADMIN_ID is not None and user_id == ADMIN_ID

async def _notify_admin_attempt(context: ContextTypes.DEFAULT_TYPE, user, cmd: str):
    """Avvisa l'ADMIN (in silenzio per chi ha tentato)."""
    if not ADMIN_ID:
        return
    uname = f"@{user.username}" if user and user.username else "-"
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "🚫 *Tentativo non autorizzato*\n"
                f"• Comando: `{cmd}`\n"
                f"• Utente: {uname} (id: {user.id if user else '?'})\n"
                f"• Quando: {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC"
            ),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    except Exception:
        pass

# ===== UI / NAVIGAZIONE =====
def _kb_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Menù",            callback_data="sec:menu")],
        [
            InlineKeyboardButton("🇪🇸 Shiip-Spagna", callback_data="sec:shipspagna"),
            InlineKeyboardButton("🎇 Recensioni",    callback_data="sec:recensioni"),
        ],
        [
            InlineKeyboardButton("📲 Info-Contatti",  callback_data="sec:infocontatti"),
            InlineKeyboardButton("📍🇮🇹 Point Attivi", callback_data="sec:pointattivi"),
        ],
    ])

def _kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="home")]])

PANEL_KEY = "panel_msg_id"   # message_id pannello da editare sempre

# === FIX ROBUSTO: garantisce sempre il pannello ===
async def _ensure_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Garantisce che il messaggio-pannello esista SEMPRE.
    - Se abbiamo un message_id salvato, proviamo a editarlo.
    - Se l'edit fallisce (messaggio non trovato, ecc.), ne creiamo uno nuovo.
    """
    chat_id = update.effective_chat.id
    msg_id = context.user_data.get(PANEL_KEY)

    text = PAGES["main"] or "\u2063"        # placeholder invisibile se vuoto
    kb   = _kb_home()

    if msg_id:
        try:
            # allinea almeno la tastiera: se il messaggio non esiste più, qui esplode
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=msg_id,
                reply_markup=kb,
            )
            # opzionale: riallinea anche il testo (se identico -> BadRequest che ignoriamo)
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=text,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                    reply_markup=kb,
                )
            except tgerr.BadRequest:
                pass
            return chat_id, msg_id
        except tgerr.BadRequest:
            # Il messaggio non esiste più o non è editabile: crea nuovo
            pass

    sent = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=kb,
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )
    context.user_data[PANEL_KEY] = sent.message_id
    return chat_id, sent.message_id

async def _edit_panel(context, chat_id: int, msg_id: int, text: str, kb: InlineKeyboardMarkup):
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=msg_id,
        text=text or "\u2063",
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=kb,
    )

# ===== HANDLERS UTENTE =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        add_user(user.id, user.username, user.first_name, user.last_name)
    # Foto + caption
    try:
        await update.message.reply_photo(photo=PHOTO_URL, caption=CAPTION_MAIN, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Errore invio foto: {e}")
    # Pannello home
    await _ensure_panel(update, context)

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q: return
    await q.answer()
    chat_id, panel_id = await _ensure_panel(update, context)
    data = q.data or ""
    if data == "home":
        await _edit_panel(context, chat_id, panel_id, PAGES["main"], _kb_home()); return
    if data.startswith("sec:"):
        key = data.split(":", 1)[1]
        await _edit_panel(context, chat_id, panel_id, PAGES.get(key, "Pagina non trovata."), _kb_back()); return

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong!")

# ===== COMANDI ADMIN (ULTRA BLINDATI: nessuna risposta ai non-admin) =====
async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await _notify_admin_attempt(context, update.effective_user, "/utenti"); return
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
    p = Path(BACKUP_DIR)
    if not p.exists(): return None
    files = sorted(p.glob("*.db"), reverse=True)
    return files[0] if files else None

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await _notify_admin_attempt(context, update.effective_user, "/status"); return
    now_utc = datetime.now(timezone.utc)
    next_bu = _next_backup_utc()
    last = _last_backup_file()
    last_line = f"📦 Ultimo backup: {last.name}" if last else "📦 Ultimo backup: nessuno"
    await update.message.reply_text(
        "🔎 **Stato bot**\n"
        f"• Versione: {VERSION}\n"
        f"• Ora server (UTC): {now_utc:%Y-%m-%d %H:%M:%S}\n"
        f"• Prossimo backup (UTC): {next_bu:%Y-%m-%d %H:%M}\n"
        f"• Utenti registrati: {count_users()}\n"
        f"{last_line}",
        disable_web_page_preview=True,
    )

async def backup_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = Path(BACKUP_DIR) / f"backup_{ts}.db"
        shutil.copy2(DB_FILE, backup_path)
        logger.info(f"💾 Backup creato: {backup_path}")
        if ADMIN_ID:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"✅ Backup giornaliero completato.\n🕒 {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC\n📦 {backup_path.name}",
            )
    except Exception as e:
        logger.exception("Errore nel backup automatico")
        if ADMIN_ID:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Errore nel backup: {e}")

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await _notify_admin_attempt(context, update.effective_user, "/backup"); return
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = Path(BACKUP_DIR) / f"manual_backup_{ts}.db"
        shutil.copy2(DB_FILE, backup_path)
        await update.message.reply_document(InputFile(str(backup_path)), caption="💾 Backup manuale completato.")
        logger.info(f"💾 Backup manuale eseguito: {backup_path}")
    except Exception as e:
        logger.exception("Errore backup manuale")
        await update.message.reply_text(f"❌ Errore durante il backup manuale: {e}")

async def ultimo_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await _notify_admin_attempt(context, update.effective_user, "/ultimo_backup"); return
    p = Path(BACKUP_DIR)
    if not p.exists():
        await update.message.reply_text("Nessun backup trovato."); return
    files = sorted(p.glob("*.db"), reverse=True)
    if not files:
        await update.message.reply_text("Nessun backup disponibile."); return
    ultimo = files[0]
    await update.message.reply_document(InputFile(str(ultimo)), caption=f"📦 Ultimo backup: {ultimo.name}")

async def test_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await _notify_admin_attempt(context, update.effective_user, "/test_backup"); return
    await update.message.reply_text("⏳ Avvio backup di test…")
    await backup_job(context)
    await update.message.reply_text("✅ Test completato.")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await _notify_admin_attempt(context, update.effective_user, "/list"); return
    users = get_all_users()
    if not users:
        await update.message.reply_text("📋 Nessun utente registrato."); return
    header = f"📋 Elenco utenti ({len(users)} totali)\n"; chunk = header
    for i, u in enumerate(users, start=1):
        uname = f"@{u['username']}" if u['username'] else "-"
        line = f"{i}. {uname} ({u['user_id']})\n"
        if len(chunk) + len(line) > 3500:
            await update.message.reply_text(chunk); chunk = ""
        chunk += line
    if chunk: await update.message.reply_text(chunk)

async def export_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await _notify_admin_attempt(context, update.effective_user, "/export"); return
    users = get_all_users()
    Path("./exports").mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = Path("./exports") / f"users_export_{ts}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id","username","first_name","last_name","joined"])
        for u in users:
            w.writerow([u["user_id"],u["username"] or "",u["first_name"] or "",u["last_name"] or "",u["joined"] or ""])
    await update.message.reply_document(InputFile(str(csv_path)), caption=f"📤 Export utenti ({len(users)} record)")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await _notify_admin_attempt(context, update.effective_user, "/broadcast"); return
    text = " ".join(context.args).strip() if context.args else ""
    if not text and update.message and update.message.reply_to_message:
        text = (update.message.reply_to_message.text or "").strip()
    if not text:
        await update.message.reply_text("ℹ️ Usa: /broadcast <testo> — oppure rispondi a un messaggio con /broadcast"); return
    users = get_all_users()
    if not users: await update.message.reply_text("❕ Nessun utente a cui inviare."); return
    ok=fail=0; await update.message.reply_text(f"📣 Invio a {len(users)} utenti…")
    for u in users:
        try:
            await context.bot.send_message(chat_id=u["user_id"], text=text)
            ok += 1
            await aio.sleep(0.05)
        except Exception:
            fail += 1
            await aio.sleep(0.05)
    await update.message.reply_text(f"✅ Inviati: {ok}\n❌ Errori: {fail}")

# ===== /help INTELLIGENTE =====
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_admin(update.effective_user.id):
        txt = (
            "Comandi disponibili:\n"
            "/start – Benvenuto + menu\n"
            "/ping – Test rapido\n"
            "\n"
            "Solo Admin:\n"
            "/status – Stato bot\n"
            "/utenti – Numero utenti\n"
            "/backup – Backup manuale\n"
            "/ultimo_backup – Invia l’ultimo file di backup\n"
            "/test_backup – Esegue job di backup\n"
            "/list – Elenco utenti\n"
            "/export – CSV utenti\n"
            "/broadcast <testo> – Messaggio a tutti"
        )
    else:
        txt = "Comandi disponibili:\n/start – Benvenuto + menu\n/ping – Test rapido"
    await update.message.reply_text(txt)

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

# ===== ANTI-CONFLICT (strong) =====
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

    # Comandi pubblici
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))

    # Comandi ADMIN (altri utenti: silenzio + notifica admin)
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("ultimo_backup", ultimo_backup))
    app.add_handler(CommandHandler("test_backup", test_backup))
    app.add_handler(CommandHandler("list", list_users))
    app.add_handler(CommandHandler("export", export_users))
    app.add_handler(CommandHandler("broadcast", broadcast))

    # Menu callback
    app.add_handler(CallbackQueryHandler(on_callback))

    # /help
    app.add_handler(CommandHandler("help", help_command))

    # Ignora qualsiasi altro comando degli utenti normali, in silenzio
    app.add_handler(MessageHandler(filters.COMMAND, lambda u, c: None))

    # Job: webhook guard + backup giornaliero
    app.job_queue.run_repeating(webhook_guard, interval=600, first=60, name="webhook_guard")
    hhmm = _parse_backup_time(BACKUP_TIME)
    app.job_queue.run_daily(backup_job, time=hhmm, days=(0,1,2,3,4,5,6), name="daily_db_backup")

    logger.info("🚀 Bot avviato (polling).")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()