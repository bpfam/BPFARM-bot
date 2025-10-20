# bot.py — BPFARM BOT (telegram-bot v21+)
# Pannello unico (foto+caption) editato in-place, niente duplicati
# Home con immagine; Info&Contatti con immagine dedicata + sotto-menu
# Contatti: nessun doppio messaggio, solo edit della caption
# Tutto inviato con protect_content=True (no forward/salva)
# Admin-only per comandi sensibili

import os
import sqlite3
import logging
import shutil
import asyncio as aio
import csv
import json
from datetime import datetime, timezone, time as dtime, timedelta, date
from pathlib import Path

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputFile, InputMediaPhoto
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
import telegram.error as tgerr

VERSION = "3.1-media-panel-protected"

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

HOME_PHOTO_URL = os.environ.get("PHOTO_URL", "")  # immagine HOME
INFO_PHOTO_URL = os.environ.get("INFO_PHOTO_URL", HOME_PHOTO_URL)  # immagine Info&Contatti

CAPTION_MAIN = os.environ.get(
    "CAPTION_MAIN",
    "🏆 *Benvenuto nel bot ufficiale di BPFARM!*\n"
    "⚡ Serietà e rispetto sono la nostra identità.\n"
    "💪 Qui si cresce con impegno e determinazione."
).replace("\\n", "\n")

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

# Pagine / testi (con default sicuri)
PAGES = {
    "info_overview": _normalize_env_text(
        os.environ.get("PAGE_INFO_OVERVIEW"),
        "📲 *Info & Contatti*\n\nScegli una sezione qui sotto 👇"
    ),
    "info_delivery": _normalize_env_text(
        os.environ.get("PAGE_INFO_DELIVERY"),
        "🚚 *Regolamento Delivery*"
    ),
    "info_meetup": _normalize_env_text(
        os.environ.get("PAGE_INFO_MEETUP"),
        "🤝 *Regolamento Meet-up*"
    ),
    "info_point": _normalize_env_text(
        os.environ.get("PAGE_INFO_POINT"),
        "📍🇮🇹 *BPFAM OFFICIAL POINT*"
    ),
}

# ===== CONTATTI (JSON in ENV) =====
def load_contacts():
    raw = os.environ.get("CONTACT_LINKS_JSON", "").strip()
    if not raw:
        return [
            {"label": "Instagram", "url": "https://instagram.com/bpfamofficial", "emoji": "📱"},
            {"label": "Telegram", "url": "https://t.me/contattobpfam", "emoji": "💬"},
            {"label": "Canale Ufficiale", "url": "https://t.me/+CIA2nWh5thE2ZWFk", "emoji": "📢"},
            {"label": "Bot Telegram", "url": "https://t.me/Bpfarmbot", "emoji": "🤖"},
        ]
    try:
        data = json.loads(raw)
        assert isinstance(data, list)
        return data
    except Exception as e:
        logger.warning(f"CONTACT_LINKS_JSON invalido: {e}")
        return []

CONTACTS = load_contacts()

def contacts_caption() -> str:
    # Caption completa per la sezione contatti
    lines = [
        "💎 *BPFAM CONTATTI UFFICIALI* 💎\n",
        "Rimani connesso ai canali ufficiali BPFAM.\n",
    ]
    for c in CONTACTS:
        emoji = c.get("emoji","")
        label = c.get("label","")
        url = c.get("url","")
        lines.append(f"{emoji} *{label}*: {url}")
    return "\n".join(lines)

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

# ===== UTILS =====
def _is_admin(user_id: int) -> bool:
    return ADMIN_ID is not None and user_id == ADMIN_ID

async def _notify_admin_attempt(context: ContextTypes.DEFAULT_TYPE, user, cmd: str):
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
            protect_content=True,
        )
    except Exception:
        pass

# ===== UI =====
PANEL_KEY = "panel_msg_id"
CURRENT_PHOTO_KEY = "panel_photo_url"

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

def _kb_info_root() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📁 Contatti", callback_data="info:contacts"),
            InlineKeyboardButton("ℹ️ Info",     callback_data="info:menu"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="home")],
    ])

def _kb_info_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚚 Info Delivery", callback_data="info:delivery")],
        [InlineKeyboardButton("🤝 Info Meet-up",  callback_data="info:meetup")],
        [InlineKeyboardButton("📍🇮🇹 Info Point", callback_data="info:point")],
        [InlineKeyboardButton("🔙 Back", callback_data="info:root")],
    ])

def _kb_back_to_info_root() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="info:root")]])

# --- Media panel helpers ---
async def _send_new_panel_photo(context, chat_id: int, photo_url: str, caption: str, kb: InlineKeyboardMarkup):
    sent = await context.bot.send_photo(
        chat_id=chat_id,
        photo=photo_url,
        caption=caption or "\u2063",
        parse_mode="Markdown",
        reply_markup=kb,
        protect_content=True,
    )
    return sent.message_id

async def _edit_panel_media(context, chat_id: int, msg_id: int, photo_url: str | None, caption: str, kb: InlineKeyboardMarkup):
    # Cambia media (se photo_url != None) altrimenti cambia solo caption
    if photo_url:
        try:
            await context.bot.edit_message_media(
                chat_id=chat_id,
                message_id=msg_id,
                media=InputMediaPhoto(media=photo_url, caption=caption or "\u2063", parse_mode="Markdown"),
                reply_markup=kb,
            )
            return
        except tgerr.BadRequest as e:
            logger.warning(f"edit media fallita: {e} — provo a cambiare solo caption")

    # fallback: solo caption
    await context.bot.edit_message_caption(
        chat_id=chat_id,
        message_id=msg_id,
        caption=caption or "\u2063",
        parse_mode="Markdown",
        reply_markup=kb,
    )

async def _ensure_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, photo_url: str, caption: str, kb: InlineKeyboardMarkup):
    chat_id = update.effective_chat.id
    panel_id = context.user_data.get(PANEL_KEY)
    current_photo = context.user_data.get(CURRENT_PHOTO_KEY)

    if not panel_id:
        # crea nuovo pannello come FOTO
        new_id = await _send_new_panel_photo(context, chat_id, photo_url, caption, kb)
        context.user_data[PANEL_KEY] = new_id
        context.user_data[CURRENT_PHOTO_KEY] = photo_url
        return chat_id, new_id

    # esiste: se l’immagine cambia, edita media; altrimenti solo caption
    change_photo = (photo_url and photo_url != current_photo)
    await _edit_panel_media(context, chat_id, panel_id, photo_url if change_photo else None, caption, kb)
    if change_photo:
        context.user_data[CURRENT_PHOTO_KEY] = photo_url
    return chat_id, panel_id

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        add_user(user.id, user.username, user.first_name, user.last_name)

    # Pannello home = foto HOME + caption di benvenuto + tastiera home
    await _ensure_panel(update, context, HOME_PHOTO_URL, CAPTION_MAIN, _kb_home())

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()
    chat_id = q.message.chat_id
    context.user_data[PANEL_KEY] = q.message.message_id  # assicura che questo è il pannello

    data = q.data or ""

    # === HOME ===
    if data == "home":
        await _edit_panel_media(context, chat_id, q.message.message_id, HOME_PHOTO_URL, CAPTION_MAIN, _kb_home())
        context.user_data[CURRENT_PHOTO_KEY] = HOME_PHOTO_URL
        return

    # === INFO & CONTATTI (root) ===
    if data == "sec:infocontatti" or data == "info:root":
        caption = PAGES["info_overview"]
        await _edit_panel_media(context, chat_id, q.message.message_id, INFO_PHOTO_URL, caption, _kb_info_root())
        context.user_data[CURRENT_PHOTO_KEY] = INFO_PHOTO_URL
        return

    # === INFO: sottomenù ===
    if data == "info:menu":
        await _edit_panel_media(context, chat_id, q.message.message_id, None, "*Info — Centro informativo BPFAM*", _kb_info_menu())
        return

    if data == "info:delivery":
        await _edit_panel_media(context, chat_id, q.message.message_id, None, PAGES["info_delivery"], _kb_back_to_info_root())
        return

    if data == "info:meetup":
        await _edit_panel_media(context, chat_id, q.message.message_id, None, PAGES["info_meetup"], _kb_back_to_info_root())
        return

    if data == "info:point":
        await _edit_panel_media(context, chat_id, q.message.message_id, None, PAGES["info_point"], _kb_back_to_info_root())
        return

    # === CONTATTI ===
    if data == "info:contacts":
        await _edit_panel_media(context, chat_id, q.message.message_id, None, contacts_caption(), _kb_back_to_info_root())
        return

    # Qualsiasi altra sezione tua (menu/recensioni/ship/pointattivi) resta come prima:
    if data.startswith("sec:"):
        key = data.split(":", 1)[1]
        text = f"📄 Sezione: *{key}*\n\n(Contenuto provvisorio)"
        await _edit_panel_media(context, chat_id, q.message.message_id, None, text, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="home")]]))
        return

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong!", protect_content=True)

# ===== ADMIN =====
async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await _notify_admin_attempt(context, update.effective_user, "/utenti"); return
    await update.message.reply_text(f"👥 Utenti registrati: {count_users()}", protect_content=True)

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
        protect_content=True,
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
                protect_content=True,
            )
    except Exception as e:
        logger.exception("Errore nel backup automatico")
        if ADMIN_ID:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Errore nel backup: {e}", protect_content=True)

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await _notify_admin_attempt(context, update.effective_user, "/backup"); return
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = Path(BACKUP_DIR) / f"manual_backup_{ts}.db"
        shutil.copy2(DB_FILE, backup_path)
        await update.message.reply_document(InputFile(str(backup_path)), caption="💾 Backup manuale completato.", protect_content=True)
        logger.info(f"💾 Backup manuale eseguito: {backup_path}")
    except Exception as e:
        logger.exception("Errore backup manuale")
        await update.message.reply_text(f"❌ Errore durante il backup manuale: {e}", protect_content=True)

async def ultimo_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await _notify_admin_attempt(context, update.effective_user, "/ultimo_backup"); return
    p = Path(BACKUP_DIR)
    if not p.exists():
        await update.message.reply_text("Nessun backup trovato.", protect_content=True); return
    files = sorted(p.glob("*.db"), reverse=True)
    if not files:
        await update.message.reply_text("Nessun backup disponibile.", protect_content=True); return
    ultimo = files[0]
    await update.message.reply_document(InputFile(str(ultimo)), caption=f"📦 Ultimo backup: {ultimo.name}", protect_content=True)

async def test_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await _notify_admin_attempt(context, update.effective_user, "/test_backup"); return
    await update.message.reply_text("⏳ Avvio backup di test…", protect_content=True)
    await backup_job(context)
    await update.message.reply_text("✅ Test completato.", protect_content=True)

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await _notify_admin_attempt(context, update.effective_user, "/list"); return
    users = get_all_users()
    if not users:
        await update.message.reply_text("📋 Nessun utente registrato.", protect_content=True); return
    header = f"📋 Elenco utenti ({len(users)} totali)\n"; chunk = header
    for i, u in enumerate(users, start=1):
        uname = f"@{u['username']}" if u['username'] else "-"
        line = f"{i}. {uname} ({u['user_id']})\n"
        if len(chunk) + len(line) > 3500:
            await update.message.reply_text(chunk, protect_content=True); chunk = ""
        chunk += line
    if chunk: await update.message.reply_text(chunk, protect_content=True)

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
    await update.message.reply_document(InputFile(str(csv_path)), caption=f"📤 Export utenti ({len(users)} record)", protect_content=True)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_admin(update.effective_user.id):
        txt = (
            "Comandi disponibili:\n"
            "/start – Benvenuto + menu\n"
            "/ping – Test rapido\n"
            "\n"
            "Solo Admin:\n"
            "/status /utenti /backup /ultimo_backup /test_backup /list /export /broadcast"
        )
    else:
        txt = "Comandi disponibili:\n/start – Benvenuto + menu\n/ping – Test rapido"
    await update.message.reply_text(txt, protect_content=True)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await _notify_admin_attempt(context, update.effective_user, "/broadcast"); return
    text = " ".join(context.args).strip() if context.args else ""
    if not text and update.message and update.message.reply_to_message:
        text = (update.message.reply_to_message.text or "").strip()
    if not text:
        await update.message.reply_text("ℹ️ Usa: /broadcast <testo> — oppure rispondi a un messaggio con /broadcast", protect_content=True); return
    users = get_all_users()
    if not users: await update.message.reply_text("❕ Nessun utente a cui inviare.", protect_content=True); return
    ok=fail=0; await update.message.reply_text(f"📣 Invio a {len(users)} utenti…", protect_content=True)
    for u in users:
        try:
            await context.bot.send_message(chat_id=u["user_id"], text=text, protect_content=True)
            ok += 1
            await aio.sleep(0.05)
        except Exception:
            fail += 1
            await aio.sleep(0.05)
    await update.message.reply_text(f"✅ Inviati: {ok}\n❌ Errori: {fail}", protect_content=True)

# ===== HARDENING =====
# Ignora/filtra tutto quello che non è previsto (no share/forward possible grazie a protect_content)
async def drop_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Silenzio per comandi non previsti
    return

async def webhook_guard(context: ContextTypes.DEFAULT_TYPE):
    try:
        info = await context.bot.get_webhook_info()
        if info and info.url:
            logger.warning(f"🛡️ Webhook inatteso: {info.url} — rimuovo.")
            await context.bot.delete_webhook(drop_pending_updates=True)
            logger.info("🛡️ Webhook rimosso.")
    except Exception as e:
        logger.debug(f"Guardiano webhook: {e}")

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

    # Blocca qualunque altro comando utente
    app.add_handler(MessageHandler(filters.COMMAND, drop_commands))

    # Jobs
    app.job_queue.run_repeating(webhook_guard, interval=600, first=60, name="webhook_guard")
    # backup giornaliero
    # (lo schedulo alle BACKUP_TIME UTC)
    hh, mm = BACKUP_TIME.split(":")
    app.job_queue.run_daily(backup_job, time=dtime(hour=int(hh), minute=int(mm)))

    app.run_polling(allowed_updates=["message","callback_query"])

if __name__ == "__main__":
    main()