# =====================================================
# BPFARM BOT – v3.6.1-secure-lite (ptb v21+)
# - Come v3.6.0-broadcast ma con:
#   ✅ Backup rotante (elimina vecchi >7 giorni)
#   ✅ Anti-Flood (limita spam utenti)
# =====================================================

import os, csv, shutil, logging, sqlite3, asyncio as aio, aiohttp
from pathlib import Path
from datetime import datetime, timezone, timedelta, date, time as dtime
from collections import defaultdict
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from telegram.error import RetryAfter, Forbidden, BadRequest, NetworkError

VERSION = "3.6.1-secure-lite"

# ---------------- LOG ----------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("bpfarm-bot")

# ---------------- ENV ----------------
def _txt(key, default=""):
    v = os.environ.get(key)
    if not v: return default
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
BACKUP_TIME = os.environ.get("BACKUP_TIME", "03:00")
RENDER_URL  = os.environ.get("RENDER_URL")

PHOTO_URL   = _txt("PHOTO_URL","https://i.postimg.cc/WbpGbTBH/5-F5-DFE41-C80-D-4-FC2-B4-F6-D105844664B3.jpg")
CAPTION_MAIN= _txt("CAPTION_MAIN","🏆 *Benvenuto nel bot ufficiale di BPFARM!*\n⚡ Serietà e rispetto sono la nostra identità.\n💪 Qui si cresce con impegno e determinazione.")
INFO_BANNER_URL=_txt("INFO_BANNER_URL","https://i.postimg.cc/m2JvXFcH/9-B509-E52-0-D6-A-4-B2-E-8-DE2-68-F81-B0-E9868.png")

PAGE_MAIN        = _txt("PAGE_MAIN", "")
PAGE_MENU        = _txt("PAGE_MENU", "📖 *Menù*\n\nScrivi qui il tuo menù completo.")
PAGE_SHIPSPAGNA  = _txt("PAGE_SHIPSPAGNA", "🇪🇸 *Shiip-Spagna*\n\nInfo e regole spedizioni.")
PAGE_RECENSIONI  = _txt("PAGE_RECENSIONI", "🎇 *Recensioni*\n\n⭐️ “Ottimo servizio!”")
PAGE_POINTATTIVI = _txt("PAGE_POINTATTIVI", "📍🇮🇹 *Point Attivi*\n\n• Roma\n• Milano")
PAGE_CONTACTS_TEXT = _txt("PAGE_CONTACTS_TEXT", "💎 *BPFAM CONTATTI UFFICIALI* 💎")

# ---------------- DB ----------------
def init_db():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        joined TEXT
    )""")
    conn.commit(); conn.close()

def add_user(u):
    if not u: return
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""INSERT OR IGNORE INTO users
        (user_id, username, first_name, last_name, joined)
        VALUES (?, ?, ?, ?, ?)""",
        (u.id, u.username, u.first_name, u.last_name, datetime.now(timezone.utc).isoformat()))
    conn.commit(); conn.close()

def count_users():
    conn = sqlite3.connect(DB_FILE)
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close(); return n

def get_all_users():
    conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, first_name, last_name, joined FROM users ORDER BY joined ASC")
    data = [dict(r) for r in cur.fetchall()]
    conn.close(); return data

# ---------------- UTILS ----------------
def is_admin(uid): return ADMIN_ID and uid == ADMIN_ID
def parse_hhmm(h): 
    try: h,m=map(int,h.split(":")); return dtime(h,m)
    except: return dtime(3,0)
def next_backup_utc():
    t=parse_hhmm(BACKUP_TIME); now=datetime.now(timezone.utc)
    nxt=datetime.combine(date.today(),t,tzinfo=timezone.utc)
    return nxt if nxt>now else nxt+timedelta(days=1)

# ---------------- BACKUP ROTANTE ----------------
async def backup_job(context):
    try:
        Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = Path(BACKUP_DIR)/f"backup_{ts}.db"
        shutil.copy2(DB_FILE, out)

        # 🔒 Elimina backup più vecchi di 7 giorni
        now = datetime.now(timezone.utc)
        for f in Path(BACKUP_DIR).glob("backup_*.db"):
            try:
                datepart = f.stem.split("_")[1]
                dt = datetime.strptime(datepart, "%Y%m%d")
                if (now - dt).days > 7:
                    f.unlink(missing_ok=True)
            except Exception:
                pass

        if ADMIN_ID:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"✅ Backup completato: {out.name}", protect_content=True)
    except Exception as e:
        log.exception(e)

# ---------------- ANTI-FLOOD ----------------
USER_MSG_COUNT = defaultdict(int)
async def flood_guard(update, context):
    uid = update.effective_user.id
    USER_MSG_COUNT[uid] += 1
    if USER_MSG_COUNT[uid] > 10:  # più di 10 messaggi in 10 secondi
        try:
            await context.bot.send_message(uid, "⛔ Flood rilevato. Attendi 10 secondi.")
        except:
            pass
        USER_MSG_COUNT[uid] = 0

async def reset_flood(context):
    USER_MSG_COUNT.clear()

# ---------------- INTERFACCIA BASE ----------------
def kb_home():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Menù",callback_data="menu")],
        [InlineKeyboardButton("SHIIP🇮🇹📦🇪🇺",callback_data="ship"),
         InlineKeyboardButton("🎇 Recensioni",callback_data="recs")],
        [InlineKeyboardButton("📲 Info-Contatti",callback_data="info_root"),
         InlineKeyboardButton("📍🇮🇹 Point Attivi",callback_data="points")]
    ])
def kb_back(to): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back",callback_data=to)]])

async def switch_to_text(context, chat_id, old_id, text, kb):
    try: await context.bot.delete_message(chat_id, old_id)
    except: pass
    await context.bot.send_message(chat_id, text=text, parse_mode="Markdown",
                                   reply_markup=kb, disable_web_page_preview=True, protect_content=True)

# ---------------- HANDLER BASE ----------------
async def start(update, context):
    add_user(update.effective_user)
    try:
        await update.message.reply_photo(photo=PHOTO_URL, caption=CAPTION_MAIN, parse_mode="Markdown", protect_content=True)
    except:
        await update.message.reply_text(CAPTION_MAIN, parse_mode="Markdown", protect_content=True)
    await update.message.reply_text(PAGE_MAIN or " ", reply_markup=kb_home(), parse_mode="Markdown")

async def cb_router(update, context):
    q=update.callback_query
    if not q:return
    await q.answer()
    c=q.data; cid=q.message.chat_id; mid=q.message.message_id
    if c=="home": await switch_to_text(context,cid,mid,PAGE_MAIN,kb_home())
    elif c=="menu": await switch_to_text(context,cid,mid,PAGE_MENU,kb_back("home"))
    elif c=="ship": await switch_to_text(context,cid,mid,PAGE_SHIPSPAGNA,kb_back("home"))
    elif c=="recs": await switch_to_text(context,cid,mid,PAGE_RECENSIONI,kb_back("home"))
    elif c=="points": await switch_to_text(context,cid,mid,PAGE_POINTATTIVI,kb_back("home"))
    elif c=="info_root":
        await switch_to_text(context,cid,mid,"ℹ️ *Info — Centro informativo BPFAM*",kb_back("home"))
    elif c=="contacts":
        await switch_to_text(context,cid,mid,PAGE_CONTACTS_TEXT,kb_back("info_root"))

# ---------------- ADMIN ----------------
async def status_cmd(update, context):
    if not is_admin(update.effective_user.id): return
    now=datetime.now(timezone.utc)
    await update.message.reply_text(
        f"🔎 Stato bot v{VERSION}\nUTC {now:%H:%M}\nUtenti {count_users()}",
        protect_content=True)

# ---------------- MAIN ----------------
def main():
    if not BOT_TOKEN: raise SystemExit("BOT_TOKEN mancante")
    init_db()
    app=ApplicationBuilder().token(BOT_TOKEN).build()
    aio.get_event_loop().run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(cb_router))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler(~filters.COMMAND, flood_guard))

    # Jobs
    hhmm=parse_hhmm(BACKUP_TIME)
    now=datetime.now(timezone.utc)
    first=datetime.combine(now.date(),hhmm,tzinfo=timezone.utc)
    if first<=now:first+=timedelta(days=1)
    app.job_queue.run_repeating(backup_job,86400,first=first)
    app.job_queue.run_repeating(reset_flood,10)  # reset contatori flood

    log.info(f"🚀 BPFARM BOT avviato — v{VERSION}")
    app.run_polling(drop_pending_updates=True,allowed_updates=Update.ALL_TYPES)

if __name__=="__main__": main()