# bot.py
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = BOT_TOKEN = "8425042215:AAHW6HTThpsc4M65sixfCsr1t3TwYcHH7ws..."

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

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

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()

if __name__ == "__main__":
    main()