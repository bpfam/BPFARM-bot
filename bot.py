# bot.py
# PyPI: python-telegram-bot>=20 (async)
from os import environ
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- CONFIGURAZIONE ---
# Metodo consigliato: impostare l'env var BOT_TOKEN su Render (Environment Variables)
TOKEN = environ.get("BOT_TOKEN") or "YOUR_TELEGRAM_BOT_TOKEN_HERE"
# Link esterni per i pulsanti
LINK_CONTATTI = "https://t.me/deseoriginal"
LINK_MENU = "https://t.me/roster879"
LINK_MINIAPP = "https://example.com/mini-app"  # sostituisci con il link della tua mini-app
# -----------------------

def build_main_keyboard():
    """Costruisce la tastiera principale con pulsanti che aprono link esterni."""
    keyboard = [
        [
            InlineKeyboardButton("📖 Menu", url=LINK_MENU),
            InlineKeyboardButton("📲 Contatti", url=LINK_CONTATTI)
        ],
        [
            InlineKeyboardButton("ℹ️ Info", callback_data="info_action"),
            InlineKeyboardButton("🌐 Mini-app", url=LINK_MINIAPP)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per /start: mostra il menu principale."""
    await update.message.reply_text(
        "👋 Ciao! Benvenuto. Usa il menu qui sotto per accedere alle sezioni.",
        reply_markup=build_main_keyboard()
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per /menu: mostra lo stesso menu (utile se vuoi comando separato)."""
    await update.message.reply_text(
        "📖 Menu principale:",
        reply_markup=build_main_keyboard()
    )

async def info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Se vuoi che il pulsante 'Info' risponda con testo (usando callback).
       Nota: i pulsanti con 'url' non inviano callback, ma qui gestiamo il comando /info
       e anche risposte se usi callback_data per altri pulsanti.
    """
    text = (
        "🔹 SHIPPING & PAYMENT INFO (esempio)\n\n"
        "SOCIALS:\n"
        "INSTAGRAM: @bpfamofficial\n\n"
        "CONTACT OPTIONS:\n"
        "Per contatti usa il pulsante Contatti oppure il link nella mini-app.\n\n"
        "— Questo è un testo di esempio, personalizzalo nelle righe del codice. —"
    )
    # se provieni da callback_query:
    if update.callback_query:
        await update.callback_query.answer()  # chiude il loading del pulsante
        await update.callback_query.edit_message_text(text)
    else:
        # messaggio diretto /info
        await update.message.reply_text(text)

def main():
    if not TOKEN or TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        raise RuntimeError("Token mancante. Imposta BOT_TOKEN come environment variable o sostituisci il token nel file.")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("info", info_handler))
    # se vuoi gestire callback (per pulsanti con callback_data), aggiungi CallbackQueryHandler

    print("✅ Bot avviato correttamente!")
    app.run_polling()

if __name__ == "__main__":
    main()