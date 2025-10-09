from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes
# se usi ApplicationBuilder: from telegram.ext import ApplicationBuilder

BOT_TOKEN = "INSERISCI_IL_TUO_TOKEN_QUI"

# --- funzione /start (lascia come la hai) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    message_text = (
        "💨 Yo! Benvenuto nel bot ufficiale **BPFam 🔥**\n"
        "📖 Menu, info e contatti qui sotto 👇\n"
        "💬 Scrivici su Telegram se hai bisogno!"
    )
    keyboard = [
        [
            InlineKeyboardButton("📖 Menù", url="https://t.me/+w3_ePB2hmVwxNmNk"),
            InlineKeyboardButton("🎇 BPFAM.RECENSIONI", url="https://t.me/+fIQWowFYHWZjZWU0")
        ],
        [
            InlineKeyboardButton("📲 Info-Contatti", url="https://t.me/+deEirerZvwRjNjA0"),
            InlineKeyboardButton("🇪🇸 Menù-shiip Spagna", url="https://t.me/+oNfKAtrBMYA1MmRk")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_photo(
        chat_id=chat_id,
        photo="https://i.postimg.cc/LJNHDQXY/5-F5-DFE41-C80-D-4-FC2-B4-F6-D105844664-B3.jpg",
        caption=message_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# --- funzione che pulisce i comandi all'avvio ---
async def clear_commands_on_startup(app):
    # cancella i comandi "globali" (di default)
    await app.bot.set_my_commands([])

    # se vuoi vedere cosa c'era prima, puoi usare get_my_commands:
    current = await app.bot.get_my_commands()
    print("Comandi impostati (dopo clear):", current)

# --- main ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # registra handler
    app.add_handler(CommandHandler("start", start))

    # avvia con post_init: chiama clear_commands_on_startup(app) subito dopo init
    print("Avvio bot e pulizia comandi...")
    app.run_polling(post_init=clear_commands_on_startup)

if __name__ == "__main__":
    main()