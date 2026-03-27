# app/routes/consumer/api.py
# CONSUMER BUSINESS CALLS — Restituisce JSON

import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.core.dependencies import get_session
from app.models.models import Merchant
from app.core.utils.whatsapp_utils import create_whatsapp_link
from app.services import card_service
from app.services.db_crud import card_crud, merchant_crud
from app.schemas.card import CardResponse, CardUpdateRequest

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
    """Crea una nuova TreeCard tramite Business Service."""
    new_card = card_service.create_card(session, body.merchant_id)
    
    # Recupera il merchant tramite CRUD per il link WhatsApp
    merchant = merchant_crud.get_merchant_by_id(session, body.merchant_id)

    card_path = f"/card/{new_card.id}"
    message = (
        "Ciao! 🌳 La creazione della mia Treecard è andata a buon fine.\n\n"
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

# ---------------------------------------------------------------------------
# 2. CRUD Operazioni per TreeCard
# ---------------------------------------------------------------------------

@router.get("/cards", response_model=list[CardResponse])
async def get_all_cards(
    skip: int = 0,
    limit: int = 100,
    session: Session = Depends(get_session)
):
    """Restituisce tutte le card tramite CRUD service."""
    return card_crud.get_all_cards(session, skip, limit)


@router.get("/card/{card_id}", response_model=CardResponse)
async def get_card(
    card_id: uuid.UUID,
    session: Session = Depends(get_session)
):
    """Restituisce una card specifica tramite CRUD service."""
    card = card_crud.get_card_by_id(session, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="TreeCard non trovata")
    return card


@router.put("/card/{card_id}", response_model=CardResponse)
async def update_card(
    card_id: uuid.UUID,
    card_in: CardUpdateRequest,
    session: Session = Depends(get_session)
):
    """Aggiorna i dati di una TreeCard (solo campi modificabili)."""
    card = card_crud.get_card_by_id(session, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="TreeCard non trovata")

    update_data = card_in.model_dump(exclude_unset=True)
    try:
        for key, value in update_data.items():
            setattr(card, key, value)
        
        session.add(card)
        session.commit()
        session.refresh(card)
        return card
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Errore aggiornamento card {card_id}: {e}")
        raise HTTPException(status_code=500, detail="Errore interno durante l'aggiornamento della carta")


@router.delete("/card/{card_id}")
async def delete_card(
    card_id: uuid.UUID,
    session: Session = Depends(get_session)
):
    """Elimina una TreeCard tramite CRUD service."""
    card_crud.delete_card(session, card_id)
    return {"status": "success", "message": f"TreeCard {card_id} eliminata con successo"}
