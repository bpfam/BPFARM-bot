from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def menu_principale():
    keyboard = [
        [InlineKeyboardButton("🌿 Weed", callback_data='weed')],
        [InlineKeyboardButton("💨 Hash", callback_data='hash')],
        [InlineKeyboardButton("💬 Contatti", callback_data='contatti')],
        [InlineKeyboardButton("ℹ️ Info", callback_data='info')]
    ]
    return InlineKeyboardMarkup(keyboard)