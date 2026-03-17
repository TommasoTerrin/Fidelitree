import urllib.parse
import logging

logger = logging.getLogger(__name__)


def create_whatsapp_link(chat_phone_number: str, message: str) -> str:
    """
    Crea un link WhatsApp per inviare un messaggio pre-compilato.

    Args:
        chat_phone_number (str): Il numero di telefono (es. +393400000000)
        message (str): Il messaggio da inviare

    Returns:
        str: URL wa.me che apre WhatsApp con il messaggio pronto per l'invio.
    """
    # Pulizia del numero di telefono: tiene solo le cifre
    clean_number = "".join(filter(str.isdigit, chat_phone_number))

    # URL encoding del messaggio
    encoded_message = urllib.parse.quote(message)

    # Costruzione del link base
    whatsapp_url = f"https://wa.me/{clean_number}?text={encoded_message}"

    # Controllo lunghezza massima (limite indicativo URL safe di ~2000 caratteri)
    MAX_URL_LENGTH = 2000

    if len(whatsapp_url) > MAX_URL_LENGTH:
        logger.warning("Messaggio troppo lungo per link WhatsApp, verrà troncato.")
        while len(f"https://wa.me/{clean_number}?text={urllib.parse.quote(message)}") > MAX_URL_LENGTH:
            message = message[:-10]

        encoded_message = urllib.parse.quote(message)
        whatsapp_url = f"https://wa.me/{clean_number}?text={encoded_message}"

    return whatsapp_url
