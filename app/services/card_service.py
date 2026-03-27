import uuid
import logging
from typing import List, Optional
from fastapi import HTTPException
from sqlmodel import Session

from app.models.models import Merchant, TreeCard
from app.services.humani_service import plant_tree
from app.core.security import decrypt_key
from app.services.db_crud import card_crud, merchant_crud

logger = logging.getLogger(__name__)

async def add_points_to_card(
    session: Session, 
    merchant: Merchant, 
    card_id: uuid.UUID, 
    points: int
) -> TreeCard:
    """
    Logica di business per aggiungere punti a una carta e piantare alberi.
    Orchestra operazioni su DB e chiamate esterne.
    """
    card = card_crud.get_card_by_id(session, card_id)
    if not card or card.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="TreeCard non valida per questo merchant")

    if card.current_points + points < 0:
        raise HTTPException(status_code=400, detail="Impossibile portare i punti sotto 0")

    card.current_points += points

    # Decifra credenziali Humani
    humani_api = decrypt_key(merchant.humami_api_key)
    humani_enterprise = decrypt_key(merchant.humami_enterprise_id)

    # Nota: card_crud.get_card_by_id pulisce già trees_list
    current_trees = card.trees_list
    humani_errors: list[str] = []

    # Logica piantaggio alberi basata sui punti del merchant
    while card.current_points >= merchant.points_to_tree:
        try:
            tree_response = await plant_tree(
                api_key=humani_api,
                enterprise_id=humani_enterprise,
                user=str(card.id),
                project_id="44117777",
                tree_count=1,
            )

            tree_uuid = tree_response.get("uuid")
            if tree_uuid:
                current_trees.append(str(tree_uuid))
                card.trees_planted += 1
                card.current_points -= merchant.points_to_tree
                logger.info("Albero piantato per card %s | uuid=%s", card.id, tree_uuid)
            else:
                humani_errors.append("Humani API: UUID mancante nella risposta")
                break
        except Exception as exc:
            msg = f"Errore Humani: {exc}"
            logger.error(msg)
            humani_errors.append(msg)
            break

    card.trees_list = current_trees
    session.add(card)
    session.commit()
    session.refresh(card)
    
    card.warnings = humani_errors if humani_errors else None
    return card

def create_card(session: Session, merchant_id: int) -> TreeCard:
    """Orchestra la creazione della card, delegando al CRUD."""
    return card_crud.create_card(session, merchant_id)

def get_card_by_id(session: Session, card_id: uuid.UUID) -> Optional[TreeCard]:
    """Recupera la card tramite CRUD."""
    return card_crud.get_card_by_id(session, card_id)

def delete_card(session: Session, card_id: uuid.UUID):
    """Elimina la card tramite CRUD."""
    card_crud.delete_card(session, card_id)
