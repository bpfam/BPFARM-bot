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

if __name__ == "__main__":
    print("🤖 Bot in esecuzione...")
    bot.infinity_polling()
