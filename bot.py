from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Menu principale
def menu_principale():
    keyboard = [
        [InlineKeyboardButton("🌿 Weed", callback_data="weed")],
        [InlineKeyboardButton("💨 Hash", callback_data="hash")],
        [InlineKeyboardButton("💬 Contatti", callback_data="contatti")],
        [InlineKeyboardButton("ℹ️ Info", callback_data="info")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Inserisci qui il tuo token del bot
TOKEN = "8425042215:AAE3l_ssv9xsPikYralbR1CdfK7MtUuEAT0"

# Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Ciao! Il bot è attivo e funzionante!")

# Comando /menu
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Scegli una sezione:",
        reply_markup=menu_principale()
    )

# Avvio del bot
if __name__ == "__main__":
    print("✅ Bot avviato correttamente!")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.run_polling()