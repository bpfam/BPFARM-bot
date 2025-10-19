# =====================================================
# bot.py — BPFARM BOT (python-telegram-bot v21+)
# Menu interno (callback + 🔙 Back) + testi da ENV su Render
# Anti-conflict strong + Webhook guard + Backup + /status
# Admin: /list /export /broadcast
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
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
import telegram.error as tgerr

VERSION = "1.8-env-pages"

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
BACKUP_TIME = os.environ.get("BACKUP_TIME", "03:00")  # HH:MM (ora server, UTC su Render)

ADMIN_ID_ENV = os.environ.get("ADMIN_ID")
ADMIN_ID = int(ADMIN_ID_ENV) if ADMIN_ID_ENV and ADMIN_ID_ENV.isdigit() else None

# Immagine di benvenuto (link diretto .jpg/.png)
PHOTO_URL = os.environ.get(
    "PHOTO_URL",
    "https://i.postimg.cc/WbpGbTBH/5-F5-DFE41-C80-D-4-FC2-B4-F6-D105844664B3.jpg",
)

# ===== LETTURA TESTI PAGINE DA ENV =====
# Suggerimento: in Render → Environment → Edit
# aggiungi/edita le variabili: PAGE_MAIN, PAGE_SHIPSPAGNA, PAGE_RECENSIONI, PAGE_INFO
# Puoi usare anche "\n" per andare a capo: verrà convertito in newline.

DEFAULT_MAIN = (
    "🏆 *Benvenuto nel bot ufficiale di BPFARM!*\n\n"
    "Scegli una sezione:\n"
    "• 🇪🇸 *Shiip-Spagna* — informazioni, regole, spedizioni\n"
    "• 🎇 *Recensioni* — feedback e testimonianze\n"
    "• 📲 *Info-Contatti* — contatti, help, note\n\n"
    "⚡ Serietà e rispetto sono la nostra identità.\n"
    "💪 Qui si cresce con impegno e determinazione."
)
DEFAULT_SHIP = (
    "🇪🇸 *Shiip-Spagna*\n\n"
    "Scrivi qui tutto il testo che vuoi (regole, costi, tempi, FAQ...).\n"
    "Il bot dividerà automaticamente i messaggi se sono molto lunghi."
)
DEFAULT_REVIEW = (
    "🎇 *Recensioni*\n\n"
    "— “Servizio top, consigliatissimo!”\n"
    "— “Precisi e puntuali.”\n"
    "— “Ottima comunicazione e supporto.”"
)
DEFAULT_INFO = (
    "📲 *Info & Contatti*\n\n"
    "• Admin: @tuo_username\n"
    "• Orari: Lun–Sab, 09:00–19:00\n"
    "• Note: Rispondiamo entro poche ore."
)

def _normalize_env_text(v: str | None, default: str) -> str:
    """
    Ritorna il testo dall'ENV (se presente), altrimenti default.
    Converte le sequenze '\\n' in newline reali.
    Se il valore inizia con 'file://', prova a leggere il file locale (opzionale).
    """
    if not v:
        return default
    v = v.replace("\\n", "\n")
    if v.startswith("file://"):
        path = v[7:]
        try:
            with open(path, "r", encoding="utf-8") as f:
                txt = f.read()
            return txt
        except Exception as e:
            logger.warning(f"Impossibile leggere {path}: {e}. Uso valore ENV grezzo.")
    return v

def _load_pages_from_env():
    return {
        "main": _normalize_env_text(os.environ.get("PAGE_MAIN"), DEFAULT_MAIN),
        "shipspagna": _normalize_env_text(os.environ.get("PAGE_SHIPSPAGNA"), DEFAULT_SHIP),
        "recensioni": _normalize_env_text(os.environ.get("PAGE_RECENSIONI"), DEFAULT_REVIEW),
        "infocontatti": _normalize_env_text(os.environ.get("PAGE_INFO"), DEFAULT_INFO),
    }

# Carica all'avvio; se modifichi ENV e ridistribuisci, i nuovi testi vengono letti
PAGES = _load_pages_from_env()

# ===== DATABASE =====
def init_db():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            first_name  TEXT,
            last_name   TEXT,
            joined      TEXT
        )
        """
    )
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
        candidate = candidate + timedelta(days=1)
    return candidate

def _last_backup_file() -> Path | None:
    p = Path(BACKUP_DIR)
    if not p.exists():
        return None
    files = sorted(p.glob("*.db"), reverse=True)
    return files[0] if files else None

def _is_admin(user_id: int) -> bool:
    return ADMIN_ID is not None and user_id == ADMIN_ID

def _kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇪🇸 Shiip-Spagna", callback_data="page:shipspagna")],
        [InlineKeyboardButton("🎇 Recensioni",    callback_data="page:recensioni")],
        [InlineKeyboardButton("📲 Info-Contatti", callback_data="page:infocontatti")],
    ])

def _kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data="page:main")]
    ])

def _chunk_text(text: str, limit: int = 3900):
    # Telegram consente 4096 caratteri; lasciamo margine
    if len(text) <= limit:
        return [text]
    parts = []
    cur = []
    cur_len = 0
    for line in text.splitlines(True):
        if cur_len + len(line) > limit:
            parts.append("".join(cur))
            cur = [line]
            cur_len = len(line)
        else:
            cur.append(line)
            cur_len += len(line)
    if cur:
        parts.append("".join(cur))
    return parts

async def _render_page_message(update: Update, context: ContextTypes.DEFAULT_TYPE, page_key: str, edit_target=None):
    """Mostra la pagina; se lunga, la spezza in più messaggi.
       Se edit_target è presente e c'è un solo chunk, prova l'edit.
    """
    text = PAGES.get(page_key, "Pagina non trovata.")
    chunks = _chunk_text(text)
    kb = _kb_main() if page_key == "main" else _kb_back()

    if edit_target and len(chunks) == 1:
        try:
            await edit_target.edit_text(
                chunks[0], reply_markup=kb, parse_mode="Markdown", disable_web_page_preview=True
            )
            return
        except Exception:
            pass

    for i, part in enumerate(chunks, start=1):
        if i < len(chunks):
            await update.effective_chat.send_message(part, parse_mode="Markdown", disable_web_page_preview=True)
        else:
            await update.effective_chat.send_message(part, reply_markup=kb, parse_mode="Markdown", disable_web_page_preview=True)

# ===== HANDLERS UTENTE =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        add_user(user.id, user.username, user.first_name, user.last_name)

    # Foto di benvenuto
    try:
        await update.message.reply_photo(
            photo=PHOTO_URL,
            caption="🏆 Benvenuto nel bot ufficiale di BPFARM!\n⚡ Serietà e rispetto sono la nostra identità.\n💪 Qui si cresce con impegno e determinazione.",
        )
    except Exception:
        pass

    await _render_page_message(update, context, "main")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Comandi disponibili:\n"
        "/start – Benvenuto + menu interno\n"
        "/help – Questo aiuto\n"
        "/ping – Test rapido\n"
        "/utenti – Numero utenti registrati\n"
        "/ultimo_backup – Invia l’ultimo file di backup\n"
        "/status – Stato del bot (versione/ora/prossimo backup/utenti)\n"
        "\n"
        "Solo Admin:\n"
        "/backup – Backup manuale\n"
        "/test_backup – Esegue ora il job di backup\n"
        "/list – Elenco utenti\n"
        "/export – CSV utenti\n"
        "/broadcast <testo> – Messaggio a tutti"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong! Il bot è attivo.")

async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"👥 Utenti registrati: {count_users()}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# ===== BACKUP =====
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
                text=f"✅ Backup giornaliero completato.\n🕒 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n📦 {backup_path.name}",
            )
    except Exception as e:
        logger.exception("Errore nel backup automatico")
        if ADMIN_ID:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Errore nel backup: {e}")

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Solo l’amministratore può eseguire questa operazione.")
        return
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
    p = Path(BACKUP_DIR)
    if not p.exists():
        await update.message.reply_text("Nessun backup trovato.")
        return
    files = sorted(p.glob("*.db"), reverse=True)
    if not files:
        await update.message.reply_text("Nessun backup disponibile.")
        return
    ultimo = files[0]
    await update.message.reply_document(InputFile(str(ultimo)), caption=f"📦 Ultimo backup: {ultimo.name}")

async def test_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Solo l’amministratore può eseguire questa operazione.")
        return
    await update.message.reply_text("⏳ Avvio backup di test…")
    await backup_job(context)
    await update.message.reply_text("✅ Test completato. Controlla messaggio all’admin e cartella backup.")

# ===== ADMIN: LIST / EXPORT / BROADCAST =====
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Solo l’amministratore può eseguire questa operazione.")
        return
    users = get_all_users()
    if not users:
        await update.message.reply_text("📋 Nessun utente registrato.")
        return
    header = f"📋 Elenco utenti ({len(users)} totali)\n"
    chunk = header
    for i, u in enumerate(users, start=1):
        uname = f"@{u['username']}" if u['username'] else "-"
        line = f"{i}. {uname} ({u['user_id']})\n"
        if len(chunk) + len(line) > 3500:
            await update.message.reply_text(chunk)
            chunk = ""
        chunk += line
    if chunk:
        await update.message.reply_text(chunk)

async def export_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Solo l’amministratore può eseguire questa operazione.")
        return
    users = get_all_users()
    Path("./exports").mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = Path("./exports") / f"users_export_{ts}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "username", "first_name", "last_name", "joined"])
        for u in users:
            w.writerow([u["user_id"], u["username"] or "", u["first_name"] or "", u["last_name"] or "", u["joined"] or ""])
    await update.message.reply_document(InputFile(str(csv_path)), caption=f"📤 Export utenti ({len(users)} record)")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Solo l’amministratore può eseguire questa operazione.")
        return

    text = " ".join(context.args).strip() if context.args else ""
    if not text and update.message and update.message.reply_to_message:
        text = (update.message.reply_to_message.text or "").strip()

    if not text:
        await update.message.reply_text("ℹ️ Usa: /broadcast <testo> — oppure rispondi a un messaggio con /broadcast")
        return

    users = get_all_users()
    if not users:
        await update.message.reply_text("❕ Nessun utente a cui inviare.")
        return

    ok = 0
    fail = 0
    await update.message.reply_text(f"📣 Invio a {len(users)} utenti…")
    for u in users:
        try:
            await context.bot.send_message(chat_id=u["user_id"], text=text)
            ok += 1
            await aio.sleep(0.05)
        except Exception:
            fail += 1
            await aio.sleep(0.05)

    await update.message.reply_text(f"✅ Inviati: {ok}\n❌ Errori: {fail}")

# ===== WEBHOOK GUARD =====
async def webhook_guard(context: ContextTypes.DEFAULT_TYPE):
    try:
        info = await context.bot.get_webhook_info()
        if info and info.url:
            logger.warning(f"🛡️ Webhook inatteso rilevato: {info.url} — lo rimuovo.")
            await context.bot.delete_webhook(drop_pending_updates=True)
            logger.info("🛡️ Webhook rimosso dal guardiano.")
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
            logger.info("✅ Slot di polling acquisito.")
            return
        except tgerr.Conflict as e:
            wait = 10
            logger.warning(f"⚠️ Conflict (tentativo {i+1}/6): {e}. Riprovo tra {wait}s…")
            loop.run_until_complete(aio.sleep(wait))
        except Exception as e:
            logger.warning(f"ℹ️ Attendo e riprovo get_updates… ({e})")
            loop.run_until_complete(aio.sleep(3))

# ===== CALLBACK: NAVIGAZIONE MENU =====
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()
    data = q.data or ""
    if data.startswith("page:"):
        key = data.split(":", 1)[1]
        try:
            await _render_page_message(update, context, key, edit_target=q.message)
        except Exception:
            await _render_page_message(update, context, key, edit_target=None)

# ===== MAIN =====
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
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("ultimo_backup", ultimo_backup))

    # Admin
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("test_backup", test_backup))
    app.add_handler(CommandHandler("list", list_users))
    app.add_handler(CommandHandler("export", export_users))
    app.add_handler(CommandHandler("broadcast", broadcast))

    # Navigazione menu (callback)
    app.add_handler(CallbackQueryHandler(on_callback))

    # Guardiano ogni 10 minuti
    app.job_queue.run_repeating(webhook_guard, interval=600, first=60, name="webhook_guard")

    # Backup giornaliero (ora server UTC)
    hhmm = _parse_backup_time(BACKUP_TIME)
    app.job_queue.run_daily(backup_job, time=hhmm, days=(0,1,2,3,4,5,6), name="daily_db_backup")
    logger.info("🕒 Backup giornaliero pianificato (timezone server).")

    # Avvio con retry anti-conflict
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