from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def menu_principale():
    keyboard = [
        [InlineKeyboardButton("🌿 Weed", callback_data='weed')],
        [InlineKeyboardButton("💨 Hash", callback_data='hash')],
        [InlineKeyboardButton("💬 Contatti", callback_data='contatti')],
        [InlineKeyboardButton("ℹ️ Info", callback_data='info')]
    ]
    return InlineKeyboardMarkup(keyboard)
    from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Inserisci qui il tuo token del bot
TOKEN = 8425042215:AAGxVzPfD7Z3RUVvqSJi8BK4iHX2TCf0I3E

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Ciao! Il bot è attivo e funzionante.\nUsa /menu per vedere le opzioni."
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Scegli una sezione:",
        reply_markup=menu_principale()
    )

if __name__ == "__main__":
    print("✅ Bot avviato correttamente!")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.run_polling()