# app/routes/consumer/api.py
# CONSUMER BUSINESS CALLS — Restituisce JSON

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.core.dependencies import get_session
from app.models.models import TreeCard, Merchant
from app.services.whatsapp_service import create_whatsapp_link

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Consumer API"])


# ---------------------------------------------------------------------------
# Schema di richiesta
# ---------------------------------------------------------------------------

class GetCardRequest(BaseModel):
    """Dati per creare una nuova TreeCard."""
    merchant_id: int = 1  # default al merchant di test


# ---------------------------------------------------------------------------
# 1. CREAZIONE DI UNA NUOVA TREECARD
# ---------------------------------------------------------------------------

@router.post("/get-card")
async def create_new_card(
    body: GetCardRequest,
    session: Session = Depends(get_session),
):
    """Crea una nuova TreeCard e restituisce un link WhatsApp per inviarla al merchant.

    Flusso:
    1. Crea la card nel DB.
    2. Recupera il numero di telefono del merchant.
    3. Genera un link wa.me con il numero del merchant + messaggio pre-compilato col link della carta.
    4. Il consumer apre WhatsApp col merchant già in chat e preme invio.
    """
    # Verifica che il merchant esista
    merchant = session.get(Merchant, body.merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant non trovato")

    # Crea la card
    new_card = TreeCard(merchant_id=body.merchant_id)
    session.add(new_card)
    session.commit()
    session.refresh(new_card)

    logger.info("Nuova TreeCard creata: %s (merchant=%s)", new_card.id, body.merchant_id)

    # Costruisci l'URL della card — il placeholder verrà risolto dal frontend
    # perché il backend non conosce l'host reale (potrebbe stare dietro proxy/HTTPS)
    card_path = f"/card/{new_card.id}"

    # Messaggio pre-compilato: il consumer lo invierà AL merchant su WhatsApp
    message = (
        "Ciao! 🌳 La creazione della mia Treecard è andata a buon fine.\n\n"
        "Premi invio per salvarla nella chat, "
        "la troverai al seguente link:\n"
        "{card_url}"   # placeholder risolto lato frontend
    )

    # Link WhatsApp con NUMERO DEL MERCHANT come destinatario
    whatsapp_link = create_whatsapp_link(
        chat_phone_number=merchant.phone_number,
        message=message,
    )

    return {
        "status": "success",
        "card_id": str(new_card.id),
        "card_path": card_path,
        "whatsapp_link_template": whatsapp_link,
    }
