import telebot
from telebot import types
import os

# Prende il token dalle variabili d'ambiente
TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "👋 Ciao! Il bot è attivo e funzionante.\nUsa /menu per vedere le opzioni.")

@bot.message_handler(commands=['menu'])
def send_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("🧾 Prodotti")
    btn2 = types.KeyboardButton("📦 Ordini")
    btn3 = types.KeyboardButton("ℹ️ Info")
    btn4 = types.KeyboardButton("💬 Contatti")
    markup.add(btn1, btn2, btn3, btn4)
    bot.send_message(message.chat.id, "📋 Scegli una sezione:", reply_markup=markup)

# Risposte ai pulsanti
@bot.message_handler(func=lambda message: message.text == "🧾 Prodotti")
def prodotti(message):
    bot.reply_to(message, "Ecco la lista dei prodotti disponibili:")

@bot.message_handler(func=lambda message: message.text == "📦 Ordini")
def ordini(message):
    bot.reply_to(message, "Qui puoi gestire i tuoi ordini.")

@bot.message_handler(func=lambda message: message.text == "ℹ️ Info")
def info(message):
    bot.reply_to(message, "Questo bot è un esempio creato da BPfarmBot!")

@bot.message_handler(func=lambda message: message.text == "💬 Contatti")
def contatti(message):
    bot.reply_to(message, "Per contattarci scrivi a: support@bpfarm.it")

if __name__ == "__main__":
    print("🤖 Bot in esecuzione...")
    bot.infinity_polling()
