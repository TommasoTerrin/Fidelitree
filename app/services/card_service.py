"""
Servizi per la logica di business relativa alle Card (carte fedeltà).
"""

import uuid
import logging
from fastapi import HTTPException
from sqlmodel import Session

from app.models.models import Merchant, Card
from app.services.db_crud import card_crud, merchant_crud

logger = logging.getLogger(__name__)


def update_cashback(
    session: Session,
    merchant: Merchant,
    card_id: uuid.UUID,
    cb_points: float
) -> Card:
    """
    Aggiunge (o rimuove, se negativo) credito cashback a una carta.
    La carta deve appartenere al merchant autenticato e il saldo
    non può mai scendere sotto zero.
    """
    card = card_crud.get_card_by_id(session, card_id)
    if not card or card.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Card non valida per questo merchant")

    if card.cashback_point + cb_points < -0.001:  # tolleranza per i float
        raise HTTPException(status_code=400, detail="Impossibile portare il cashback sotto 0")

    card.cashback_point += cb_points
    session.add(card)
    session.commit()
    session.refresh(card)
    logger.info("Cashback aggiornato per card %s: %+.2f", card.id, cb_points)
    return card


def create_card(session: Session, merchant_id: int) -> Card:
    """Crea una carta dopo aver verificato che il merchant esista."""
    merchant = merchant_crud.get_merchant_by_id(session, merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant non trovato")

    return card_crud.create_card(session, merchant_id)
