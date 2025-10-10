import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import json
import os

USERS_FILE = "users.json"

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return []

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)

# Prende il token in modo sicuro dalla variabile d’ambiente su Render
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Funzione /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    # 🔹 Salva automaticamente l’utente
    users = load_users()
    if user.id not in [u["id"] for u in users]:
        users.append({
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name
        })
        save_users(users)
        print(f"✅ Nuovo utente salvato: {user.first_name} (@{user.username})")

    # Messaggio di benvenuto
    message_text = (
        "💨 Yo! Benvenuto nel bot ufficiale **BPFam 🔥**\n"
        "📖 Menu, info e contatti qui sotto 👇\n"
        "💬 Scrivici su Telegram se hai bisogno!"
    )

    # Pulsanti con link
    keyboard = [
        [
            InlineKeyboardButton("📖 Menù", url="https://t.me/+w3_ePB2hmVwxNmNk"),
            InlineKeyboardButton("🎇RECENSIONI", url="https://t.me/+fIQWowFYHWZjZWU0")
        ],
        [
            InlineKeyboardButton("📲Info-Contatti", url="https://t.me/+deEirerZvwRjNjA0"),
            InlineKeyboardButton("🇪🇸SHIIP-SPAGNA-menu", url="https://t.me/+oNfKAtrBMYA1MmRk")
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Invia il messaggio con i pulsanti
    await context.bot.send_photo(
        chat_id=chat_id,
        photo="https://i.postimg.cc/LJNHDQXY/5-F5-DFE41-C80-D-4-FC2-B4-F6-D105844664-B3.jpg",
        caption=message_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# Avvio del bot
def main():
    if not BOT_TOKEN:
        print("❌ ERRORE: Nessun token trovato. Aggiungi BOT_TOKEN come variabile d’ambiente su Render.")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    print("✅ Bot avviato con successo! In attesa di messaggi...")
    app.run_polling()

if __name__ == "__main__":
    main()