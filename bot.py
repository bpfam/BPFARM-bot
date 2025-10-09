from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes

# 🔑 Inserisci qui il tuo token
BOT_TOKEN = "INSERISCI_IL_TUO_TOKEN_QUI"


# 🔹 Funzione di avvio del bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Messaggio di benvenuto
    message_text = (
        "💨 Yo! Benvenuto nel bot ufficiale **BPFam 🔥**\n"
        "📖 Menu, info e contatti qui sotto 👇\n"
        "💬 Scrivici su Telegram se hai bisogno!"
    )

    # Pulsanti con i link
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

    # Invia il messaggio con la foto e i pulsanti
    await context.bot.send_photo(
        chat_id=chat_id,
        photo="https://i.postimg.cc/LJNHDQXY/5-F5-DFE41-C80-D-4-FC2-B4-F6-D105844664-B3.jpg",
        caption=message_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


# 🔹 Funzione principale per avviare il bot
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Imposta solo il comando /start
    app.bot.set_my_commands([
        ("start", "Avvia il bot e mostra il menu principale")
    ])

    # Aggiungi il comando /start
    app.add_handler(CommandHandler("start", start))

    print("🤖 Bot avviato! In attesa di messaggi...")
    app.run_polling()


if __name__ == "__main__":
    main()