# bot.py
# PyPI: python-telegram-bot>=20 (async)
from os import environ
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

# --- CONFIGURAZIONE ---
TOKEN = "8425042215:AAHsGkzeKgc6IbxY30zRKYgUUWiOKBnR_k0"
LINK_CONTATTI = "https://t.me/deseoriginal"
LINK_MENU = "https://t.me/roster879"
LINK_MINIAPP = "https://example.com/mini-app"  # sostituisci se hai il link vero
IMMAGINE_BENVENUTO = "https://i.postimg.cc/LJNHDQXY/5-F5-DFE41-C80-D-4-FC2-B4-F6-D105844664-B3.jpg"
# -----------------------

def build_main_keyboard():
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
    """Messaggio di benvenuto con immagine e pulsanti"""
    caption = (
        "💨 Yo! Benvenuto nel bot ufficiale **BPFam 🔥**\n"
        "📖 Menu, info e contatti qui sotto 👇\n"
        "💬 Scrivici su Telegram se hai bisogno!"
    )
    await update.message.reply_photo(
        photo=IMMAGINE_BENVENUTO,
        caption=caption,
        reply_markup=build_main_keyboard()
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Menu principale:",
        reply_markup=build_main_keyboard()
    )

async def info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Testo Info"""
    text = (
        "🚢 SHIPPING & PAYMENT INFO 💶\n\n"
        "SOCIALS:\n"
        "INSTAGRAM: @bpfamofficial / @bpfamofficial420backup\n"
        "⚠️ Tutti gli altri account sono falsi — nessuno Snapchat!\n\n"
        "📲 CONTATTI:\nhttps://t.me/+88807134596\n\n"
        "💸 PAGAMENTI:\nCrypto / Western Union / MoneyGram / Cash a Barcellona / Bonifico (clienti verificati)\n\n"
        "📦 SPEDIZIONI:\nWorldwide 🌍 con 95%+ landing rate ✅\n"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text)
    else:
        await update.message.reply_text(text)

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("info", info_handler))
    app.add_handler(CallbackQueryHandler(info_handler, pattern="^info_action$"))

    print("✅ Bot avviato correttamente!")
    app.run_polling()

if __name__ == "__main__":
    main()