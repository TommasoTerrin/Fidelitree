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


def create_card(session: Session, merchant_id: int, customer_id: int) -> Card:
    """Crea una nuova Card per la coppia merchant/cliente."""
    new_card = Card(merchant_id=merchant_id, customer_id=customer_id)
    session.add(new_card)
    session.commit()
    session.refresh(new_card)
    logger.info("Nuova Card creata: %s (merchant=%s)", new_card.id, merchant_id)
    return new_card


def get_card_by_id(session: Session, card_id: uuid.UUID) -> Optional[Card]:
    """Recupera una carta per ID."""
    return session.get(Card, card_id)


def get_card_by_merchant_and_customer(
    session: Session, merchant_id: int, customer_id: int
) -> Optional[Card]:
    """Recupera la carta di un cliente presso un negozio (ne esiste una sola per coppia)."""
    statement = select(Card).where(Card.merchant_id == merchant_id, Card.customer_id == customer_id)
    return session.exec(statement).first()


def get_cards_by_customer(session: Session, customer_id: int) -> List[Card]:
    """Tutte le carte di un cliente (il suo wallet), senza ordinamento."""
    return session.exec(select(Card).where(Card.customer_id == customer_id)).all()


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
