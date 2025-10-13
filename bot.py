# bot.py — BPFARM bot completo (python-telegram-bot v21+)
import os
import csv
import sqlite3
import logging
import shutil
from io import StringIO, BytesIO
from datetime import datetime, timezone
from pathlib import Path

from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ===== LOGGING =====
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("bpfarm-bot")

# ===== CONFIG (Render ENV) =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_FILE = os.environ.get("DB_FILE", "./data/users.db")
ADMIN_ID_ENV = os.environ.get("ADMIN_ID")
ADMIN_ID = int(ADMIN_ID_ENV) if ADMIN_ID_ENV and ADMIN_ID_ENV.isdigit() else None  # su Render: 8033084779

# Immagine e pulsanti — leggibili da ENV, con i tuoi default già impostati
WELCOME_PHOTO_URL = os.environ.get(
    "WELCOME_PHOTO_URL",
    "https://i.postimg.cc/0QSgSydz/5-F5-DFE41-C80-D-4-FC2-B4-F6-D1058440-B1.jpg",
)

BTN_MENU_LABEL        = os.environ.get("BTN_MENU_LABEL",        "📖 Menù")
BTN_SPAIN_LABEL       = os.environ.get("BTN_SPAIN_LABEL",       "🇪🇸 Shiip-Spagna")
BTN_REVIEWS_LABEL     = os.environ.get("BTN_REVIEWS_LABEL",     "🎇 Recensioni")
BTN_CONTACTS_LABEL    = os.environ.get("BTN_CONTACTS_LABEL",    "📲 Info-Contatti")

MENU_URL              = os.environ.get("MENU_URL",              "https://t.me/+w3_ePB2hmVwxNmNk")
SPAIN_URL             = os.environ.get("SPAIN_URL",             "https://t.me/+oNfKAtrBMYA1MmRk")
RECENSIONI_URL        = os.environ.get("RECENSIONI_URL",        "https://t.me/+fIQWowFYHWZjZWU0")
CONTATTI_URL          = os.environ.get("CONTATTI_URL",          "https://t.me/+dBuWJRY9sH0xMGE0")

# ===== DATABASE =====
def ensure_users_table():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            joined_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()

def add_user_if_needed(tg_user):
    ensure_users_table()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, joined_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            tg_user.id,
            tg_user.username,
            tg_user.first_name,
            tg_user.last_name,
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()
    conn.close()

def get_user_count():
    ensure_users_table()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    (count,) = cur.fetchone()
    conn.close()
    return count

def build_users_csv_bytes():
    ensure_users_table()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, username, first_name, last_name, joined_at FROM users ORDER BY joined_at ASC"
    )
    rows = cur.fetchall()
    conn.close()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["user_id", "username", "first_name", "last_name", "joined_at"])
    writer.writerows(rows)
    data = output.getvalue().encode("utf-8")
    bio = BytesIO(data)
    bio.name = f"users_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    bio.seek(0)
    return bio

# ===== UTILS =====
def is_admin(user_id: int) -> bool:
    return True if ADMIN_ID is None else (user_id == ADMIN_ID)

async def require_admin(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    if not is_admin(user.id):
        try:
            await update.effective_message.reply_text("❌ Solo l'admin può usare questo comando.")
        except Exception:
            pass
        logger.warning("Accesso negato a user_id=%s per comando admin.", user.id)
        return False
    return True

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

def validate_sqlite_db(db_path: Path) -> tuple[bool, str]:
    if not db_path.exists() or db_path.stat().st_size == 0:
        return False, "File assente o vuoto."
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        res = cur.fetchone()
        if not res or str(res[0]).lower() != "ok":
            conn.close()
            return False, "PRAGMA integrity_check non OK."
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
        has_users = cur.fetchone() is not None
        conn.close()
        if not has_users:
            return False, "Tabella 'users' non trovata nel DB."
        return True, "OK"
    except Exception as e:
        return False, f"Errore apertura/verifica SQLite: {e}"

# ===== UI / START =====
def menu_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(BTN_MENU_LABEL, url=MENU_URL), InlineKeyboardButton(BTN_REVIEWS_LABEL, url=RECENSIONI_URL)],
        [InlineKeyboardButton(BTN_CONTACTS_LABEL, url=CONTATTI_URL), InlineKeyboardButton(BTN_SPAIN_LABEL, url=SPAIN_URL)],
    ]
    return InlineKeyboardMarkup(rows)

WELCOME_TEXT = (
    "🏆 *Benvenuto nel bot ufficiale di BPFAM!*\n\n"
    "⚡ Serietà e rispetto sono la nostra identità.\n"
    "💪 Qui si cresce con impegno e determinazione."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        add_user_if_needed(update.effective_user)

    kb = menu_keyboard()
    try:
        if WELCOME_PHOTO_URL:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=WELCOME_PHOTO_URL,
                caption=WELCOME_TEXT,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        else:
            await update.effective_message.reply_text(
                WELCOME_TEXT, parse_mode="Markdown", reply_markup=kb
            )
    except Exception as e:
        logger.exception("Errore invio start: %s", e)
        await update.effective_message.reply_text(
            "👋 Benvenuto! (immagine non disponibile ora)\nUsa i pulsanti qui sotto.",
            reply_markup=kb,
        )

# ===== COMANDI BASE =====
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "ℹ️ Comandi:\n"
        "/start — benvenuto + menu\n"
        "/utenti — totale utenti\n"
        "/export_utenti — esporta CSV (admin)\n"
        "/backup_db — invia DB (admin)\n"
        "/restore_db — ripristino da file (admin)\n"
        "/annulla_restore — annulla ripristino\n"
        "/db_status — stato DB\n"
        "/whoami — il tuo user_id\n"
        "/ping — test"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("🏓 Pong!")

async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = get_user_count()
    await update.effective_message.reply_text(f"👥 Utenti salvati: {count}")

async def export_utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    csv_file = build_users_csv_bytes()
    await update.effective_message.reply_document(document=csv_file, caption="📄 CSV con tutti gli utenti.")

# ===== Diagnostica =====
async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await update.effective_message.reply_text(f"Il tuo user_id è: {u.id if u else 'sconosciuto'}")

async def db_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = Path(DB_FILE)
    if p.exists():
        try:
            size = p.stat().st_size
        except Exception:
            size = 0
        await update.effective_message.reply_text(f"DB trovato ✅\nPercorso: {p}\nDimensione: {size} B")
    else:
        await update.effective_message.reply_text(f"DB non trovato ❌\nPercorso atteso: {p}")

# ===== /backup_db =====
async def backup_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info("/backup_db richiesto da user_id=%s", user.id if user else None)

    if not await require_admin(update):
        return

    try:
        db_path = Path(DB_FILE)
        if not db_path.exists():
            await update.effective_message.reply_text(f"⚠️ Database non trovato: {db_path}")
            return

        await update.effective_message.reply_document(
            document=InputFile(str(db_path)),
            filename=db_path.name,
            caption="🗂️ Backup del database SQLite."
        )
        logger.info("DB inviato (%s)", db_path)
    except Exception as e:
        logger.exception("Errore /backup_db: %s", e)
        await update.effective_message.reply_text(f"❌ Errore durante l'invio del DB: {e}")

# ===== RESTORE DB =====
RESTORE_FLAG_KEY = "awaiting_restore"

def _incoming_dir() -> Path:
    p = Path(DB_FILE).parent / "incoming"
    p.mkdir(parents=True, exist_ok=True)
    return p

async def restore_db_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    context.user_data[RESTORE_FLAG_KEY] = True
    await update.effective_message.reply_text(
        "🛠️ Modalità ripristino attivata.\n"
        "➡️ Inviami ora come documento il file **users.db** oppure il CSV esportato.\n"
        "• Supporto: .db, .csv\n"
        "• Farò un backup automatico del DB attuale\n"
        "• Per annullare: /annulla_restore"
    )

async def restore_db_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    context.user_data[RESTORE_FLAG_KEY] = False
    await update.effective_message.reply_text("❎ Ripristino annullato.")

async def restore_db_receive_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if not context.user_data.get(RESTORE_FLAG_KEY):
        return

    message = update.effective_message
    doc = message.document
    if not doc:
        return

    filename = (doc.file_name or "").lower()
    is_db = filename.endswith(".db")
    is_csv = filename.endswith(".csv")

    incoming_path = _incoming_dir() / f"in_{_ts()}_{filename or 'file'}"
    try:
        tgfile = await doc.get_file()
        await tgfile.download_to_drive(custom_path=str(incoming_path))
    except Exception as e:
        await message.reply_text(f"❌ Errore nel download del file: {e}")
        return

    if is_db:
        ok, reason = validate_sqlite_db(incoming_path)
        if not ok:
            await message.reply_text(f"❌ File DB non valido: {reason}")
            return
        try:
            ensure_users_table()
            db_path = Path(DB_FILE)
            if db_path.exists():
                bak_path = db_path.with_name(f"{db_path.stem}.bak_{_ts()}{db_path.suffix}")
                shutil.copyfile(db_path, bak_path)
                logger.info("Creato backup DB: %s", bak_path)
        except Exception as e:
            await message.reply_text(f"❌ Impossibile creare backup del DB esistente: {e}")
            return
        try:
            shutil.copyfile(incoming_path, DB_FILE)
        except Exception as e:
            await message.reply_text(f"❌ Errore nella sostituzione del DB: {e}")
            return

        context.user_data[RESTORE_FLAG_KEY] = False
        await message.reply_text("✅ Ripristino completato dal file .db.\nRiavvia il bot se necessario.")
        return

    if is_csv:
        try:
            import csv as _csv
            rows = []
            with open(incoming_path, "r", encoding="utf-8") as f:
                reader = _csv.DictReader(f)
                for r in reader:
                    rows.append((
                        int(r.get("user_id", "0")) if r.get("user_id") else None,
                        r.get("username"),
                        r.get("first_name"),
                        r.get("last_name"),
                        r.get("joined_at"),
                    ))

            ensure_users_table()
            db_path = Path(DB_FILE)
            if db_path.exists():
                bak_path = db_path.with_name(f"{db_path.stem}.bak_{_ts()}{db_path.suffix}")
                shutil.copyfile(db_path, bak_path)
                logger.info("Creato backup DB: %s", bak_path)

            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute("DROP TABLE IF EXISTS users;")
            cur.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    joined_at TEXT
                )
                """
            )
            cur.executemany(
                """
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, joined_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.commit()
            conn.close()

            context.user_data[RESTORE_FLAG_KEY] = False
            await message.reply_text("✅ Import da CSV completato. Tabella 'users' ricreata.")
            return

        except Exception as e:
            await message.reply_text(f"❌ Errore durante l'import CSV: {e}")
            return

    await message.reply_text("⚠️ Formato non supportato. Invia un file .db (SQLite) oppure .csv esportato dal bot.")

# ===== MAIN =====
def main():
    if not BOT_TOKEN:
        raise SystemExit("❌ Imposta BOT_TOKEN nelle variabili d'ambiente.")

    ensure_users_table()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Anti-conflitto: rimuove webhook e scarta update pendenti
    import asyncio
    asyncio.get_event_loop().run_until_complete(
        app.bot.delete_webhook(drop_pending_updates=True)
    )

    # Comandi
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("utenti", utenti))

    # Diagnostica
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(CommandHandler("db_status", db_status))

    # Admin
    app.add_handler(CommandHandler("export_utenti", export_utenti))
    app.add_handler(CommandHandler("backup_db", backup_db))
    app.add_handler(CommandHandler("restore_db", restore_db_start))
    app.add_handler(CommandHandler("annulla_restore", restore_db_cancel))

    # Ricezione file per /restore_db
    file_filter = (
        filters.Document.MimeType("application/octet-stream")
        | filters.Document.MimeType("application/x-sqlite3")
        | filters.Document.FileExtension("db")
        | filters.Document.FileExtension("csv")
        | filters.Document.ALL
    )
    app.add_handler(MessageHandler(file_filter, restore_db_receive_document))

    logger.info("🚀 Bot in esecuzione…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()