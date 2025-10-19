# =====================================================
# bot.py — BPFARM BOT (python-telegram-bot v21+)
# UI: 5 bottoni in home | Pannello unico edit-in-place
# 📲 Info-Contatti: invia immagine + sotto-menù (📇 Contatti | ℹ️ Info)
# Admin ultra-blindati + Backup automatico + Anti-conflict + Webhook guard
# Versione: 3.1-info-contacts-image
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

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
import telegram.error as tgerr

VERSION = "3.1-info-contacts-image"

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
BACKUP_TIME = os.environ.get("BACKUP_TIME", "03:00")  # UTC (Render)

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

# Immagine specifica per la sezione Info & Contatti (usa link pubblico alla grafica BPFAM oro/nero)
INFO_CONTACTS_IMAGE_URL = os.environ.get("INFO_CONTACTS_IMAGE_URL", PHOTO_URL)

# ===== UTILITY TESTI (ENV) =====
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
        "main":         _normalize_env_text(os.environ.get("PAGE_MAIN"), ""),
        "menu":         _normalize_env_text(os.environ.get("PAGE_MENU"), "📖 *Menù*\n\nScrivi qui il tuo menù completo."),
        "shipspagna":   _normalize_env_text(os.environ.get("PAGE_SHIPSPAGNA"), "🇪🇸 *Shiip-Spagna*\n\nInfo e regole spedizioni."),
        "recensioni":   _normalize_env_text(os.environ.get("PAGE_RECENSIONI"), "🎇 *Recensioni*\n\n⭐️ “Ottimo servizio!”"),
        "infocontatti": _normalize_env_text(os.environ.get("PAGE_INFO"), "📲 *Info & Contatti*\nScegli una sezione:"),
        "pointattivi":  _normalize_env_text(os.environ.get("PAGE_POINTATTIVI"), "📍🇮🇹 *Point Attivi*\n\n• Roma\n• Milano"),

        # Sezioni INFO
        "info_overview": _normalize_env_text(os.environ.get("PAGE_INFO_OVERVIEW"),
            "ℹ️ *Info — Centro informativo BPFAM*\n\nSeleziona una voce: Delivery, Meet-Up o Point."
        ),

        "info_delivery": _normalize_env_text(os.environ.get("PAGE_INFO_DELIVERY"),
            "🧾 *REGOLAMENTO DELIVERY — BPFARM OFFICIAL*\n\n"
            "1️⃣ ✅ Verifica dell’identità obbligatoria per ogni consegna, a meno che tu non sia già registrato nel sistema clienti.\n\n"
            "2️⃣ 🚗 Solo una persona può ricevere l’ordine. Se il rider nota più persone o situazioni non conformi, la consegna sarà annullata immediatamente.\n\n"
            "3️⃣ ⏰ Gli orari concordati sono vincolanti. Ogni modifica va comunicata con almeno 1 ora di anticipo e motivazione valida.\n\n"
            "4️⃣ ❌ Chi non si presenta, annulla all’ultimo momento o crea problemi durante la consegna verrà bannato definitivamente dai nostri canali e servizi BPFAM.\n\n"
            "© 2025 BPFAM Official — Consegne sicure, riservate e blindate.\n\n"
            "🚗 *SERVIZIO DELIVERY — BPFAM OFFICIAL*\n\n"
            "🏡 Il Delivery BPFAM ti permette di ricevere i tuoi ordini comodamente a casa o nel punto concordato, sempre con la massima riservatezza e puntualità. "
            "⚡ Serietà, rispetto e fiducia sono i principi che guidano ogni consegna.\n\n"
            "💸 Il servizio prevede un piccolo costo aggiuntivo, stabilito in base alla distanza e alla quantità dell’ordine. Tutte le informazioni vengono comunicate in privato dal nostro staff ufficiale.\n\n"
            "✅ Dopo la verifica dell’identità e la conferma dell’ordine, verrà organizzata la consegna con data, orario e luogo precisi. "
            "❗In caso di ritardi o mancata presenza senza avviso, il servizio verrà sospeso.\n\n"
            "© 2025 BPFAM Official — Serietà, rispetto e fiducia."
        ),

        "info_meetup": _normalize_env_text(os.environ.get("PAGE_INFO_MEETUP"),
            "🧾 *REGOLAMENTO MEET-UP — BPFAM OFFICIAL*\n\n"
            "📌 Professionalità, rispetto e organizzazione sono la base di ogni incontro.\n\n"
            "1️⃣ ✅ Verifica dell’identità obbligatoria prima di qualsiasi incontro, a meno che tu non sia già registrato nel sistema clienti BPFAM.\n\n"
            "2️⃣ 🤝 Massimo 2 persone per appuntamento. Chi accompagna dovrà essere segnalato in anticipo per la verifica di sicurezza.\n\n"
            "3️⃣ 🕒 Orari e luoghi fissati non possono essere modificati, salvo comunicazione con almeno 6 ore di preavviso e motivo valido.\n\n"
            "4️⃣ ❌ Chi non si presenta o annulla all’ultimo momento senza giustificazione potrà essere escluso da futuri servizi o punti BPFAM.\n\n"
            "5️⃣ ⚡ Ogni incontro è riservato e gestito esclusivamente dallo staff autorizzato BPFAM. Serietà, puntualità e rispetto sono fondamentali.\n\n"
            "© 2025 BPFAM Official — Serietà, rispetto e fiducia.\n\n"
            "🏆 *SERVIZI MEET-UP — BPFAM OFFICIAL*\n\n"
            "🤝 Il Meet-Up è un servizio esclusivo che ti permette di ritirare i tuoi ordini di persona in zone selezionate dal nostro team o dai nostri point ufficiali. "
            "⚡ Serietà e rispetto sono alla base di ogni incontro: organizziamo solo con chi mostra impegno e affidabilità.\n\n"
            "📅 Dopo la verifica dell’identità e la conferma dell’ordine, verrà fissato un appuntamento con data, orario e luogo precisi per il ritiro. "
            "❗ La puntualità è obbligatoria: eventuali ritardi o assenze non giustificate comporteranno l’esclusione dai nostri servizi.\n\n"
            "📜 Tutte le comunicazioni ufficiali e i dettagli dell’incontro vengono gestiti direttamente tramite il nostro staff BPFAM.\n\n"
            "© 2025 BPFAM Official — Serietà, rispetto e fiducia."
        ),

        "info_point": _normalize_env_text(os.environ.get("PAGE_INFO_POINT"),
            "🌐 *BPFAM OFFICIAL POINT* 🌐\n📍\n\n"
            "👁‍🗨 *ENTRA NEL MONDO BPFAM*\n"
            "Siamo alla ricerca di persone affidabili e motivate che vogliano rappresentare il nostro nome in nuove città e regioni 🏙\n\n"
            "🎯 Il nostro obiettivo è creare una rete solida, sicura e coordinata di referenti BPFAM, mantenendo sempre gli stessi standard di serietà, rispetto e professionalità.\n\n"
            "📋 *REQUISITI ESSENZIALI:*\n"
            "• Responsabilità e discrezione 🔒\n• Conoscenza base del settore 🌿\n• Capacità organizzativa e puntualità ⏱\n• Comunicazione chiara e rispetto delle regole 📑\n\n"
            "💰 È richiesto un capitale iniziale minimo (15.000 – 20.000 €), necessario per garantire serietà, autonomia e una gestione professionale del proprio Point 🔒\n\n"
            "🧭 Durante la selezione verranno valutati metodo, esperienza e attitudine al lavoro, fornendo supporto e linee guida per una collaborazione stabile e duratura ✅\n\n"
            "⸻\n\n"
            "🚩 *BPFAM POINT ITALIA* 🇮🇹\n📍\n\n"
            "✅ Supera la selezione e diventa un BPFAM POINT ufficiale. Entrerai a far parte di una rete esclusiva, con accesso a strumenti dedicati e vantaggi riservati ai nostri affiliati 🔥\n\n"
            "🤖💻 Ogni Point avrà un bot Telegram personalizzato, gestito dal nostro team tecnico e sincronizzato con il database centrale BPFAM, per offrire ai propri clienti un servizio moderno, rapido e sicuro.\n\n"
            "📦 *PRIORITÀ E VANTAGGI ESCLUSIVI:* I Point BPFAM beneficiano di sconti riservati sul materiale, condizioni privilegiate e fornitura garantita anche nei periodi di scarsità. Il magazzino centrale BPFAM assicura sempre continuità e stabilità costante 💎\n\n"
            "🔒 *VERIFICA, CREDIBILITÀ E PARTNERSHIP:* Tutti i nostri Point vengono riconosciuti e inseriti all’interno dei nostri sponsor e partner ufficiali BPFAM, con certificazione verificata e approvazione diretta. Ogni affiliato gode della copertura del marchio BPFAM, simbolo di serietà, sicurezza e affidabilità nel settore.\n\n"
            "🤝 *ASSISTENZA DIRETTA E CONTINUA:* Il nostro servizio di supporto è attivo 24 ore su 24, 7 giorni su 7, con personale qualificato sempre disponibile per assistenza tecnica o gestionale. Il contatto diretto con il team centrale BPFAM garantisce efficienza, supporto e trasparenza costante 💬\n\n"
            "🏆 *SELEZIONE E STANDARD DI QUALITÀ:* BPFAM seleziona esclusivamente profili che rispecchiano la propria filosofia e i propri standard elevati. Solo chi dimostra affidabilità, competenza e dedizione potrà rappresentare ufficialmente il marchio BPFAM.\n\n"
            "📩 Contattaci su Telegram per ricevere maggiori informazioni e scopri come entrare nella rete BPFAM POINT ITALIA 🚀\n\n"
            "⸻\n\n"
            "📍 *COSA SONO I BPFAM POINT?* 👤\n\n"
            "I BPFAM Point sono punti ufficiali autorizzati, presenti in varie città e regioni d’Italia 🇮🇹. Rappresentano il canale diretto per accedere ai servizi e prodotti BPFAM, con la garanzia di qualità, riservatezza e professionalità.\n\n"
            "Ogni Point opera in autonomia, ma seguendo gli standard e le linee guida ufficiali BPFAM, per assicurare un’esperienza coerente, sicura e affidabile 📋\n\n"
            "💰 I prezzi possono variare in base alla zona e alla gestione locale del Point. Si invita a rivolgersi solo ai canali ufficiali, evitando intermediari non verificati ✅\n\n"
            "📌 BPFAM supervisiona direttamente i Point principali, garantendo serietà, trasparenza e continuità del servizio.\n\n"
            "⸻\n\n"
            "© 2025 — Powered by BPFAM Official Network | Management Division 💎"
        ),
    }

PAGES = _load_pages_from_env()

# ===== CONTATTI (da ENV JSON oppure default) =====
def _load_contacts():
    raw = os.environ.get("CONTACT_LINKS_JSON", "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
                return data
        except Exception as e:
            logger.warning(f"CONTACT_LINKS_JSON invalido: {e}")
    # Default: i tuoi contatti
    return {
        "Instagram Principale 📲": "https://www.instagram.com/bpfamofficial?igsh=MXM4YmljZmE1b2Uweg==",
        "Instagram Backup 📲": "https://www.instagram.com/bpfamofficial420backup?igsh=YTQxdzVpdTE5MGd2",
        "Instagram Media 🎥": "https://www.instagram.com/bpfam_official420media?igsh=ZjgzcnJvazg1c2dq&utm_source=qr",
        "Contatto Telegram 💬": "https://t.me/contattobpfam",
        "Canale Telegram Ufficiale 📢": "https://t.me/+CIA2nWh5thE2ZWFk",
        "Bot Telegram Ufficiale 🤖": "https://t.me/Bpfarmbot",
        "Contatto Potato 🥔": "https://ptwdym158.org/joinchat/B2iAXRTlpC5_5Awy9UugrQ",
    }

CONTACT_LINKS = _load_contacts()

CONTACTS_TEXT = _normalize_env_text(os.environ.get("PAGE_CONTACTS_TEXT"), 
    "💎 *BPFAM CONTATTI UFFICIALI* 💎\n\n"
    "📍 Resta connesso solo attraverso i canali verificati BPFAM.\n"
    "Tutti i contatti elencati qui sotto sono ufficiali e riconosciuti dal network BPFAM.\n\n"
    "⸻\n\n"
    "🔴 *INSTAGRAM PRINCIPALE 📲*\n👉 @bpfamofficial\n\n"
    "🟠 *INSTAGRAM BACKUP 📲*\n👉 @bpfamofficial420backup\n\n"
    "🟣 *INSTAGRAM MEDIA 🎥*\n👉 @bpfam_official420media\n\n"
    "💬 *CONTATTO TELEGRAM 📲*\n👉 @contattobpfam\n\n"
    "📢 *CANALE TELEGRAM UFFICIALE 📲*\n👉 t.me/+CIA2nWh5thE2ZWFk\n\n"
    "👾 *BOT TELEGRAM UFFICIALE 🤖*\n👉 @Bpfarmbot\n\n"
    "🥔 *CONTATTO POTATO 📲*\n👉 Apri link\n\n"
    "⸻\n\n"
    "⚠️ Diffida da profili o canali non presenti in questo elenco.\n"
    "Solo i contatti elencati sono verificati e gestiti direttamente da BPFAM Official Network.\n\n"
    "⸻\n\n"
    "© 2025 — Powered by BPFAM Official Network | Management Division 💎"
)

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

def _kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="home")]])

def _kb_infocontatti_root() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📇 Contatti", callback_data="contacts:open"),
            InlineKeyboardButton("ℹ️ Info",     callback_data="info:root"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="home")],
    ])

def _kb_contacts() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, url=url)] for label, url in CONTACT_LINKS.items()]
    rows.append([InlineKeyboardButton("🔙 Indietro", callback_data="sec:infocontatti")])
    return InlineKeyboardMarkup(rows)

def _kb_info_root() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚚 Info Delivery", callback_data="info:delivery")],
        [InlineKeyboardButton("🤝 Info Meet-Up",  callback_data="info:meetup")],
        [InlineKeyboardButton("📍🇮🇹 Info Point", callback_data="info:point")],
        [InlineKeyboardButton("🔙 Indietro",      callback_data="sec:infocontatti")],
    ])

PANEL_KEY = "panel_msg_id"

async def _edit_panel(context, chat_id: int, msg_id: int, text: str, kb: InlineKeyboardMarkup):
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=msg_id,
        text=text or "\u2063",
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=kb,
    )

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
            pass

    sent = await context.bot.send_message(
        chat_id=chat_id, text=text, reply_markup=kb,
        parse_mode="Markdown", disable_web_page_preview=True
    )
    context.user_data[PANEL_KEY] = sent.message_id
    return chat_id, sent.message_id

# ===== HANDLERS UTENTE =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        add_user(user.id, user.username, user.first_name, user.last_name)
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
    context.user_data[PANEL_KEY] = panel_id

    data = q.data or ""
    if data == "home":
        await _edit_panel(context, chat_id, panel_id, PAGES["main"], _kb_home()); return

    if data.startswith("sec:"):
        key = data.split(":", 1)[1]
        if key == "infocontatti":
            # Invia l'immagine in stile Packz (foto sopra al pannello)
            try:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=INFO_CONTACTS_IMAGE_URL,
                    caption="*BPFAM OFFICIAL NETWORK*\n*INFO & CONTATTI*\n\nRimani connesso ai canali ufficiali BPFAM.",
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.warning(f"Errore invio immagine Info&Contatti: {e}")
            # Pannello con due cartelle
            text = PAGES.get("infocontatti", "📲 *Info & Contatti*\nScegli una sezione:")
            await _edit_panel(context, chat_id, panel_id, text, _kb_infocontatti_root()); return

        await _edit_panel(context, chat_id, panel_id, PAGES.get(key, "Pagina non trovata."), _kb_back()); return

    # Sotto-menù: Contatti
    if data == "contacts:open":
        await _edit_panel(context, chat_id, panel_id, CONTACTS_TEXT, _kb_contacts()); return

    # Sotto-menù: Info
    if data == "info:root":
        await _edit_panel(context, chat_id, panel_id, PAGES.get("info_overview"), _kb_info_root()); return
    if data == "info:delivery":
        await _edit_panel(context, chat_id, panel_id, PAGES.get("info_delivery"), _kb_info_root()); return
    if data == "info:meetup":
        await _edit_panel(context, chat_id, panel_id, PAGES.get("info_meetup"), _kb_info_root()); return
    if data == "info:point":
        await _edit_panel(context, chat_id, panel_id, PAGES.get("info_point"), _kb_info_root()); return

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong!")

# ===== COMANDI ADMIN (silenzio ai non-admin) =====
async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await _notify_admin_attempt(context, update.effective_user, "/utenti"); return
    await update.message.reply_text(f"👥 Utenti registrati: {count_users()}")

def _parse_backup_time(hhmm: str) -> dtime:
    try:
        h, m = map(int, hhmm.split(":")); return dtime(hour=h, minute=m)
    except:
        return dtime(hour=3, minute=0)

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

# ===== /help =====
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _is_admin(update.effective_user.id):
        txt = (
            "Comandi disponibili:\n"
            "/start – Benvenuto + menu\n"
            "/ping – Test rapido\n"
            "\n"
            "Solo Admin:\n"
            "/status, /utenti, /backup, /ultimo_backup, /test_backup, /list, /export, /broadcast"
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

    # Admin
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

    # Ignora comandi non gestiti per utenti normali
    app.add_handler(MessageHandler(filters.COMMAND, lambda u, c: None))

    # Job: webhook guard + backup giornaliero
    app.job_queue.run_repeating(webhook_guard, interval=600, first=60, name="webhook_guard")
    hhmm = _parse_backup_time(BACKUP_TIME)
    app.job_queue.run_daily(backup_job, time=hhmm, name="backup_daily")

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()