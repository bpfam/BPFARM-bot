# =====================================================
# bot.py — BPFARM BOT (python-telegram-bot v21+)
# Pannello unico (edit in-place), niente duplicati
# Sezione "Info & Contatti" semplificata:
#   - "Contatti" => solo lista link (no preview), solo Back
#   - "Info"     => sottomenu Delivery / Meetup / Point
# Blindato:
#   - Utenti NON admin: qualunque messaggio non-comando viene cancellato
#   - Comandi admin silenziati per i non-admin (+ notifica all'admin)
# Backup giornaliero + utilità admin
# =====================================================

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
    MessageHandler, ContextTypes, filters
)
import telegram.error as tgerr

VERSION = "3.0-ultra-locked-single-panel"

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

PHOTO_URL = os.environ.get(
    "PHOTO_URL",
    "https://i.postimg.cc/WbpGbTBH/5-F5-DFE41-C80-D-4-FC2-B4-F6-D105844664B3.jpg",
)
CAPTION_MAIN = os.environ.get(
    "CAPTION_MAIN",
    "🏆 *Benvenuto nel bot ufficiale di BPFARM!*\n⚡ Serietà e rispetto sono la nostra identità.\n💪 Qui si cresce con impegno e determinazione."
).replace("\\n", "\n")

# Immagine per la pagina Info & Contatti
INFO_IMAGE_URL = os.environ.get(
    "INFO_IMAGE_URL",
    "https://i.postimg.cc/m2JvXFcH/9-B509-E52-0-D6-A-4-B2-E-8-DE2-68-F81-B0-E9868.png"
)

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
        "infocontatti":_normalize_env_text(os.environ.get("PAGE_INFO"), "📲 *Info & Contatti*\n\nScegli una sezione qui sotto 👇"),
        "pointattivi": _normalize_env_text(os.environ.get("PAGE_POINTATTIVI"), "📍🇮🇹 *Point Attivi*\n\n• Roma\n• Milano"),

        # Sezioni INFO
        "info_overview": _normalize_env_text(os.environ.get("PAGE_INFO_OVERVIEW"),
                           "📲 *Info & Contatti*\n\nScegli una sezione qui sotto 👇"),
        "info_delivery": _normalize_env_text(os.environ.get("PAGE_INFO_DELIVERY"),
                           "🧾 *REGOLAMENTO DELIVERY — BPFARM OFFICIAL*\n\n"
                           "1️⃣ ✅ Verifica dell’identità obbligatoria…\n\n"
                           "🚗 *SERVIZIO DELIVERY — BPFARM OFFICIAL*\n…"),
        "info_meetup":   _normalize_env_text(os.environ.get("PAGE_INFO_MEETUP"),
                           "🧾 *REGOLAMENTO MEET-UP — BPFAM OFFICIAL*\n…"),
        "info_point":    _normalize_env_text(os.environ.get("PAGE_INFO_POINT"),
                           "🌐 *BPFAM OFFICIAL POINT* 🌐\n…"),
    }

PAGES = _load_pages_from_env()

# ===== CONTATTI (JSON in ENV) =====
def _load_contacts():
    raw = os.environ.get("CONTACT_LINKS_JSON")
    default = [
        {"label":"Instagram", "url":"https://instagram.com/bpfamofficial", "emoji":"📱"},
        {"label":"Telegram", "url":"https://t.me/contattobpfam", "emoji":"💬"},
        {"label":"Canale Ufficiale", "url":"https://t.me/+CIA2nWh5thE2ZWFk", "emoji":"📢"},
        {"label":"Bot Telegram", "url":"https://t.me/Bpfarmbot", "emoji":"🤖"},
    ]
    if not raw:
        return default
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        return default
    except Exception as e:
        logger.warning(f"CONTACT_LINKS_JSON invalido: {e}")
        return default

CONTACTS = _load_contacts()

def contacts_caption() -> str:
    # Solo testo (senza preview); usiamo markdown [ancora] per evitare URL nude
    lines = [
        "💎 *BPFAM CONTATTI UFFICIALI* 💎\n",
        "Rimani connesso ai canali ufficiali BPFAM.\n",
    ]
    for c in CONTACTS:
        emoji = c.get("emoji","")
        label = c.get("label","")
        url = c.get("url","")
        lines.append(f"{emoji} *{label}*: [{label}]({url})")
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

# ===== UTILS / SECURITY =====
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

def _kb_info_root() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 Contatti", callback_data="info:contacts"),
            InlineKeyboardButton("ℹ️ Info",     callback_data="info:open"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="home")],
    ])

def _kb_info_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚚 Info Delivery", callback_data="info:delivery"),
            InlineKeyboardButton("🤝 Info Meetup",   callback_data="info:meetup"),
        ],
        [InlineKeyboardButton("📍🇮🇹 Info Point", callback_data="info:point")],
        [InlineKeyboardButton("🔙 Back", callback_data="sec:infocontatti")],
    ])

def _kb_back_to_info_root() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="sec:infocontatti")]])

def _kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="home")]])

PANEL_KEY = "panel_msg_id"

async def _edit_panel_text(context, chat_id: int, msg_id: int, text: str, kb: InlineKeyboardMarkup):
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=msg_id,
        text=text or "\u2063",
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=kb,
    )

async def _edit_panel_media(context, chat_id: int, msg_id: int,
                            photo_url: str | None,
                            caption: str,
                            kb: InlineKeyboardMarkup):
    """
    Se photo_url è fornito => edit media (foto+caption).
    Altrimenti => edit solo la caption dell'immagine esistente.
    """
    try:
        if photo_url:
            await context.bot.edit_message_media(
                chat_id=chat_id,
                message_id=msg_id,
                media=InputMediaPhoto(media=photo_url, caption=caption, parse_mode="Markdown"),
                reply_markup=kb
            )
        else:
            await context.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=msg_id,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=kb
            )
    except tgerr.BadRequest as e:
        # Se il pannello attuale NON è media e proviamo a cambiare solo caption,
        # ripieghiamo su edit_message_text
        if "message is not modified" in str(e):
            pass
        elif "message content is not modified" in str(e):
            pass
        else:
            # fallback robusto a testo
            await _edit_panel_text(context, chat_id, msg_id, caption, kb)

# Unico pannello: crea se serve, rimuove eventuale pannello precedente
async def _ensure_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    existing_id = context.user_data.get(PANEL_KEY)

    text = PAGES["main"] or "\u2063"
    kb = _kb_home()

    if existing_id:
        try:
            await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=existing_id, reply_markup=kb)
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=existing_id,
                    text=text, parse_mode="Markdown",
                    disable_web_page_preview=True, reply_markup=kb
                )
            except tgerr.BadRequest:
                pass
            return chat_id, existing_id
        except tgerr.BadRequest:
            pass  # non esiste più: creeremo un nuovo pannello

    sent = await context.bot.send_message(
        chat_id=chat_id, text=text, reply_markup=kb,
        parse_mode="Markdown", disable_web_page_preview=True
    )
    if existing_id and existing_id != sent.message_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=existing_id)
        except Exception:
            pass
    context.user_data[PANEL_KEY] = sent.message_id
    return chat_id, sent.message_id

# ===== HANDLERS UTENTE =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        add_user(user.id, user.username, user.first_name, user.last_name)
    # benvenuto (foto profilo + caption)
    try:
        await update.message.reply_photo(photo=PHOTO_URL, caption=CAPTION_MAIN, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Errore invio foto: {e}")
    await _ensure_panel(update, context)

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    chat_id = q.message.chat_id
    panel_id = q.message.message_id
    context.user_data[PANEL_KEY] = panel_id  # aggiorna l'ID pannello (pannello unico)

    data = q.data or ""

    if data == "home":
        await _edit_panel_text(context, chat_id, panel_id, PAGES["main"], _kb_home())
        return

    if data.startswith("sec:"):
        sec = data.split(":", 1)[1]
        if sec == "menu":
            await _edit_panel_text(context, chat_id, panel_id, PAGES["menu"], _kb_back()); return
        if sec == "shipspagna":
            await _edit_panel_text(context, chat_id, panel_id, PAGES["shipspagna"], _kb_back()); return
        if sec == "recensioni":
            await _edit_panel_text(context, chat_id, panel_id, PAGES["recensioni"], _kb_back()); return
        if sec == "pointattivi":
            await _edit_panel_text(context, chat_id, panel_id, PAGES["pointattivi"], _kb_back()); return
        if sec == "infocontatti":
            # Mostriamo IMMAGINE + overview + 2 bottoni (Contatti / Info)
            await _edit_panel_media(
                context, chat_id, panel_id,
                INFO_IMAGE_URL,
                PAGES.get("info_overview", "📲 *Info & Contatti*\n\nScegli una sezione qui sotto 👇"),
                _kb_info_root()
            )
            return

    # ==== SOTTO-MENU INFO & CONTATTI ====
    if data == "info:contacts":
        # Semplice: manteniamo la stessa immagine, cambiamo SOLO la caption
        await _edit_panel_media(
            context, chat_id, panel_id,
            None,                      # non tocchiamo la foto
            contacts_caption(),        # lista link (no preview)
            _kb_back_to_info_root()
        )
        return

    if data == "info:open":
        await _edit_panel_media(
            context, chat_id, panel_id,
            None,  # stessa foto
            "ℹ️ *Centro Informazioni*\n\nScegli una voce:",
            _kb_info_menu()
        )
        return

    if data == "info:delivery":
        await _edit_panel_media(context, chat_id, panel_id, None, PAGES["info_delivery"], _kb_info_menu()); return
    if data == "info:meetup":
        await _edit_panel_media(context, chat_id, panel_id, None, PAGES["info_meetup"], _kb_info_menu()); return
    if data == "info:point":
        await _edit_panel_media(context, chat_id, panel_id, None, PAGES["info_point"], _kb_info_menu()); return

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong!")

# ===== COMANDI ADMIN =====
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
            await context.bot.send_message(chat_id=u["user_id"], text=text, disable_web_page_preview=True)
            ok += 1
            await aio.sleep(0.05)
        except Exception:
            fail += 1
            await aio.sleep(0.05)
    await update.message.reply_text(f"✅ Inviati: {ok}\n❌ Errori: {fail}")

# ===== /help =====
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_admin(update.effective_user.id):
        txt = (
            "Comandi disponibili:\n"
            "/start – Benvenuto + menu\n"
            "/ping – Test rapido\n"
            "\n"
            "Solo Admin:\n"
            "/status, /utenti, /backup, /ultimo_backup, /test_backup,\n"
            "/list, /export, /broadcast <testo>"
        )
    else:
        txt = "Comandi disponibili:\n/start – Benvenuto + menu\n/ping – Test rapido"
    await update.message.reply_text(txt, disable_web_page_preview=True)

# ===== GUARDIANI =====
async def webhook_guard(context: ContextTypes.DEFAULT_TYPE):
    try:
        info = await context.bot.get_webhook_info()
        if info and info.url:
            logger.warning(f"🛡️ Webhook inatteso: {info.url} — rimuovo.")
            await context.bot.delete_webhook(drop_pending_updates=True)
            logger.info("🛡️ Webhook rimosso.")
    except Exception as e:
        logger.debug(f"Guardiano webhook: {e}")

# Anti-sharing: cancella TUTTO ciò che non è comando degli utenti non-admin
async def nuke_non_admin_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and not _is_admin(user.id):
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.effective_message.id)
        except Exception:
            pass

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

    # Pubblici
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("help", help_command))

    # Admin (non-admin: silenzio + notifica)
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

    # BLINDATO: cancella tutto ciò che non è comando dei non-admin
    app.add_handler(MessageHandler(
        (~filters.COMMAND)
        & (~filters.StatusUpdate.ALL),
        nuke_non_admin_messages
    ), group=1)

    # Job: webhook guard + backup giornaliero
    app.job_queue.run_repeating(webhook_guard, interval=600, first=60, name="webhook_guard")
    hhmm = _parse_backup_time(BACKUP_TIME)
    # trigger giornaliero approssimato
    app.job_queue.run_repeating(backup_job, interval=24*3600, first=10, name="daily_backup")

    logger.info("🤖 BPFARM bot avviato.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()