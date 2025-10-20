# =====================================================
# bot.py — BPFARM BOT (python-telegram-bot v21+)
# Pannello unico, sezioni Info & Contatti con immagine,
# anti-spam totale non-admin, admin tools completi.
# =====================================================

import os
import json
import csv
import shutil
import logging
import asyncio as aio
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta, date, time as dtime

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
import telegram.error as tgerr

VERSION = "3.2-bpfam-ultralocked"

# ---------- LOG ----------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("bpfarm-bot")

# ---------- ENV ----------
def _txt(env_key: str, default: str = "") -> str:
    v = os.environ.get(env_key)
    if not v:
        return default
    v = v.replace("\\n", "\n")
    if v.startswith("file://"):
        try:
            with open(v[7:], "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            log.warning(f"Impossibile leggere {env_key} da file: {e}")
    return v

BOT_TOKEN   = os.environ.get("BOT_TOKEN", "")
ADMIN_ID    = int(os.environ.get("ADMIN_ID", "0") or "0") or None

DB_FILE     = os.environ.get("DB_FILE", "./data/users.db")
BACKUP_DIR  = os.environ.get("BACKUP_DIR", "./backup")
BACKUP_TIME = os.environ.get("BACKUP_TIME", "03:00")

PHOTO_URL   = _txt("PHOTO_URL",
                   "https://i.postimg.cc/WbpGbTBH/5-F5-DFE41-C80-D-4-FC2-B4-F6-D105844664B3.jpg")
CAPTION_MAIN = _txt(
    "CAPTION_MAIN",
    "🏆 Benvenuto nel bot ufficiale di BPFARM!\n"
    "⚡ Serietà e rispetto sono la nostra identità.\n"
    "💪 Qui si cresce con impegno e determinazione."
)

# Immagine hero per la sezione “Info & Contatti”
INFO_IMAGE_URL = _txt("INFO_IMAGE_URL",
                      "https://i.postimg.cc/m2JvXFcH/9-B509-E52-0-D6-A-4-B2-E-8-DE2-68-F81-B0-E9868.png")

# Pagine testuali
PAGE_MAIN            = _txt("PAGE_MAIN", "")
PAGE_CONTACTS        = _txt("PAGE_CONTACTS", "💎 BPFAM CONTATTI UFFICIALI 💎")
PAGE_INFO_OVERVIEW   = _txt("PAGE_INFO_OVERVIEW", "")  # lascialo vuoto se non vuoi testo sotto la foto
PAGE_INFO_DELIVERY   = _txt("PAGE_INFO_DELIVERY", "🚚 Info Delivery")
PAGE_INFO_MEETUP     = _txt("PAGE_INFO_MEETUP", "🤝 Info Meet-Up")
PAGE_INFO_POINT      = _txt("PAGE_INFO_POINT", "📍🇮🇹 Info Point")

# Pulsanti link opzionali per i contatti
def _load_contact_links():
    raw = os.environ.get("CONTACT_LINKS_JSON", "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            out = []
            for it in data:
                t = (it.get("text") or "").strip()
                u = (it.get("url") or "").strip()
                if t and u:
                    out.append({"text": t, "url": u})
            return out
    except Exception as e:
        log.warning(f"CONTACT_LINKS_JSON non valido: {e}")
    return []
CONTACT_LINKS = _load_contact_links()

# ---------- DB ----------
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

# ---------- UTILS ----------
def is_admin(user_id: int) -> bool:
    return ADMIN_ID is not None and user_id == ADMIN_ID

async def notify_admin_attempt(context: ContextTypes.DEFAULT_TYPE, user, cmd: str):
    if not ADMIN_ID:
        return
    uname = f"@{user.username}" if (user and user.username) else "-"
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

# ---------- UI ----------
def kb_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Menù", callback_data="sec:menu")],
        [
            InlineKeyboardButton("🇪🇸 Shiip-Spagna", callback_data="sec:shipspagna"),
            InlineKeyboardButton("🎇 Recensioni",    callback_data="sec:recensioni"),
        ],
        [
            InlineKeyboardButton("📲 Info-Contatti",  callback_data="infohub"),
            InlineKeyboardButton("📍🇮🇹 Point Attivi", callback_data="sec:pointattivi"),
        ],
    ])

def kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="home")]])

def kb_infohub() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 Contatti", callback_data="contacts"),
            InlineKeyboardButton("ℹ️ Info",    callback_data="info:submenu"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="home")]
    ])

def kb_info_submenu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚚 Delivery", callback_data="info:delivery"),
            InlineKeyboardButton("🤝 Meet-Up",  callback_data="info:meetup"),
        ],
        [
            InlineKeyboardButton("📍🇮🇹 Point", callback_data="info:point"),
            InlineKeyboardButton("🔙 Back",     callback_data="info:back"),
        ]
    ])

PANEL_KEY = "panel_msg_id"
HERO_KEY  = "hero_msg_id"

async def set_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, kb: InlineKeyboardMarkup, parse_md=True):
    """Mostra o aggiorna il messaggio pannello testuale (non foto)."""
    chat_id = update.effective_chat.id
    msg_id = context.user_data.get(PANEL_KEY)

    if msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=text or "\u2063",
                parse_mode="Markdown" if parse_md else None,
                disable_web_page_preview=True,
                reply_markup=kb,
            )
            return
        except tgerr.BadRequest:
            # se non esiste più, ricreiamo
            pass

    sent = await context.bot.send_message(
        chat_id=chat_id, text=text or "\u2063",
        parse_mode="Markdown" if parse_md else None,
        disable_web_page_preview=True,
        reply_markup=kb,
        protect_content=True,
    )
    context.user_data[PANEL_KEY] = sent.message_id

async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # elimina eventuale foto hero
    hero = context.user_data.pop(HERO_KEY, None)
    if hero:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=hero)
        except Exception:
            pass
    await set_panel(update, context, PAGE_MAIN, kb_home())

# ---------- HANDLERS BASE ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user)
    try:
        await update.message.reply_photo(
            photo=PHOTO_URL, caption=CAPTION_MAIN,
            parse_mode="Markdown", protect_content=True
        )
    except Exception as e:
        log.warning(f"Invio foto benvenuto fallito: {e}")
        await update.message.reply_text(CAPTION_MAIN, parse_mode="Markdown")
    await show_home(update, context)

async def cb_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q: return
    await q.answer()

    data = q.data or ""
    # aggiorna riferimento al pannello (usiamo sempre quello del click)
    context.user_data[PANEL_KEY] = q.message.message_id

    if data == "home":
        await show_home(update, context); return

    if data == "sec:menu":
        await set_panel(update, context, _txt("PAGE_MENU", "📖 *Menù*\n\nScrivi qui il tuo menù completo."), kb_back()); return
    if data == "sec:shipspagna":
        await set_panel(update, context, _txt("PAGE_SHIPSPAGNA", "🇪🇸 *Shiip-Spagna*"), kb_back()); return
    if data == "sec:recensioni":
        await set_panel(update, context, _txt("PAGE_RECENSIONI", "🎇 *Recensioni*"), kb_back()); return
    if data == "sec:pointattivi":
        await set_panel(update, context, _txt("PAGE_POINTATTIVI", "📍🇮🇹 *Point Attivi*"), kb_back()); return

    # ---- InfoHub (immagine + pulsanti) ----
    if data == "infohub":
        # rimuovi eventuale pannello testuale per lasciare spazio alla foto
        try:
            pid = context.user_data.get(PANEL_KEY)
            if pid:
                await context.bot.delete_message(chat_id=q.message.chat_id, message_id=pid)
        except Exception:
            pass

        sent = await context.bot.send_photo(
            chat_id=q.message.chat_id,
            photo=INFO_IMAGE_URL,
            caption=None,
            reply_markup=kb_infohub(),
            protect_content=True
        )
        context.user_data[HERO_KEY] = sent.message_id
        # sotto la foto teniamo un pannello “invisibile” (se vuoi mostrare del testo, usa PAGE_INFO_OVERVIEW)
        await set_panel(update, context, PAGE_INFO_OVERVIEW, kb_infohub())
        return

    # ---- Contatti: testo + (opzionale) bottoni link ----
    if data == "contacts":
        kb = []
        if CONTACT_LINKS:
            row = []
            for i, it in enumerate(CONTACT_LINKS, start=1):
                row.append(InlineKeyboardButton(it["text"], url=it["url"]))
                if len(row) == 2:
                    kb.append(row); row=[]
            if row: kb.append(row)
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="infohub")])

        # Nessun parse_mode per evitare errori nei link (Markdown)
        await set_panel(update, context, PAGE_CONTACTS, InlineKeyboardMarkup(kb), parse_md=False)
        return

    # ---- Info sottomenu ----
    if data == "info:submenu":
        await set_panel(update, context, "\u2063", kb_info_submenu(), parse_md=False); return
    if data == "info:back":
        await set_panel(update, context, PAGE_INFO_OVERVIEW, kb_infohub()); return
    if data == "info:delivery":
        await set_panel(update, context, PAGE_INFO_DELIVERY, kb_info_submenu()); return
    if data == "info:meetup":
        await set_panel(update, context, PAGE_INFO_MEETUP, kb_info_submenu()); return
    if data == "info:point":
        await set_panel(update, context, PAGE_INFO_POINT, kb_info_submenu()); return

# ---------- ANTI-SPAM (non-admin) ----------
async def nuke_non_admin_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if u and is_admin(u.id):
        return  # consenti all'admin
    try:
        await update.effective_message.delete()
    except Exception:
        pass

# ---------- ADMIN ----------
async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/utenti"); return
    await update.message.reply_text(f"👥 Utenti registrati: {count_users()}")

def _parse_backup_time(hhmm: str) -> dtime:
    try:
        h, m = map(int, hhmm.split(":")); return dtime(hour=h, minute=m)
    except Exception:
        return dtime(hour=3, minute=0)

def _next_backup_utc() -> datetime:
    run_t = _parse_backup_time(BACKUP_TIME)
    now = datetime.now(timezone.utc)
    cand = datetime.combine(date.today(), run_t, tzinfo=timezone.utc)
    return cand if cand > now else cand + timedelta(days=1)

def _last_backup_file() -> Path | None:
    p = Path(BACKUP_DIR)
    if not p.exists(): return None
    files = sorted(p.glob("*.db"), reverse=True)
    return files[0] if files else None

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/status"); return
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
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

async def backup_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = Path(BACKUP_DIR) / f"backup_{ts}.db"
        shutil.copy2(DB_FILE, out)
        log.info(f"Backup creato: {out}")
        if ADMIN_ID:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"✅ Backup giornaliero completato.\n🕒 {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC\n📦 {out.name}",
            )
    except Exception as e:
        log.exception("Errore backup")
        if ADMIN_ID:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Errore nel backup: {e}")

async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/backup"); return
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = Path(BACKUP_DIR) / f"manual_backup_{ts}.db"
        shutil.copy2(DB_FILE, out)
        await update.message.reply_document(InputFile(str(out)), caption="💾 Backup manuale completato.")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore backup: {e}")

async def ultimo_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/ultimo_backup"); return
    p = Path(BACKUP_DIR); p.mkdir(parents=True, exist_ok=True)
    files = sorted(p.glob("*.db"), reverse=True)
    if not files:
        await update.message.reply_text("Nessun backup disponibile."); return
    await update.message.reply_document(InputFile(str(files[0])), caption=f"📦 Ultimo backup: {files[0].name}")

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
        if len(chunk)+len(line) > 3500:
            await update.message.reply_text(chunk); chunk = ""
        chunk += line
    if chunk:
        await update.message.reply_text(chunk)

async def export_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/export"); return
    users = get_all_users()
    Path("./exports").mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = Path("./exports") / f"users_export_{ts}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["user_id","username","first_name","last_name","joined"])
        for u in users:
            w.writerow([u["user_id"], u["username"] or "", u["first_name"] or "", u["last_name"] or "", u["joined"] or ""])
    await update.message.reply_document(InputFile(str(csv_path)), caption=f"📤 Export utenti ({len(users)})")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/broadcast"); return
    if not context.args and not (update.message and update.message.reply_to_message):
        await update.message.reply_text("✉️ Usa: /broadcast <testo> — oppure rispondi a un messaggio con /broadcast")
        return
    text = " ".join(context.args).strip()
    if not text and update.message and update.message.reply_to_message:
        text = (update.message.reply_to_message.text or "").strip()
    users = get_all_users()
    sent=fail=0
    await update.message.reply_text(f"📣 Invio a {len(users)} utenti…")
    for u in users:
        try:
            await context.bot.send_message(chat_id=u["user_id"], text=text,
                                           disable_web_page_preview=True, protect_content=True)
            sent += 1
        except Exception:
            fail += 1
        await aio.sleep(0.05)
    await update.message.reply_text(f"✅ Inviati: {sent}\n❌ Errori: {fail}")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        txt = (
            "Comandi:\n"
            "/start – Benvenuto + menu\n"
            "/help – Aiuto\n"
            "\n"
            "Solo Admin:\n"
            "/status, /utenti, /backup, /ultimo_backup, /test_backup,\n"
            "/list, /export, /broadcast <testo>"
        )
    else:
        txt = "Comandi:\n/start – Benvenuto + menu\n/help – Aiuto"
    await update.message.reply_text(txt)

# ---------- WEBHOOK GUARD / ANTI-CONFLICT ----------
async def webhook_guard(context: ContextTypes.DEFAULT_TYPE):
    try:
        info = await context.bot.get_webhook_info()
        if info and info.url:
            log.warning(f"Webhook inatteso: {info.url} — rimuovo.")
            await context.bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        log.debug(f"webhook_guard: {e}")

def anti_conflict_prepare(app):
    loop = aio.get_event_loop()
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
    for _ in range(6):
        try:
            loop.run_until_complete(app.bot.get_updates(timeout=1))
            return
        except tgerr.Conflict:
            loop.run_until_complete(aio.sleep(8))
        except Exception:
            loop.run_until_complete(aio.sleep(3))

# ---------- MAIN ----------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN mancante")
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    anti_conflict_prepare(app)

    # pubblici
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))

    # admin
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("ultimo_backup", ultimo_backup))
    app.add_handler(CommandHandler("test_backup", test_backup))
    app.add_handler(CommandHandler("list", list_users))
    app.add_handler(CommandHandler("export", export_users))
    app.add_handler(CommandHandler("broadcast", broadcast))

    # callback menu
    app.add_handler(CallbackQueryHandler(cb_router))

    # blocca qualunque altro comando dei non-admin
    app.add_handler(MessageHandler(filters.COMMAND, lambda u, c: None))

    # anti-spam totale per i non-admin (qualsiasi messaggio)
    app.add_handler(MessageHandler(~filters.COMMAND, nuke_non_admin_messages))

    # jobs
    app.job_queue.run_repeating(webhook_guard, interval=600, first=60, name="webhook_guard")
    app.job_queue.run_daily(backup_job, time=_parse_backup_time(BACKUP_TIME), name="daily_backup")

    log.info(f"BPFARM BOT {VERSION} avviato.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()