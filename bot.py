# =====================================================
# BPFARM BOT – v3.6.3-secure-full (ptb v21+)
# - Base: tua v3.6.2
# - /restore_db MERGE (non cancella utenti)
# - Backup rotante (7 giorni)
# - Anti-flood
# - FIX iPhone: backup salvabile (protect_content=False)
# - Nuovo: /backup_zip (ZIP compatibile iOS)
# - Backup notturno: invia anche il file in DM all'admin
# =====================================================

import os, csv, shutil, logging, sqlite3, asyncio as aio, aiohttp, zipfile   # <--- aggiunto zipfile
from pathlib import Path
from datetime import datetime, timezone, timedelta, date, time as dtime
from collections import defaultdict
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from telegram.error import RetryAfter, Forbidden, BadRequest, NetworkError

VERSION = "3.6.3-secure-full"

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
    # hardening: assicura colonna joined
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info('users')").fetchall()}
        if "joined" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN joined TEXT;")
            conn.commit()
    except Exception:
        pass
    conn.commit(); conn.close()

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

def get_all_users():
    conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, first_name, last_name, joined FROM users ORDER BY joined ASC")
    out = [dict(r) for r in cur.fetchall()]
    conn.close(); return out

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
async def _send_one(context, chat_id, text, kb, mode):
    return await context.bot.send_message(
        chat_id,
        text=text or "\u2063",
        parse_mode=mode,
        disable_web_page_preview=True,
        reply_markup=kb,
        protect_content=True
    )

async def _send_long(context, chat_id, text, kb=None):
    SAFE = 3800
    parts = [text] if len(text) <= SAFE else []
    if not parts:
        cur = ""
        for p in text.split("\n\n"):
            if len(cur) + len(p) < SAFE:
                cur += p + "\n\n"
            else:
                parts.append(cur); cur = p + "\n\n"
        if cur: parts.append(cur)

    last_msg = None
    for i, pt in enumerate(parts):
        last_kb = kb if i == len(parts) - 1 else None
        for mode in ("Markdown", "HTML", None):
            try:
                last_msg = await _send_one(context, chat_id, pt, last_kb, mode)
                break
            except Exception as e:
                log.warning(f"_send_long fallback ({mode}): {e}")
                continue
        await aio.sleep(0.05)
    return last_msg

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

# ---------------- SWITCH PANNELLO ----------------
async def switch_to_photo(context, chat_id, old_id, url, caption, kb):
    try: await context.bot.delete_message(chat_id,old_id)
    except: pass
    try:
        sent = await context.bot.send_photo(chat_id,photo=url,
            caption=caption,parse_mode="Markdown",
            reply_markup=kb,protect_content=True)
        return sent.message_id
    except Exception:
        await switch_to_text(context,chat_id,old_id,caption,kb)
        return None

async def switch_to_text(context, chat_id, old_id, text, kb):
    try: await context.bot.delete_message(chat_id,old_id)
    except: pass
    sent = await _send_long(context,chat_id,text,kb)
    return getattr(sent, "message_id", None)

# ---------------- HANDLERS PUBBLICI ----------------
async def start(update,context):
    add_user(update.effective_user)
    try:
        await update.message.reply_photo(photo=PHOTO_URL,caption=CAPTION_MAIN,
                                         parse_mode="Markdown",protect_content=True)
    except:
        await update.message.reply_text(CAPTION_MAIN,parse_mode="Markdown",protect_content=True)
    await _send_long(context,update.effective_chat.id,PAGE_MAIN,kb_home())

async def cb_router(update,context):
    q=update.callback_query
    if not q:return
    await q.answer()
    c=q.data; cid=q.message.chat_id; mid=q.message.message_id
    if c=="home":   await switch_to_text(context,cid,mid,PAGE_MAIN,kb_home());return
    if c=="menu":   await switch_to_text(context,cid,mid,PAGE_MENU,kb_back("home"));return
    if c=="ship":   await switch_to_text(context,cid,mid,PAGE_SHIPSPAGNA,kb_back("home"));return
    if c=="recs":   await switch_to_text(context,cid,mid,PAGE_RECENSIONI,kb_back("home"));return
    if c=="points": await switch_to_text(context,cid,mid,PAGE_POINTATTIVI,kb_back("home"));return
    if c=="info_root":
        if INFO_BANNER_URL:
            await switch_to_photo(context,cid,mid,INFO_BANNER_URL,"ℹ️ *Info — Centro informativo BPFAM*",kb_info_root())
        else:
            await switch_to_text(context,cid,mid,"ℹ️ *Info — Centro informativo BPFAM*",kb_info_root())
        return
    if c=="contacts":  await switch_to_text(context,cid,mid,PAGE_CONTACTS_TEXT,kb_back("info_root"));return
    if c=="info_menu": await switch_to_text(context,cid,mid,PAGE_INFO_MENU,kb_info_menu());return
    if c=="info_del":  await switch_to_text(context,cid,mid,PAGE_INFO_DELIVERY,kb_info_menu());return
    if c=="info_meet": await switch_to_text(context,cid,mid,PAGE_INFO_MEETUP,kb_info_menu());return
    if c=="info_point":await switch_to_text(context,cid,mid,PAGE_INFO_POINT,kb_info_menu());return

# ---------------- ANTI-FLOOD ----------------
USER_MSG_COUNT = defaultdict(int)
async def flood_guard(update, context):
    uid = update.effective_user.id
    USER_MSG_COUNT[uid] += 1
    if USER_MSG_COUNT[uid] > 10:  # >10 msg in 10s
        try:
            await context.bot.send_message(uid, "⛔ Flood rilevato. Attendi 10 secondi.")
        except: pass
        USER_MSG_COUNT[uid] = 0

async def reset_flood(context):
    USER_MSG_COUNT.clear()

# ---------------- ADMIN ----------------
def admin_only(update):
    return update.effective_user and is_admin(update.effective_user.id)

async def status_cmd(update,context):
    if not admin_only(update): return
    now=datetime.now(timezone.utc)
    nxt=next_backup_utc(); last=last_backup_file()
    await update.message.reply_text(
        f"🔎 Stato bot v{VERSION}\nUTC {now:%H:%M}\nUtenti {count_users()}\nUltimo backup {last.name if last else 'nessuno'}\nProssimo {nxt:%H:%M}",
        protect_content=True)

# --- Backup automatico + rotazione 7 giorni
async def backup_job(context):
    try:
        Path(BACKUP_DIR).mkdir(parents=True,exist_ok=True)
        out=Path(BACKUP_DIR)/f"backup_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.db"
        shutil.copy2(DB_FILE,out)

        # Rotazione: elimina backup_*.db più vecchi di 7 giorni
        now = datetime.now(timezone.utc)
        for f in Path(BACKUP_DIR).glob("backup_*.db"):
            try:
                parts = f.stem.split("_")
                ts = datetime.strptime(parts[1]+"_"+parts[2], "%Y%m%d_%H%M%S")
            except Exception:
                continue
            if (now - ts).days > 7:
                f.unlink(missing_ok=True)

        if ADMIN_ID:
            # Invia anche il file in DM all'admin (compatibile iOS)
            await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=InputFile(str(out)),
                filename=out.name,
                caption=f"✅ Backup completato: {out.name}",
                disable_content_type_detection=True,
                protect_content=False
            )
    except Exception as e: 
        log.exception(e)

# --- /restore_db: MERGE (non cancella)
async def restore_db(update, context):
    if not admin_only(update): return
    m = update.effective_message
    if not m or not m.reply_to_message or not m.reply_to_message.document:
        await update.message.reply_text("📦 Rispondi a un file .db con /restore_db")
        return
    d = m.reply_to_message.document
    if not d.file_name.lower().endswith(".db"):
        await update.message.reply_text("❌ Il file deve terminare con .db"); return

    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    tmp = Path(BACKUP_DIR) / f"import_{d.file_unique_id}.db"
    tg_file = await d.get_file()
    await tg_file.download_to_drive(custom_path=str(tmp))

    try:
        main = sqlite3.connect(DB_FILE)
        imp  = sqlite3.connect(tmp)
        main.execute("""CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name  TEXT,
            joined     TEXT
        )""")
        main.commit()

        has_users = imp.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if not has_users:
            imp.close(); main.close(); tmp.unlink(missing_ok=True)
            await update.message.reply_text("❌ Il DB importato non contiene la tabella 'users'."); return

        cols_imp = {r[1] for r in imp.execute("PRAGMA table_info('users')").fetchall()}
        has_joined = ("joined" in cols_imp)

        if has_joined:
            rows = imp.execute("SELECT user_id,username,first_name,last_name,joined FROM users").fetchall()
        else:
            rows = [(uid, un, fn, ln, None) for (uid, un, fn, ln) in
                    imp.execute("SELECT user_id,username,first_name,last_name FROM users").fetchall()]

        before = main.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        now_iso = datetime.now(timezone.utc).isoformat()

        sql = """
        INSERT INTO users (user_id, username, first_name, last_name, joined)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username   = COALESCE(excluded.username, users.username),
            first_name = COALESCE(excluded.first_name, users.first_name),
            last_name  = COALESCE(excluded.last_name,  users.last_name)
        """
        payload = [(uid, un, fn, ln, jn or now_iso) for (uid, un, fn, ln, jn) in rows]
        main.executemany(sql, payload)
        main.commit()

        after = main.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        await update.message.reply_text(f"✅ Merge completato.\n👥 Totale: {after} (+{after-before})",protect_content=True)
    except Exception as e:
        await update.message.reply_text(f"❌ Errore merge DB: {e}",protect_content=True)
    finally:
        try: imp.close()
        except: pass
        try: main.close()
        except: pass
        try: tmp.unlink(missing_ok=True)
        except: pass

# --- /backup manuale  (iPhone-friendly)
async def backup_cmd(update, context):
    if not admin_only(update): return
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    out = Path(BACKUP_DIR) / f"backup_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.db"
    shutil.copy2(DB_FILE, out)
    await update.message.reply_document(
        document=InputFile(str(out)),
        filename=out.name,
        caption=f"✅ Backup generato: {out.name}",
        disable_content_type_detection=True,
        protect_content=False   # <--- cambiato a False
    )

# --- /backup_zip (super compatibile iOS)
async def backup_zip_cmd(update, context):
    if not admin_only(update): return
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    stem = f"backup_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}"
    db_path  = Path(BACKUP_DIR)/f"{stem}.db"
    zip_path = Path(BACKUP_DIR)/f"{stem}.zip"
    shutil.copy2(DB_FILE, db_path)
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.write(db_path, arcname=db_path.name)
    await update.message.reply_document(
        document=InputFile(str(zip_path)),
        filename=zip_path.name,
        caption=f"✅ Backup ZIP: {zip_path.name}",
        disable_content_type_detection=True,
        protect_content=False
    )
    try: db_path.unlink(missing_ok=True)
    except: pass

# --- /utenti (totale + CSV)
async def utenti_cmd(update, context):
    if not admin_only(update): return
    users = get_all_users()
    n = len(users)
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    csv_path = Path(BACKUP_DIR)/f"users_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["user_id","username","first_name","last_name","joined"])
        for u in users:
            w.writerow([u["user_id"], u["username"] or "", u["first_name"] or "", u["last_name"] or "", u["joined"] or ""])
    await update.message.reply_text(f"👥 Utenti totali: {n}", protect_content=True)
    await update.message.reply_document(document=InputFile(str(csv_path)), filename=csv_path.name, protect_content=True)

# --- /help (admin)
async def help_cmd(update, context):
    if not admin_only(update): return
    msg = (
        f"<b>🛡 Pannello Admin — v{VERSION}</b>\n\n"
        "/status — stato bot / utenti / backup\n"
        "/backup — backup immediato (.db)\n"
        "/backup_zip — backup in ZIP (iOS friendly)\n"
        "/restore_db — rispondi a un .db per importare/merge\n"
        "/utenti — totale e CSV degli utenti\n"
        "/broadcast <testo> — invia a tutti\n"
        "/broadcast (in reply) — copia contenuto a tutti\n"
        "/broadcast_stop — interrompe l'invio"
    )
    await update.message.reply_text(msg, parse_mode="HTML", protect_content=True)

# --- /broadcast
BCAST_SLEEP = 0.08
BCAST_PROGRESS_EVERY = 200

async def broadcast_cmd(update, context):
    if not admin_only(update): return
    m = update.effective_message
    users = get_all_users()
    total = len(users)
    if total == 0:
        await m.reply_text("Nessun utente nel DB."); return

    context.application.bot_data["broadcast_stop"] = False

    if m.reply_to_message:
        mode = "copy"
        text_preview = m.reply_to_message.text or m.reply_to_message.caption or "(media)"
    else:
        mode = "text"
        text_body = " ".join(context.args) if context.args else None
        if not text_body:
            await m.reply_text("Uso: /broadcast <testo> oppure in reply a un contenuto /broadcast"); return
        text_preview = (text_body[:120] + "…") if len(text_body) > 120 else text_body

    sent = failed = blocked = 0
    start_msg = await m.reply_text(f"📣 Broadcast iniziato\nUtenti: {total}\nAnteprima: {text_preview}")

    for i, u in enumerate(users, start=1):
        if context.application.bot_data.get("broadcast_stop"): break
        chat_id = u["user_id"]
        try:
            if mode == "copy":
                await m.reply_to_message.copy(chat_id=chat_id, protect_content=True)
            else:
                await context.bot.send_message(chat_id=chat_id, text=text_body, protect_content=True, disable_web_page_preview=True)
            sent += 1
        except Forbidden:
            blocked += 1
        except RetryAfter as e:
            await aio.sleep(e.retry_after + 1)
            try:
                if mode == "copy":
                    await m.reply_to_message.copy(chat_id=chat_id, protect_content=True)
                else:
                    await context.bot.send_message(chat_id=chat_id, text=text_body, protect_content=True, disable_web_page_preview=True)
                sent += 1
            except Forbidden:
                blocked += 1
            except Exception:
                failed += 1
        except (BadRequest, NetworkError, Exception):
            failed += 1

        if i % BCAST_PROGRESS_EVERY == 0:
            try:
                await start_msg.edit_text(f"📣 In corso… {sent}/{total} | Bloccati {blocked} | Errori {failed}")
            except: pass
        await aio.sleep(BCAST_SLEEP)

    stopped = context.application.bot_data.get("broadcast_stop", False)
    status = "⏹️ Interrotto" if stopped else "✅ Completato"
    await start_msg.edit_text(f"{status}\nTotali: {total}\nInviati: {sent}\nBloccati: {blocked}\nErrori: {failed}")

async def broadcast_stop_cmd(update, context):
    if not admin_only(update): return
    context.application.bot_data["broadcast_stop"] = True
    await update.message.reply_text("⏹️ Broadcast: verrà interrotto al prossimo step.")

# --- Block in gruppi (come prima)
async def block_all(update,context):
    if update.effective_chat.type in ("group","supergroup") and not is_admin(update.effective_user.id):
        try: await context.bot.delete_message(update.effective_chat.id,update.effective_message.id)
        except: pass

# --- Keep alive
async def keep_alive_job(context):
    if not RENDER_URL: return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(RENDER_URL) as r:
                if r.status == 200: log.info("Ping keep-alive OK ✅")
                else: log.warning(f"Ping keep-alive fallito: {r.status}")
    except Exception as e: log.warning(f"Errore keep-alive: {e}")

# ---------------- MAIN ----------------
def main():
    if not BOT_TOKEN: raise SystemExit("BOT_TOKEN mancante")
    init_db()
    app=ApplicationBuilder().token(BOT_TOKEN).build()
    try:
        aio.get_event_loop().run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
    except Exception as e:
        log.warning(f"Webhook reset fallito: {e}")

    # Pubblici
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CallbackQueryHandler(cb_router))
    app.add_handler(MessageHandler(~filters.COMMAND, flood_guard))  # anti-flood

    # Admin
    app.add_handler(CommandHandler("status",status_cmd))
    app.add_handler(CommandHandler("restore_db",restore_db))
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("backup_zip", backup_zip_cmd))   # <--- nuovo comando
    app.add_handler(CommandHandler("utenti", utenti_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("broadcast_stop", broadcast_stop_cmd))

    # Jobs
    hhmm=parse_hhmm(BACKUP_TIME)
    now=datetime.now(timezone.utc)
    first=datetime.combine(now.date(),hhmm,tzinfo=timezone.utc)
    if first<=now:first+=timedelta(days=1)
    app.job_queue.run_repeating(backup_job,86400,first=first)   # backup ogni 24h
    app.job_queue.run_repeating(reset_flood,10)                 # reset anti-flood
    app.job_queue.run_repeating(keep_alive_job,600,first=60)    # keep-alive 10 min

    log.info(f"🚀 BPFARM BOT avviato — v{VERSION}")
    app.run_polling(drop_pending_updates=True,allowed_updates=Update.ALL_TYPES)

if __name__=="__main__": main()