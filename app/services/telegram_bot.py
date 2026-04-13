import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from sqlmodel import Session, select

from app.core.config import settings
from app.core.dependencies import get_session
from app.models.models import Merchant
from app.core.security import decrypt_key

# Configurazione logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia un messaggio con il pulsante per aprire la Mini App dello scanner."""
    webapp_url = f"{settings.BASE_URL}/merchant/telegram/scanner"
    
    welcome_text = (
        "🌲 *Benvenuto su Fidelitree Bot!*\n\n"
        "Per iniziare a usare lo scanner, clicca sul pulsante qui sotto.\n"
        "Se è la prima volta, ti verrà chiesto di effettuare il login per collegare il tuo account."
    )
    
    keyboard = [
        [
            InlineKeyboardButton(
                "📷 Apri Scanner", 
                web_app=WebAppInfo(url=webapp_url)
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invita l'utente a usare il pulsante Mini App."""
    await update.message.reply_text("Usa il comando /start per aprire lo scanner.")

# Inizializzazione applicazione bot
bot_app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).build()

# Aggiunta handler
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

async def run_bot():
    """Funzione per avviare il bot in background."""
    logger.info("Avvio Telegram Bot...")
    # Inizializza e avvia il polling
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()
    logger.info("Telegram Bot in esecuzione.")
