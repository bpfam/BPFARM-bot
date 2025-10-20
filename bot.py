# =====================================================
# bot.py — BPFARM BOT (python-telegram-bot v21+)
# UI: 5 bottoni in home (📖 Menù + 4 sezioni)
# Sezione "Info-Contatti": mostra banner + 2 bottoni (Contatti / Info)
#   - "Contatti" mostra il testo ufficiale (da ENV: PAGE_CONTACTS_TEXT)
#   - "Info" è libero per future sezioni (delivery/meet-up/point) — opzionale
# Un SOLO pannello (edit in-place). Nessun duplicato.
# Ultra-blindato: gli utenti NON possono inviare / incollare / inoltrare nulla.
# Admin ONLY: /status /backup /ultimo_backup /test_backup /list /export /broadcast /utenti
# Backup giornaliero alle 03:00 UTC (configurabile via ENV BACKUP_TIME).
# Anti-conflict: rimuove webhook, prende lo slot di polling e droppa gli update pendenti.
# =====================================================

import os
import csv
import shutil
import logging
import sqlite3
import asyncio as aio
from datetime import datetime, timezone, time as dtime, timedelta, date
from pathlib import Path

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
import telegram.error as tgerr

VERSION = "3.2-ultra-locked-onepanel-contacts-banner"

# ---------------- LOGGING ----------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("bpfarm-bot")

# ---------------- CONFIG (ENV) ----------------
BOT_TOKEN   = os.environ.get("BOT_TOKEN")
DB_FILE     = os.environ.get("DB_FILE", "./data/users.db")
BACKUP_DIR  = os.environ.get("BACKUP_DIR", "./backup")
BACKUP_TIME = os.environ.get("BACKUP_TIME", "03:00")  # UTC su Render
TZ          = os.environ.get("TZ", "Europe/Rome")

ADMIN_ID_ENV = os.environ.get("ADMIN_ID")
ADMIN_ID = int(ADMIN_ID_ENV) if ADMIN_ID_ENV and ADMIN_ID_ENV.isdigit() else None

DISABLE_USER_MESSAGES = os.environ.get("DISABLE_USER_MESSAGES", "true").lower() in ("1","true","yes")

PHOTO_URL = os.environ.get(
    "PHOTO_URL",
    "https://i.postimg.cc/WbpGbTBH/5-F5-DFE41-C80-D-4-FC2-B4-F6-D105844664B3.jpg",
)

CAPTION_MAIN = os.environ.get(
    "CAPTION_MAIN",
    "🏆 Benvenuto nel bot ufficiale di BPFARM!\n"
    "⚡ Serietà e rispetto sono la nostra identità.\n"
    "💪 Qui si cresce con impegno e determinazione."
).replace("\\n","\n")

INFO_BANNER_URL = os.environ.get(
    "INFO_BANNER_URL",
    "https://i.postimg.cc/m2JvXFcH/9-B509-E52-0-D6-A-4-B2-E-8-DE2-68-F81-B0-E9868.png"
)

PAGE_CONTACTS_TEXT = os.environ.get("PAGE_CONTACTS_TEXT", "").replace("\\n","\n")

# Opzionali (li userai più avanti se vuoi riaprire le 3 info)
PAGE_INFO_DELIVERY = (os.environ.get("PAGE_INFO_DELIVERY") or "").replace("\\n","\n")
PAGE_INFO_MEETUP   = (os.environ.get("PAGE_INFO_MEETUP") or "").replace("\\n","\n")
PAGE_INFO_POINT    = (os.environ.get("PAGE_INFO_POINT") or "").replace("\\n","\n")

# ---------------- DATABASE ----------------
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

def add_user(u):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""INSERT OR IGNORE INTO users (user_id,username,first_name,last_name,joined)
                   VALUES (?,?,?,?,?)""", (
        u.id, u.username, u.first_name, u.last_name, datetime.now(timezone.utc).isoformat()
    ))
    conn.commit(); conn.close()

def count_users() -> int:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor(); cur.execute("SELECT COUNT(*) FROM users")
    n = cur.fetchone()[0]; conn.close(); return n

def get_all_users():
    conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT user_id,username,first_name,last_name,joined FROM users ORDER BY joined ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close(); return rows

# ---------------- UTILS / SEC ----------------
def is_admin(uid: int) -> bool:
    return ADMIN_ID is not None and uid == ADMIN_ID

async def notify_admin_attempt(context: ContextTypes.DEFAULT_TYPE, user, cmd: str):
    if not ADMIN_ID: return
    try:
        uname = f"@{user.username}" if (user and user.username) else "-"
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

def parse_hhmm(hhmm: str) -> dtime:
    try:
        h, m = map(int, hhmm.split(":")); return dtime(hour=h, minute=m)
    except Exception:
        return dtime(hour=3, minute=0)

def next_backup_utc() -> datetime:
    run_t = parse_hhmm(BACKUP_TIME)
    now = datetime.now(timezone.utc)
    candidate = datetime.combine(date.today(), run_t, tzinfo=timezone.utc)
    return candidate if candidate > now else candidate + timedelta(days=1)

def last_backup_file() -> Path|None:
    p = Path(BACKUP_DIR)
    if not p.exists(): return None
    files = sorted(p.glob("*.db"), reverse=True)
    return files[0] if files else None

# ---------------- UI / PANNELLO ----------------
PANEL_KEY = "panel_msg_id"

def kb_home() -> InlineKeyboardMarkup:
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

def kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="home")]])

def kb_contacts_info() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 Contatti", callback_data="contacts:open"),
            InlineKeyboardButton("ℹ️ Info",     callback_data="info:open"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="home")]
    ])

async def set_panel_id_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Assicura che il 'pannello' sia il messaggio su cui clicchiamo (evita duplicati)."""
    q = update.callback_query
    if q and q.message:
        context.user_data[PANEL_KEY] = q.message.message_id

async def ensure_home_with_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia la foto di benvenuto + pannello home (sempre pulito)."""
    chat_id = update.effective_chat.id
    # invia la foto di benvenuto (niente web preview param su photo!)
    try:
        await context.bot.send_photo(chat_id=chat_id, photo=PHOTO_URL, caption=CAPTION_MAIN)
    except Exception as e:
        log.warning(f"Foto home non inviata: {e}")
        # fallback: solo testo
        await context.bot.send_message(chat_id=chat_id, text=CAPTION_MAIN, disable_web_page_preview=True)

    # crea/aggiorna il pannello home
    sent = await context.bot.send_message(
        chat_id=chat_id, text="\u2063",  # carattere invisibile
        reply_markup=kb_home(), parse_mode="Markdown", disable_web_page_preview=True
    )
    context.user_data[PANEL_KEY] = sent.message_id

async def edit_panel_text(context, chat_id: int, msg_id: int, text: str, kb: InlineKeyboardMarkup):
    await context.bot.edit_message_text(
        chat_id=chat_id, message_id=msg_id,
        text=text or "\u2063",
        parse_mode="Markdown", disable_web_page_preview=True,
        reply_markup=kb
    )

# ---------------- HANDLER PUBBLICI ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user: add_user(user)
    await ensure_home_with_photo(update, context)

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong!")

# ---------------- CALLBACK (NAV) ----------------
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q: return
    await q.answer()

    await set_panel_id_from_message(update, context)
    chat_id = q.message.chat_id
    panel_id = q.message.message_id
    data = q.data or ""

    if data == "home":
        # Torna alla home: rimanda foto + ricrea pannello home
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=panel_id)
        except Exception:
            pass
        await ensure_home_with_photo(update, context)
        return

    if data.startswith("sec:"):
        sec = data.split(":",1)[1]

        if sec == "infocontatti":
            # 1) mostra il banner immagine (nuovo messaggio)
            try:
                await context.bot.send_photo(chat_id=chat_id, photo=INFO_BANNER_URL)
            except Exception as e:
                log.warning(f"Banner info non inviato: {e}")
            # 2) il pannello (lo stesso messaggio del click) viene editato con bottoni
            await edit_panel_text(context, chat_id, panel_id,
                                  " ", kb_contacts_info())
            return

        # Altre sezioni base (puoi personalizzarle se vuoi)
        if sec == "menu":
            await edit_panel_text(context, chat_id, panel_id, "📖 *Menù*\n\nScrivi qui il tuo menù completo.", kb_back()); return
        if sec == "shipspagna":
            await edit_panel_text(context, chat_id, panel_id, "🇪🇸 *Shiip-Spagna*\n\nInfo e regole spedizioni.", kb_back()); return
        if sec == "recensioni":
            await edit_panel_text(context, chat_id, panel_id, "🎇 *Recensioni*\n\n⭐️ “Ottimo servizio!”", kb_back()); return
        if sec == "pointattivi":
            await edit_panel_text(context, chat_id, panel_id, "📍🇮🇹 *Point Attivi*\n\n• Roma\n• Milano", kb_back()); return

        # default
        await edit_panel_text(context, chat_id, panel_id, "Sezione non trovata.", kb_back()); return

    if data == "contacts:open":
        text = PAGE_CONTACTS_TEXT.strip() or "📋 Nessun contatto configurato."
        await edit_panel_text(context, chat_id, panel_id, text, kb_back()); return

    if data == "info:open":
        # Se vuoi riattivare le sotto-sezioni info, qui potresti mostrare un mini-menu.
        info_txt = "ℹ️ *Info — Centro informativo BPFAM*\n\n(Prossimamente: Delivery, Meet-Up, Point.)"
        await edit_panel_text(context, chat_id, panel_id, info_txt, kb_back()); return

# ---------------- ANTI-MESSAGGI UTENTE ----------------
async def block_everything(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Blocca TUTTO ciò che non è comando, comprese media/link/inoltri."""
    if not DISABLE_USER_MESSAGES:
        return
    # Non rispondiamo e non facciamo nulla: super blindato.
    return

# ---------------- ADMIN COMANDI ----------------
async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/utenti"); return
    await update.message.reply_text(f"👥 Utenti registrati: {count_users()}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/status"); return
    now_utc = datetime.now(timezone.utc)
    next_bu = next_backup_utc()
    last = last_backup_file()
    last_line = f"📦 Ultimo backup: {last.name}" if last else "📦 Ultimo backup: nessuno"
    await update.message.reply_text(
        "🔎 **Stato bot**\n"
        f"• Versione: {VERSION}\n"
        f"• Ora server (UTC): {now_utc:%Y-%m-%d %H:%M:%S}\n"
        f"• Prossimo backup (UTC): {next_bu:%Y-%m-%d %H:%M}\n"
        f"• Utenti registrati: {count_users()}\n"
        f"{last_line}",
        parse_mode="Markdown", disable_web_page_preview=True
    )

async def backup_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dst = Path(BACKUP_DIR) / f"backup_{ts}.db"
        shutil.copy2(DB_FILE, dst)
        log.info(f"💾 Backup creato: {dst}")
        if ADMIN_ID:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"✅ Backup giornaliero completato.\n🕒 {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC\n📦 {dst.name}",
            )
    except Exception as e:
        log.exception("Errore backup automatico")
        if ADMIN_ID:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Errore nel backup: {e}")

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/backup"); return
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = Path(BACKUP_DIR) / f"manual_backup_{ts}.db"
        shutil.copy2(DB_FILE, dst)
        await update.message.reply_document(InputFile(str(dst)), caption="💾 Backup manuale completato.")
    except Exception as e:
        log.exception("Errore backup manuale")
        await update.message.reply_text(f"❌ Errore durante il backup manuale: {e}")

async def ultimo_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/ultimo_backup"); return
    p = Path(BACKUP_DIR)
    if not p.exists():
        await update.message.reply_text("Nessun backup trovato."); return
    files = sorted(p.glob("*.db"), reverse=True)
    if not files:
        await update.message.reply_text("Nessun backup disponibile."); return
    ultimo = files[0]
    await update.message.reply_document(InputFile(str(ultimo)), caption=f"📦 Ultimo backup: {ultimo.name}")

async def test_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/test_backup"); return
    await update.message.reply_text("⏳ Avvio backup di test…")
    await backup_job(context)
    await update.message.reply_text("✅ Test completato.")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/list"); return
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
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/export"); return
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
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/broadcast"); return
    text = " ".join(context.args).strip() if context.args else ""
    if not text and update.message and update.message.reply_to_message:
        text = (update.message.reply_to_message.text or "").strip()
    if not text:
        await update.message.reply_text("ℹ️ Usa: /broadcast <testo> — oppure rispondi a un messaggio con /broadcast")
        return
    users = get_all_users()
    if not users:
        await update.message.reply_text("❕ Nessun utente a cui inviare."); return
    ok=fail=0
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

# ---------------- /help ----------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        txt = (
            "Comandi disponibili:\n"
            "/start – Benvenuto + home\n"
            "/ping – Test rapido\n\n"
            "Solo Admin:\n"
            "/status /utenti\n"
            "/backup /ultimo_backup /test_backup\n"
            "/list /export\n"
            "/broadcast <testo>"
        )
    else:
        txt = "/start – Benvenuto + home\n/ping – Test rapido"
    await update.message.reply_text(txt)

# ---------------- ANTI-CONFLICT ----------------
def anti_conflict_prepare(app):
    loop = aio.get_event_loop()
    # rimuove eventuale webhook e droppa pending
    try:
        loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
        log.info("🔧 Webhook rimosso + pending updates droppati.")
    except Exception as e:
        log.warning(f"Webhook delete: {e}")
    # prova a prendere lo slot polling
    for i in range(6):
        try:
            loop.run_until_complete(app.bot.get_updates(timeout=1))
            log.info("✅ Slot polling acquisito.")
            return
        except tgerr.Conflict as e:
            wait = 10
            log.warning(f"⚠️ Conflict ({i+1}/6): {e}. Riprovo tra {wait}s…")
            loop.run_until_complete(aio.sleep(wait))
        except Exception as e:
            log.warning(f"ℹ️ Retry get_updates… ({e})")
            loop.run_until_complete(aio.sleep(3))

# ---------------- MAIN ----------------
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    anti_conflict_prepare(app)

    # Pubblici
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))

    # Admin
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("ultimo_backup", ultimo_backup))
    app.add_handler(CommandHandler("test_backup", test_backup))
    app.add_handler(CommandHandler("list", list_users))
    app.add_handler(CommandHandler("export", export_users))
    app.add_handler(CommandHandler("broadcast", broadcast))

    # Callback menu
    app.add_handler(CallbackQueryHandler(on_callback))

    # /help
    app.add_handler(CommandHandler("help", help_command))

    # BLINDATO: blocca tutto ciò che non è comando
    app.add_handler(MessageHandler(~filters.COMMAND, block_everything))

    # Job: backup giornaliero
    hhmm = parse_hhmm(BACKUP_TIME)
    # prossimo run (UTC)
    now_utc = datetime.now(timezone.utc)
    first_run = datetime.combine(now_utc.date(), hhmm, tzinfo=timezone.utc)
    if first_run <= now_utc:
        first_run += timedelta(days=1)
    app.job_queue.run_repeating(backup_job, interval=86400, first=first_run, name="daily_backup")

    log.info(f"🚀 BPFARM BOT avviato — v{VERSION}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()