"""
Modulo per la gestione del bot Telegram di Fidelitree.
Gestisce l'interazione con gli esercenti, l'associazione dell'account e lo scanner.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from sqlmodel import Session, select

from app.core.config import settings
from app.core.dependencies import get_session
from app.models.models import Merchant
from app.core.security import decrypt_key, generate_telegram_hash

# Configurazione logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /start: associazione o accesso allo scanner."""
    user = update.effective_user
    telegram_id = str(user.id)
    
    # Cerchiamo se l'utente è già associato ad un merchant
    with next(get_session()) as session:
        statement = select(Merchant).where(Merchant.id_telegram == telegram_id)
        merchant = session.exec(statement).first()
    
    if merchant:
        # UTENTE ASSOCIATO -> Pulsante per lo scanner con auto-login
        hash_val = generate_telegram_hash(telegram_id)
        auto_login_url = f"{settings.BASE_URL}/merchant/telegram/auto-login?tid={telegram_id}&h={hash_val}"
        
        text = (
            f"🌲 *Bentornato, {merchant.business_name}!*\n\n"
            "Puoi iniziare subito a scannerizzare le card dei clienti."
        )
        keyboard = [
            [InlineKeyboardButton("📷 Nuova Scansione", url=auto_login_url)]
        ]
    else:
        # UTENTE NON ASSOCIATO -> Pulsante per il login/associazione
        login_url = f"{settings.BASE_URL}/merchant/login?telegram_id={telegram_id}"
        
        text = (
            "🌲 *Benvenuto su Fidelitree Bot!*\n\n"
            "Per iniziare, associa al tuo profilo fidelitree questo bot telegram dal seguente link.\n\n"
            "Se non hai già un profilo contatta Tommaso Terrin."
        )
        keyboard = [
            [InlineKeyboardButton("🔗 Collega Account", url=login_url)]
        ]
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

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
    try:
        logger.info("Tentativo di avvio Telegram Bot...")
        
        # Inizializza l'applicazione
        await bot_app.initialize()
        
        # IMPORTANTE: Rimuove eventuali webhook residui per permettere il polling
        logger.info("Rimozione webhook esistenti...")
        await bot_app.bot.delete_webhook(drop_pending_updates=True)
        
        # Avvia l'applicazione e il polling
        await bot_app.start()
        await bot_app.updater.start_polling()
        
        logger.info("✅ Telegram Bot in esecuzione (Polling attivo).")
    except Exception as e:
        logger.error(f"❌ Errore critico durante l'avvio del bot: {e}", exc_info=True)
