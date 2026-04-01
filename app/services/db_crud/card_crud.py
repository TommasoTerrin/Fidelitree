import uuid
import logging
import json
from typing import List, Optional
from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.models import Merchant, TreeCard

logger = logging.getLogger(__name__)

def _get_clean_trees_list(card: TreeCard) -> List[str]:
    """Helper interno per pulire la lista degli alberi."""
    raw_data = card.trees_list
    if isinstance(raw_data, list):
        actual_list = raw_data
    elif isinstance(raw_data, str) and raw_data.strip():
        try:
            actual_list = json.loads(raw_data)
            if not isinstance(actual_list, list):
                actual_list = []
        except:
            actual_list = []
    else:
        actual_list = []
    
    # Pulizia UUID
    cleaned = [str(t) for t in actual_list if len(str(t)) > 5]
    return cleaned

def create_card(session: Session, merchant_id: int, card_type: str = "just_trees") -> TreeCard:
    """Crea una nuova TreeCard."""
    merchant = session.get(Merchant, merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant non trovato")

    new_card = TreeCard(merchant_id=merchant_id, type=card_type)
    session.add(new_card)
    session.commit()
    session.refresh(new_card)
    logger.info("Nuova TreeCard creata: %s (merchant=%s)", new_card.id, merchant_id)
    return new_card

def get_card_by_id(session: Session, card_id: uuid.UUID) -> Optional[TreeCard]:
    """Recupera una carta per ID e ne pulisce la lista alberi."""
    card = session.get(TreeCard, card_id)
    if card:
        card.trees_list = _get_clean_trees_list(card)
    return card

def get_all_cards(session: Session, skip: int = 0, limit: int = 100) -> List[TreeCard]:
    """Restituisce la lista di tutte le TreeCard."""
    statement = select(TreeCard).offset(skip).limit(limit)
    results = session.exec(statement).all()
    for card in results:
        card.trees_list = _get_clean_trees_list(card)
    return results

def delete_card(session: Session, card_id: uuid.UUID):
    """Elimina una carta."""
    card = session.get(TreeCard, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="TreeCard non trovata")
    session.delete(card)
    session.commit()

def update_card_points(session: Session, card: TreeCard, points: int):
    """Aggiorna i punti di una carta (operazione atomica sul DB)."""
    card.current_points += points
    session.add(card)
    session.commit()
    session.refresh(card)
    return card
