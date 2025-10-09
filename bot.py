import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# 🔹 Attiva i log per debug
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# 🔹 Leggi il token dalle variabili d’ambiente
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("❌ Errore: Variabile BOT_TOKEN non trovata! Aggiungila su Render → Environment → BOT_TOKEN")

# 🔹 Comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Ciao 👋! Il bot è attivo e funzionante ✅")

# 🔹 Risposta ai messaggi normali
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    await update.message.reply_text(f"Hai scritto: {text}")

# 🔹 Crea l’applicazione del bot
app = ApplicationBuilder().token(TOKEN).build()

# 🔹 Aggiungi i comandi e i gestori
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# 🔹 Avvia il bot
if __name__ == "__main__":
    logging.info("🤖 Il bot è in esecuzione...")
    app.run_polling()