"""
Operazioni CRUD per la gestione delle Card nel database.
"""

import uuid
import logging
from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from app.models.models import Card

logger = logging.getLogger(__name__)


def add_card(session: Session, card: Card) -> Card:
    """
    Salva una carta già costruita (`igsid_hash` e `link_token_hash` li calcola il service). Solleva
    `IntegrityError` se esiste già la carta per `(merchant_id, igsid_hash)` o se manca un campo obbligatorio.
    """
    session.add(card)
    session.commit()
    session.refresh(card)
    logger.info("Nuova Card creata: %s (merchant=%s)", card.id, card.merchant_id)
    return card


def count_cards_by_merchant(session: Session, merchant_ids: List[int]) -> dict[int, int]:
    """Numero di carte per negozio con una sola query raggruppata (chi non ne ha manca dal dizionario)."""
    if not merchant_ids:
        return {}
    rows = session.exec(
        select(Card.merchant_id, func.count(Card.id)).where(Card.merchant_id.in_(merchant_ids)).group_by(Card.merchant_id)
    ).all()
    return {merchant_id: count for merchant_id, count in rows}


def get_card_by_igsid_hash(session: Session, merchant_id: int, igsid_hash: str) -> Optional[Card]:
    """Recupera la carta di un cliente Instagram presso un negozio, dall'indice cieco dell'IGSID."""
    statement = select(Card).where(Card.merchant_id == merchant_id, Card.igsid_hash == igsid_hash)
    return session.exec(statement).first()


def get_card_by_link_token_hash(session: Session, token_hash: str) -> Optional[Card]:
    """Recupera la carta dall'hash SHA-256 del token del suo link (`link_token_hash`, unico e indicizzato)."""
    return session.exec(select(Card).where(Card.link_token_hash == token_hash)).first()


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
