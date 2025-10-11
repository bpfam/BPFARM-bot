# bot.py – compatibile python-telegram-bot v20+
import os, sqlite3, logging
from datetime import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import ApplicationBuilder, Application, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("bot")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
DB_FILE = os.environ.get("DB_FILE") or str(Path(__file__).with_name("users.db"))

def init_db():
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            created_at TEXT
        );
    """)
    conn.commit(); conn.close()

def add_user(user):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO users (id, username, first_name, created_at)
        VALUES (?, ?, ?, ?)
    """, (user.id, user.username, user.first_name, datetime.utcnow().isoformat(timespec="seconds")))
    conn.commit(); conn.close()

def count_users():
    conn = sqlite3.connect(DB_FILE); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users"); (n,) = cur.fetchone()
    conn.close(); return int(n or 0)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_user(update.effective_user)
    kb = [
        [InlineKeyboardButton("📖 Menu", url="https://example.com/menu"),
         InlineKeyboardButton("💥 Recensioni", url="https://example.com/reviews")],
        [InlineKeyboardButton("📱 Info-bot", url="https://t.me/tuo_canale"),
         InlineKeyboardButton("🚢 Ship", url="https://example.com/ship")],
    ]
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo="https://picsum.photos/800/400",
        caption=("💨 Yo! Benvenuto nel bot ufficiale!\n"
                 "📖 *Menu, info e contatti* qui sotto.\n"
                 "💬 Scrivici se hai domande."),
        parse_mode=constants.ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(kb),
    )

async def utenti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"👥 Utenti registrati: *{count_users()}*",
                                    parse_mode=constants.ParseMode.MARKDOWN)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/start – Benvenuto\n/utenti – Numero utenti\n/help – Aiuto\n/ping – Pong")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong 🏓")

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Errore non gestito: %s", context.error)

def main():
    if not BOT_TOKEN:
        log.error("❌ BOT_TOKEN mancante."); return
    init_db()
    app: Application = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ping", ping))
    app.add_error_handler(on_error)
    log.info("✅ Bot avviato con successo! In ascolto (polling)...")
    app.run_polling(drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    main()