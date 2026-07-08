"""
Operazioni CRUD per la gestione delle Card nel database.
"""

import uuid
import logging
from typing import List, Optional
from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.models import Card

logger = logging.getLogger(__name__)


def create_card(session: Session, merchant_id: int) -> Card:
    """Crea una nuova Card per il merchant indicato."""
    new_card = Card(merchant_id=merchant_id)
    session.add(new_card)
    session.commit()
    session.refresh(new_card)
    logger.info("Nuova Card creata: %s (merchant=%s)", new_card.id, merchant_id)
    return new_card


def get_card_by_id(session: Session, card_id: uuid.UUID) -> Optional[Card]:
    """Recupera una carta per ID."""
    return session.get(Card, card_id)


def get_all_cards(session: Session, skip: int = 0, limit: int = 100) -> List[Card]:
    """Restituisce la lista di tutte le Card."""
    statement = select(Card).offset(skip).limit(limit)
    return session.exec(statement).all()


def delete_card(session: Session, card_id: uuid.UUID):
    """Elimina una carta."""
    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card non trovata")
    session.delete(card)
    session.commit()
