"""
Endpoint API per i clienti.
Gestisce l'iscrizione a un negozio, il wallet e la consultazione delle proprie carte.
Tutti gli endpoint richiedono la sessione del cliente (cookie `access_token` o Bearer).
"""

import logging
import uuid
from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.dependencies import get_current_customer, get_session
from app.models.models import Customer
from app.schemas.card import CardResponse, JoinResponse, WalletEntryResponse
from app.services import customer_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Consumer API"])


@router.post("/customer/join/{merchant_id}", response_model=JoinResponse)
async def join_merchant(
    merchant_id: int,
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    """
    Iscrive il cliente al negozio: crea la carta o riapre quella esistente (`created=False`).
    Errori: 401 non autenticato, 404 negozio inesistente.
    """
    card, created = customer_service.join_merchant(session, customer, merchant_id)
    return JoinResponse(card_id=card.id, created=created)


@router.get("/customer/wallet", response_model=list[WalletEntryResponse])
async def get_wallet(
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    """Le carte del cliente, ordinate per negozio, con il livello del pool del mese di ciascuno."""
    return customer_service.list_wallet(session, customer)


@router.get("/card/{card_id}", response_model=CardResponse)
async def get_card(
    card_id: uuid.UUID,
    customer: Customer = Depends(get_current_customer),
    session: Session = Depends(get_session),
):
    """
    Restituisce una carta solo al suo proprietario. Errori: 401 non autenticato,
    404 se la carta non esiste o è di un altro cliente (stesso messaggio).
    """
    return customer_service.get_owned_card(session, customer, card_id)
