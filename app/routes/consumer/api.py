"""
Endpoint API per i consumatori.
Gestisce la creazione di nuove carte fedeltà e la loro consultazione.
"""

import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.core.dependencies import get_session
from app.core.utils.whatsapp_utils import create_whatsapp_link
from app.services import card_service
from app.services.db_crud import card_crud, merchant_crud
from app.schemas.card import CardResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Consumer API"])


class GetCardRequest(BaseModel):
    """Dati per creare una nuova Card."""
    merchant_id: int = 1  # default al merchant di test


@router.post("/get-card")
async def create_new_card(
    body: GetCardRequest,
    session: Session = Depends(get_session),
):
    """Crea una nuova Card e restituisce il link WhatsApp per salvarla."""
    new_card = card_service.create_card(session, body.merchant_id)

    # Recupera il merchant per costruire il link WhatsApp
    merchant = merchant_crud.get_merchant_by_id(session, body.merchant_id)

    card_path = f"/card/{new_card.id}"
    message = (
        "Ciao! La creazione della mia carta fedeltà è andata a buon fine.\n\n"
        "Premi invio per salvarla nella chat, "
        "la troverai al seguente link:\n"
        "{card_url}"
    )

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


@router.get("/card/{card_id}", response_model=CardResponse)
async def get_card(
    card_id: uuid.UUID,
    session: Session = Depends(get_session)
):
    """Restituisce una card specifica (l'UUID della carta funge da capability URL)."""
    card = card_crud.get_card_by_id(session, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card non trovata")
    return card
