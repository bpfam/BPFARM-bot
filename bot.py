import telebot
import os

# Legge il token del bot dalle variabili di ambiente
TOKEN = os.environ.get("BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Ciao 👋! Il bot è attivo e funzionante ✅")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, message.text)
@bot.message_handler(commands=['info'])
def send_info(message):
    bot.reply_to(message, "ℹ️ Questo è un bot di test creato per BP Farm!")

@bot.message_handler(commands=['help'])
def send_help(message):
    bot.reply_to(message, "💡 Comandi disponibili:\n/start - avvia il bot\n/info - informazioni\n/menu - mostra il menu")

@bot.message_handler(commands=['menu'])
def send_menu(message):
    bot.reply_to(message, "📋 Menu:\n1️⃣ Info\n2️⃣ Aiuto\n3️⃣ Altro in arrivo!")
if __name__ == "__main__":
    print("🤖 Bot in esecuzione...")
    bot.infinity_polling()
