# =====================================================
# BPFARM BOT – v3.5.3-fix-help (ptb v21+)
# - Identico alla 3.5.2 ma:
#   * /help ora funziona (usa HTML, nessun errore Markdown)
#   * /backup /status /restore_db blindati (solo admin)
#   * delete_webhook protetto (no conflict)
# =====================================================

import os, csv, shutil, logging, sqlite3, asyncio as aio
from pathlib import Path
from datetime import datetime, timezone, timedelta, date, time as dtime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

VERSION = "3.5.3-fix-help"

# ---------------- LOG ----------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("bpfarm-bot")

# ---------------- ENV ----------------
def _txt(key, default=""):
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
BACKUP_TIME = os.environ.get("BACKUP_TIME", "03:00")

PHOTO_URL   = _txt("PHOTO_URL","https://i.postimg.cc/WbpGbTBH/5-F5-DFE41-C80-D-4-FC2-B4-F6-D105844664B3.jpg")
CAPTION_MAIN= _txt("CAPTION_MAIN","🏆 *Benvenuto nel bot ufficiale di BPFARM!*\n⚡ Serietà e rispetto sono la nostra identità.\n💪 Qui si cresce con impegno e determinazione.")
INFO_BANNER_URL=_txt("INFO_BANNER_URL","https://i.postimg.cc/m2JvXFcH/9-B509-E52-0-D6-A-4-B2-E-8-DE2-68-F81-B0-E9868.png")

PAGE_MAIN        = _txt("PAGE_MAIN", "")
PAGE_MENU        = _txt("PAGE_MENU", "📖 *Menù*\n\nScrivi qui il tuo menù completo.")
PAGE_SHIPSPAGNA  = _txt("PAGE_SHIPSPAGNA", "🇪🇸 *Shiip-Spagna*\n\nInfo e regole spedizioni.")
PAGE_RECENSIONI  = _txt("PAGE_RECENSIONI", "🎇 *Recensioni*\n\n⭐️ “Ottimo servizio!”")
PAGE_POINTATTIVI = _txt("PAGE_POINTATTIVI", "📍🇮🇹 *Point Attivi*\n\n• Roma\n• Milano")
PAGE_CONTACTS_TEXT = _txt("PAGE_CONTACTS_TEXT", "💎 *BPFAM CONTATTI UFFICIALI* 💎")
PAGE_INFO_MENU     = _txt("PAGE_INFO_MENU", "ℹ️ *Info — Centro informativo BPFAM*\n\nSeleziona una voce:")
PAGE_INFO_DELIVERY = _txt("PAGE_INFO_DELIVERY", "🚚 *Info Delivery*\n(Testo non impostato)")
PAGE_INFO_MEETUP   = _txt("PAGE_INFO_MEETUP", "🤝 *Info Meet-Up*\n(Testo non impostato)")
PAGE_INFO_POINT    = _txt("PAGE_INFO_POINT", "📍🇮🇹 *Info Point*\n(Testo non impostato)")

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
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info('users')").fetchall()}
        if "joined" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN joined TEXT;")
            conn.commit()
    except Exception:
        pass
    conn.commit()
    conn.close()

def add_user(u):
    if not u: return
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""INSERT OR IGNORE INTO users 
        (user_id, username, first_name, last_name, joined)
        VALUES (?, ?, ?, ?, ?)""",
        (u.id, u.username, u.first_name, u.last_name,
         datetime.now(timezone.utc).isoformat()))
    conn.commit(); conn.close()

def count_users():
    conn = sqlite3.connect(DB_FILE)
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close(); return n

# ---------------- UTILS ----------------
def is_admin(uid): return ADMIN_ID and uid == ADMIN_ID

def parse_hhmm(h):
    try: h,m = map(int,h.split(":")); return dtime(h,m)
    except: return dtime(3,0)

def next_backup_utc():
    t = parse_hhmm(BACKUP_TIME)
    now = datetime.now(timezone.utc)
    nxt = datetime.combine(date.today(),t,tzinfo=timezone.utc)
    return nxt if nxt>now else nxt+timedelta(days=1)

def last_backup_file():
    p=Path(BACKUP_DIR)
    if not p.exists(): return None
    f=sorted(p.glob("*.db"),reverse=True)
    return f[0] if f else None

# ---------------- TEXT SENDER ----------------
async def _send_long(context, chat_id, text, kb=None):
    SAFE=3800
    if len(text)<=SAFE:
        return await context.bot.send_message(chat_id, text=text or "\u2063",
            parse_mode="Markdown", disable_web_page_preview=True,
            reply_markup=kb, protect_content=True)
    parts=[]
    cur=""
    for p in text.split("\n\n"):
        if len(cur)+len(p)<SAFE: cur+=p+"\n\n"
        else: parts.append(cur); cur=p+"\n\n"
    if cur: parts.append(cur)
    for i,pt in enumerate(parts):
        await context.bot.send_message(chat_id,text=pt,
            parse_mode="Markdown",disable_web_page_preview=True,
            reply_markup=(kb if i==len(parts)-1 else None),
            protect_content=True)
        await aio.sleep(0.05)

# ---------------- KEYBOARDS ----------------
def kb_home():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Menù",callback_data="menu")],
        [InlineKeyboardButton("SHIIP🇮🇹📦🇪🇺",callback_data="ship"),
         InlineKeyboardButton("🎇 Recensioni",callback_data="recs")],
        [InlineKeyboardButton("📲 Info-Contatti",callback_data="info_root"),
         InlineKeyboardButton("📍🇮🇹 Point Attivi",callback_data="points")]
    ])

def kb_back(to): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back",callback_data=to)]])

def kb_info_root():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Contatti",callback_data="contacts"),
         InlineKeyboardButton("ℹ️ Info",callback_data="info_menu")],
        [InlineKeyboardButton("🔙 Back",callback_data="home")]
    ])

def kb_info_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚚 Delivery",callback_data="info_del")],
        [InlineKeyboardButton("🤝 Meet-Up",callback_data="info_meet")],
        [InlineKeyboardButton("📍🇮🇹 Point",callback_data="info_point")],
        [InlineKeyboardButton("🔙 Back",callback_data="info_root")]
    ])

# ---------------- HANDLERS ----------------
async def start(update,context):
    add_user(update.effective_user)
    try: await update.message.reply_photo(photo=PHOTO_URL,caption=CAPTION_MAIN,
            parse_mode="Markdown",protect_content=True)
    except: await update.message.reply_text(CAPTION_MAIN,parse_mode="Markdown")
    await _send_long(context,update.effective_chat.id,PAGE_MAIN,kb_home())

async def cb_router(update,context):
    q=update.callback_query
    if not q:return
    await q.answer()
    c=q.data; cid=q.message.chat_id; mid=q.message.message_id
    if c=="home": await _send_long(context,cid,PAGE_MAIN,kb_home());return
    if c=="menu": await _send_long(context,cid,PAGE_MENU,kb_back("home"));return
    if c=="ship": await _send_long(context,cid,PAGE_SHIPSPAGNA,kb_back("home"));return
    if c=="recs": await _send_long(context,cid,PAGE_RECENSIONI,kb_back("home"));return
    if c=="points": await _send_long(context,cid,PAGE_POINTATTIVI,kb_back("home"));return
    if c=="info_root":
        if INFO_BANNER_URL:
            await switch_to_photo(context,cid,mid,INFO_BANNER_URL,"ℹ️ *Info — Centro informativo BPFAM*",kb_info_root())
        else:
            await _send_long(context,cid,"ℹ️ *Info — Centro informativo BPFAM*",kb_info_root())
        return
    if c=="contacts": await _send_long(context,cid,PAGE_CONTACTS_TEXT,kb_back("info_root"));return
    if c=="info_menu": await _send_long(context,cid,PAGE_INFO_MENU,kb_info_menu());return
    if c=="info_del": await _send_long(context,cid,PAGE_INFO_DELIVERY,kb_info_menu());return
    if c=="info_meet": await _send_long(context,cid,PAGE_INFO_MEETUP,kb_info_menu());return
    if c=="info_point": await _send_long(context,cid,PAGE_INFO_POINT,kb_info_menu());return

# ---------------- ADMIN ----------------
async def status_cmd(update,context):
    if not is_admin(update.effective_user.id):return
    now=datetime.now(timezone.utc)
    nxt=next_backup_utc(); last=last_backup_file()
    await update.message.reply_text(
        f"🔎 Stato bot v{VERSION}\nUTC {now:%H:%M}\nUtenti {count_users()}\nUltimo backup {last.name if last else 'nessuno'}\nProssimo {nxt:%H:%M}",
        protect_content=True)

async def backup_job(context):
    try:
        Path(BACKUP_DIR).mkdir(parents=True,exist_ok=True)
        out=Path(BACKUP_DIR)/f"backup_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.db"
        shutil.copy2(DB_FILE,out)
        if ADMIN_ID:
            await context.bot.send_message(chat_id=ADMIN_ID,text=f"✅ Backup completato {out.name}",protect_content=True)
    except Exception as e: log.exception(e)

# --------- /restore_db (merge sicuro) ----------
async def restore_db(update, context):
    if not is_admin(update.effective_user.id):
        return

    m = update.effective_message
    if not m.reply_to_message or not m.reply_to_message.document:
        await update.message.reply_text("📦 Rispondi a un file .db con /restore_db")
        return

    d = m.reply_to_message.document
    if not d.file_name.endswith(".db"):
        await update.message.reply_text("❌ Il file deve terminare con .db")
        return

    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    tmp = Path(BACKUP_DIR) / f"import_{d.file_unique_id}.db"

    f = await d.get_file()
    await f.download_to_drive(custom_path=str(tmp))

    try:
        main = sqlite3.connect(DB_FILE)
        main.execute("""CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            joined TEXT
        )""")
        try: main.execute("ALTER TABLE users ADD COLUMN joined TEXT;")
        except: pass
        main.commit()

        imp = sqlite3.connect(tmp)
        imp.row_factory = sqlite3.Row
        has_users = imp.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';").fetchone()
        if not has_users:
            imp.close(); main.close(); tmp.unlink(missing_ok=True)
            await update.message.reply_text("❌ Il DB importato non contiene la tabella 'users'."); return

        cols = {r["name"] for r in imp.execute("PRAGMA table_info('users')").fetchall()}
        need_joined = ("joined" not in cols)
        sel = "SELECT user_id, username, first_name, last_name" + ("" if need_joined else ", joined") + " FROM users"
        rows = imp.execute(sel).fetchall()

        before = main.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        now_iso = datetime.now(timezone.utc).isoformat()
        to_insert = [
            (r["user_id"], r["username"], r["first_name"], r["last_name"],
             r["joined"] if (not need_joined and r["joined"]) else now_iso)
            for r in rows
        ]
        main.executemany("INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, joined) VALUES (?,?,?,?,?)", to_insert)
        main.commit()
        after = main.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        added = after - before
        imp.close(); main.close(); tmp.unlink(missing_ok=True)
        await update.message.reply_text(f"✅ Merge completato.\nAggiunti: {added}\nTotale attuale: {after}",protect_content=True)
    except Exception as e:
        await update.message.reply_text(f"❌ Errore merge DB: {e}",protect_content=True)

# --------- /backup (manuale, solo admin) ----------
async def backup_cmd(update, context):
    if not is_admin(update.effective_user.id): return
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    out = Path(BACKUP_DIR) / f"backup_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.db"
    shutil.copy2(DB_FILE, out)
    await update.message.reply_document(
        document=InputFile(str(out)),
        filename=out.name,
        caption=f"✅ Backup generato: {out.name}",
        disable_content_type_detection=True,
        protect_content=True
    )

# --------- /help (solo admin, FIX) ----------
async def help_cmd(update, context):
    if not is_admin(update.effective_user.id): return
    msg = (
        f"<b>🛡 Pannello Admin</b> — v{VERSION}<br><br>"
        "/status — stato bot/utenti/backup<br>"
        "/backup — backup immediato (invio file .db)<br>"
        "/restore_db — rispondi a un .db per importare/merge"
    )
    await update.message.reply_text(msg, parse_mode="HTML", protect_content=True)

async def block_all(update,context):
    if update.effective_chat.type in ("group","supergroup") and not is_admin(update.effective_user.id):
        try: await context.bot.delete_message(update.effective_chat.id,update.effective_message.id)
        except: pass

# ---------------- MAIN ----------------
def main():
    if not BOT_TOKEN: raise SystemExit("BOT_TOKEN mancante")
    init_db()
    app=ApplicationBuilder().token(BOT_TOKEN).build()
    try:
        aio.get_event_loop().run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
    except Exception as e:
        log.warning(f"Webhook reset fallito: {e}")

    app.add_handler(CommandHandler("start",start))
    app.add_handler(CallbackQueryHandler(cb_router))
    app.add_handler(CommandHandler("status",status_cmd))
    app.add_handler(CommandHandler("restore_db",restore_db))
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(~filters.COMMAND,block_all))

    hhmm=parse_hhmm(BACKUP_TIME)
    now=datetime.now(timezone.utc)
    first=datetime.combine(now.date(),hhmm,tzinfo=timezone.utc)
    if first<=now:first+=timedelta(days=1)
    app.job_queue.run_repeating(backup_job,86400,first=first)

    log.info(f"🚀 BPFARM BOT avviato — v{VERSION}")
    app.run_polling(drop_pending_updates=True,allowed_updates=Update.ALL_TYPES)

if __name__=="__main__": main()