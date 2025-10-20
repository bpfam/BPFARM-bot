# =====================================================
# BPFARM BOT – v3.5 (python-telegram-bot v21+)
# - Home con 5 bottoni
# - "Info-Contatti": banner (foto) + 2 bottoni (📦 Contatti / ℹ️ Info)
# - "Info": sottomenu con 3 cartelle (Delivery / Meet-Up / Point)
# - Pannello unico: switch foto<->testo senza duplicati
# - Anti-spam: i non-admin non possono inviare; blocco inoltro su TUTTI gli invii del bot
# - Admin only: /status /utenti /backup /ultimo_backup /test_backup /list /export /broadcast
# - Backup giornaliero alle BACKUP_TIME (UTC)
# - Anti-conflict: rimuove webhook e occupa polling
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

VERSION = "3.5-bpfam-infohub"

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

DB_FILE     = os.environ.get("DB_FILE", "./data/users.db")
BACKUP_DIR  = os.environ.get("BACKUP_DIR", "./backup")
BACKUP_TIME = os.environ.get("BACKUP_TIME", "03:00")  # UTC

PHOTO_URL   = _txt("PHOTO_URL",
                   "https://i.postimg.cc/WbpGbTBH/5-F5-DFE41-C80-D-4-FC2-B4-F6-D105844664B3.jpg")
CAPTION_MAIN = _txt("CAPTION_MAIN",
                    "🏆 *Benvenuto nel bot ufficiale di BPFARM!*\n"
                    "⚡ Serietà e rispetto sono la nostra identità.\n"
                    "💪 Qui si cresce con impegno e determinazione.")

# Banner nero/oro della sezione Info & Contatti
INFO_BANNER_URL = _txt("INFO_BANNER_URL",
                       "https://i.postimg.cc/m2JvXFcH/9-B509-E52-0-D6-A-4-B2-E-8-DE2-68-F81-B0-E9868.png")

# Pagine home/altro
PAGE_MAIN        = _txt("PAGE_MAIN", "")
PAGE_MENU        = _txt("PAGE_MENU", "📖 *Menù*\n\nScrivi qui il tuo menù completo.")
PAGE_SHIPSPAGNA  = _txt("PAGE_SHIPSPAGNA", "🇪🇸 *Shiip-Spagna*\n\nInfo e regole spedizioni.")
PAGE_RECENSIONI  = _txt("PAGE_RECENSIONI", "🎇 *Recensioni*\n\n⭐️ “Ottimo servizio!”")
PAGE_POINTATTIVI = _txt("PAGE_POINTATTIVI", "📍🇮🇹 *Point Attivi*\n\n• Roma\n• Milano")

# Pagine Info-Contatti
PAGE_CONTACTS_TEXT = _txt("PAGE_CONTACTS_TEXT", "💎 *BPFAM CONTATTI UFFICIALI* 💎\n(aggiungi PAGE_CONTACTS_TEXT)")
PAGE_INFO_MENU     = _txt("PAGE_INFO_MENU",
                          "ℹ️ *Info — Centro informativo BPFAM*\n\nSeleziona una voce:")
PAGE_INFO_DELIVERY = _txt("PAGE_INFO_DELIVERY", "🚚 *Info Delivery*\n(Testo non impostato)")
PAGE_INFO_MEETUP   = _txt("PAGE_INFO_MEETUP",   "🤝 *Info Meet-Up*\n(Testo non impostato)")
PAGE_INFO_POINT    = _txt("PAGE_INFO_POINT",    "📍🇮🇹 *Info Point*\n(Testo non impostato)")

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
            protect_content=True
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
        [
            InlineKeyboardButton("🇪🇸 Shiip-Spagna", callback_data="sec:ship"),
            InlineKeyboardButton("🎇 Recensioni",    callback_data="sec:recs"),
        ],
        [
            InlineKeyboardButton("📲 Info-Contatti",  callback_data="info:root"),
            InlineKeyboardButton("📍🇮🇹 Point Attivi", callback_data="sec:points"),
        ],
    ])

def kb_back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="home")]])

def kb_info_root() -> InlineKeyboardMarkup:
    # Banner con due bottoni
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Contatti", callback_data="contacts:open"),
         InlineKeyboardButton("ℹ️ Info",     callback_data="info:menu")],
        [InlineKeyboardButton("🔙 Back",      callback_data="home")]
    ])

def kb_info_menu() -> InlineKeyboardMarkup:
    # 3 cartelle
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚚 Info Delivery", callback_data="info:delivery")],
        [InlineKeyboardButton("🤝 Info Meet-Up",  callback_data="info:meetup")],
        [InlineKeyboardButton("📍🇮🇹 Info Point",  callback_data="info:point")],
        [InlineKeyboardButton("🔙 Back",          callback_data="info:root")]
    ])

# ---------------- PANNELLO (UNICO) ----------------
PANEL_KEY = "panel_msg_id"
PANEL_IS_PHOTO = "panel_is_photo"  # True se il pannello corrente è foto

async def switch_to_photo(context, chat_id: int, old_msg_id: int, photo_url: str, caption: str, kb):
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
    except Exception:
        pass
    sent = await context.bot.send_photo(
        chat_id=chat_id, photo=photo_url, caption=caption or "\u2063",
        parse_mode="Markdown", reply_markup=kb, protect_content=True
    )
    context.user_data[PANEL_KEY] = sent.message_id
    context.user_data[PANEL_IS_PHOTO] = True
    return sent.message_id

async def switch_to_text(context, chat_id: int, old_msg_id: int, text: str, kb):
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
    except Exception:
        pass
    sent = await context.bot.send_message(
        chat_id=chat_id, text=text or "\u2063",
        parse_mode="Markdown", disable_web_page_preview=True,
        reply_markup=kb, protect_content=True
    )
    context.user_data[PANEL_KEY] = sent.message_id
    context.user_data[PANEL_IS_PHOTO] = False
    return sent.message_id

async def ensure_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    # foto principale
    try:
        await context.bot.send_photo(
            chat_id=chat_id, photo=PHOTO_URL,
            caption=CAPTION_MAIN, parse_mode="Markdown", protect_content=True
        )
    except Exception as e:
        log.warning(f"Foto home non inviata: {e}")
        await context.bot.send_message(
            chat_id=chat_id, text=CAPTION_MAIN,
            parse_mode="Markdown", disable_web_page_preview=True, protect_content=True
        )
    # pannello testuale home
    sent = await context.bot.send_message(
        chat_id=chat_id, text=PAGE_MAIN or "\u2063",
        parse_mode="Markdown", disable_web_page_preview=True,
        reply_markup=kb_home(), protect_content=True
    )
    context.user_data[PANEL_KEY] = sent.message_id
    context.user_data[PANEL_IS_PHOTO] = False

# ---------------- HANDLERS PUBBLICI ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user(update.effective_user)
    try:
        await update.message.reply_photo(
            photo=PHOTO_URL, caption=CAPTION_MAIN,
            parse_mode="Markdown", protect_content=True
        )
    except Exception as e:
        log.warning(f"Start photo err: {e}")
        await update.message.reply_text(
            CAPTION_MAIN, parse_mode="Markdown",
            disable_web_page_preview=True, protect_content=True
        )
    # crea pannello home
    sent = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=PAGE_MAIN or "\u2063",
        parse_mode="Markdown", disable_web_page_preview=True,
        reply_markup=kb_home(), protect_content=True
    )
    context.user_data[PANEL_KEY] = sent.message_id
    context.user_data[PANEL_IS_PHOTO] = False

async def cb_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q: return
    await q.answer()

    chat_id = q.message.chat_id
    panel_id = q.message.message_id
    data = q.data or ""
    context.user_data[PANEL_KEY] = panel_id

    # HOME
    if data == "home":
        await switch_to_text(context, chat_id, panel_id, PAGE_MAIN, kb_home())
        return

    # SEZIONI BASE
    if data == "sec:menu":
        await switch_to_text(context, chat_id, panel_id, PAGE_MENU, kb_back_home()); return
    if data == "sec:ship":
        await switch_to_text(context, chat_id, panel_id, PAGE_SHIPSPAGNA, kb_back_home()); return
    if data == "sec:recs":
        await switch_to_text(context, chat_id, panel_id, PAGE_RECENSIONI, kb_back_home()); return
    if data == "sec:points":
        await switch_to_text(context, chat_id, panel_id, PAGE_POINTATTIVI, kb_back_home()); return

    # INFO & CONTATTI ROOT (banner + 2 bottoni)
    if data == "info:root":
        caption = "ℹ️ *Info — Centro informativo BPFAM*"
        if INFO_BANNER_URL:
            await switch_to_photo(context, chat_id, panel_id, INFO_BANNER_URL, caption, kb_info_root())
        else:
            await switch_to_text(context, chat_id, panel_id, caption, kb_info_root())
        return

    # CONTATTI (solo testo lungo)
    if data == "contacts:open":
        await switch_to_text(context, chat_id, panel_id, PAGE_CONTACTS_TEXT,
                             InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="info:root")]]))
        return

    # INFO MENU (3 cartelle)
    if data == "info:menu":
        await switch_to_text(context, chat_id, panel_id, PAGE_INFO_MENU, kb_info_menu()); return

    if data == "info:delivery":
        await switch_to_text(context, chat_id, panel_id, PAGE_INFO_DELIVERY, kb_info_menu()); return
    if data == "info:meetup":
        await switch_to_text(context, chat_id, panel_id, PAGE_INFO_MEETUP, kb_info_menu()); return
    if data == "info:point":
        await switch_to_text(context, chat_id, panel_id, PAGE_INFO_POINT, kb_info_menu()); return

# ---------------- ANTI-MESSAGGI (non-admin) ----------------
async def block_everything(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ignora ogni messaggio dei non-admin; se in gruppi e con permessi, prova a cancellarlo."""
    u = update.effective_user
    if u and is_admin(u.id):
        return
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup"):
        try:
            await context.bot.delete_message(chat_id=chat.id, message_id=update.effective_message.id)
        except Exception:
            pass
    return  # in privato: silenzio totale

# ---------------- ADMIN ----------------
async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/utenti"); return
    await update.message.reply_text(f"👥 Utenti registrati: {count_users()}", protect_content=True)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/status"); return
    now_utc = datetime.now(timezone.utc)
    nxt = next_backup_utc()
    last = last_backup_file()
    last_line = f"📦 Ultimo backup: {last.name}" if last else "📦 Ultimo backup: nessuno"
    await update.message.reply_text(
        "🔎 **Stato bot**\n"
        f"• Versione: {VERSION}\n"
        f"• Ora server (UTC): {now_utc:%Y-%m-%d %H:%M:%S}\n"
        f"• Prossimo backup (UTC): {nxt:%Y-%m-%d %H:%M}\n"
        f"• Utenti registrati: {count_users()}\n"
        f"{last_line}",
        parse_mode="Markdown", disable_web_page_preview=True, protect_content=True
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
                protect_content=True
            )
    except Exception as e:
        log.exception("Errore backup")
        if ADMIN_ID:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ Errore nel backup: {e}", protect_content=True)

async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/backup"); return
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = Path(BACKUP_DIR) / f"manual_backup_{ts}.db"
        shutil.copy2(DB_FILE, out)
        await update.message.reply_document(InputFile(str(out)), caption="💾 Backup manuale completato.", protect_content=True)
    except Exception as e:
        await update.message.reply_text(f"❌ Errore backup: {e}", protect_content=True)

async def ultimo_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/ultimo_backup"); return
    p = Path(BACKUP_DIR); p.mkdir(parents=True, exist_ok=True)
    files = sorted(p.glob("*.db"), reverse=True)
    if not files:
        await update.message.reply_text("Nessun backup disponibile.", protect_content=True); return
    await update.message.reply_document(InputFile(str(files[0])), caption=f"📦 Ultimo backup: {files[0].name}", protect_content=True)

async def test_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/test_backup"); return
    await update.message.reply_text("⏳ Avvio backup di test…", protect_content=True)
    await backup_job(context)
    await update.message.reply_text("✅ Test completato.", protect_content=True)

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/list"); return
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
    if chunk:
        await update.message.reply_text(chunk, protect_content=True)

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
    await update.message.reply_document(InputFile(str(csv_path)), caption=f"📤 Export utenti ({len(users)})", protect_content=True)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await notify_admin_attempt(context, update.effective_user, "/broadcast"); return
    text = " ".join(context.args).strip() if context.args else ""
    if not text and update.message and update.message.reply_to_message:
        text = (update.message.reply_to_message.text or "").strip()
    if not text:
        await update.message.reply_text("ℹ️ Usa: /broadcast <testo> — oppure rispondi a un messaggio con /broadcast", protect_content=True)
        return
    users = get_all_users()
    if not users:
        await update.message.reply_text("❕ Nessun utente a cui inviare.", protect_content=True)
        return
    ok=fail=0
    await update.message.reply_text(f"📣 Invio a {len(users)} utenti…", protect_content=True)
    for u in users:
        try:
            await context.bot.send_message(chat_id=u["user_id"], text=text, protect_content=True)
            ok += 1
        except Exception:
            fail += 1
        await aio.sleep(0.05)
    await update.message.reply_text(f"✅ Inviati: {ok}\n❌ Errori: {fail}", protect_content=True)

# ---------------- /help ----------------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        txt = (
            "Comandi:\n"
            "/start – Benvenuto + home\n"
            "/help – Aiuto\n"
            "/ping – Test rapido\n\n"
            "Solo Admin:\n"
            "/status /utenti\n"
            "/backup /ultimo_backup /test_backup\n"
            "/list /export /broadcast"
        )
    else:
        txt = "/start – Benvenuto + home\n/help – Aiuto\n/ping – Test rapido"
    await update.message.reply_text(txt, protect_content=True)

# ---------------- WEBHOOK GUARD / ANTI-CONFLICT ----------------
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
    try:
        loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
        log.info("🔧 Webhook rimosso + pending updates droppati.")
    except Exception as e:
        log.warning(f"delete_webhook err: {e}")
    for _ in range(6):
        try:
            loop.run_until_complete(app.bot.get_updates(timeout=1))
            log.info("✅ Slot polling acquisito.")
            return
        except tgerr.Conflict:
            loop.run_until_complete(aio.sleep(8))
        except Exception:
            loop.run_until_complete(aio.sleep(3))

# ---------------- MAIN ----------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN mancante")
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    anti_conflict_prepare(app)

    # Pubblici
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ping", lambda u,c: u.message.reply_text("🏓 Pong!", protect_content=True)))

    # Admin
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("ultimo_backup", ultimo_backup))
    app.add_handler(CommandHandler("test_backup", test_backup))
    app.add_handler(CommandHandler("list", list_users))
    app.add_handler(CommandHandler("export", export_users))
    app.add_handler(CommandHandler("broadcast", broadcast))

    # Menu callback
    app.add_handler(CallbackQueryHandler(cb_router))

    # Anti-spam non-admin
    app.add_handler(MessageHandler(~filters.COMMAND, block_everything))

    # Jobs
    app.job_queue.run_repeating(webhook_guard, interval=600, first=60, name="webhook_guard")
    hhmm = parse_hhmm(BACKUP_TIME)
    now_utc = datetime.now(timezone.utc)
    first_run = datetime.combine(now_utc.date(), hhmm, tzinfo=timezone.utc)
    if first_run <= now_utc:
        first_run += timedelta(days=1)
    app.job_queue.run_repeating(backup_job, interval=86400, first=first_run, name="daily_backup")

    log.info(f"🚀 BPFARM BOT avviato — v{VERSION}")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()