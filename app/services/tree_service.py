"""
Business logic dei Tree Points: accumulo punti sulla carta e piantumazione
automatica via Ecologi al raggiungimento della soglia del merchant.

Regole:
- soglia (merchant.tree_threshold): ogni N tree points → 1 albero;
- cap mensile (merchant.monthly_tree_cap): spend cap di sicurezza sulla
  carta di credito del merchant; a cap raggiunto i punti restano accumulati
  e gli alberi verranno piantati al primo aggiornamento del mese successivo;
- ogni piantumazione è loggata in TreePlanting (audit + contatore pubblico).
"""

import uuid
import logging
from datetime import datetime

from fastapi import HTTPException
from sqlmodel import Session, select, func

from app.core.config import settings
from app.core.security import decrypt_key
from app.models.models import Merchant, Card, TreePlanting
from app.services import ecologi_service
from app.services.db_crud import card_crud

logger = logging.getLogger(__name__)


def trees_planted_this_month(session: Session, merchant_id: int) -> int:
    """Totale alberi piantati dal merchant nel mese corrente (per il cap)."""
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    statement = (
        select(func.coalesce(func.sum(TreePlanting.tree_count), 0))
        .where(TreePlanting.merchant_id == merchant_id)
        .where(TreePlanting.created_at >= month_start)
    )
    return session.exec(statement).one()


def trees_planted_total(session: Session, merchant_id: int | None = None) -> int:
    """Totale alberi realmente piantati (esclude il test mode). Se merchant_id è None: globale."""
    statement = select(func.coalesce(func.sum(TreePlanting.tree_count), 0)).where(
        TreePlanting.test == False  # noqa: E712 — confronto SQL, non Python
    )
    if merchant_id is not None:
        statement = statement.where(TreePlanting.merchant_id == merchant_id)
    return session.exec(statement).one()


async def update_tree_points(
    session: Session,
    merchant: Merchant,
    card_id: uuid.UUID,
    points: int,
) -> tuple[Card, int, str | None]:
    """
    Aggiunge (o rimuove, se negativo) tree points a una carta del merchant
    e pianta gli alberi dovuti se la soglia è raggiunta.
    Ritorna (carta aggiornata, alberi piantati ora, eventuale warning).
    """
    card = card_crud.get_card_by_id(session, card_id)
    if not card or card.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Card non valida per questo merchant")

    if card.tree_points + points < 0:
        raise HTTPException(status_code=400, detail="Impossibile portare i tree points sotto 0")

    card.tree_points += points
    planted_now, warning = await _plant_due_trees(session, merchant, card)

    session.add(card)
    session.commit()
    session.refresh(card)
    logger.info(
        "Tree points aggiornati per card %s: %+d (piantati ora: %d)",
        card.id, points, planted_now,
    )
    return card, planted_now, warning


async def _plant_due_trees(
    session: Session,
    merchant: Merchant,
    card: Card,
) -> tuple[int, str | None]:
    """
    Pianta gli alberi maturati dalla carta, rispettando il cap mensile.
    Non solleva mai per errori Ecologi: i punti restano sulla carta e
    l'operazione del merchant (lo scan) va comunque a buon fine.
    """
    due = card.tree_points // merchant.tree_threshold
    if due == 0:
        return 0, None

    if not merchant.ecologi_api_key:
        return 0, "Chiave Ecologi non configurata: i punti restano accumulati"

    cap_remaining = merchant.monthly_tree_cap - trees_planted_this_month(session, merchant.id)
    if cap_remaining <= 0:
        return 0, (
            f"Cap mensile di {merchant.monthly_tree_cap} alberi raggiunto: "
            "i punti restano accumulati per il mese prossimo"
        )

    to_plant = min(due, cap_remaining)
    try:
        await ecologi_service.purchase_trees(
            api_key=decrypt_key(merchant.ecologi_api_key),
            number=to_plant,
            name=f"Fidelitree carta {card.id.hex[:6]}",  # niente PII del cliente
        )
    except ecologi_service.EcologiError as e:
        logger.error("Piantumazione fallita per card %s: %s", card.id, e)
        return 0, "Piantumazione momentaneamente non riuscita: i punti restano accumulati"

    card.tree_points -= to_plant * merchant.tree_threshold
    card.trees_planted += to_plant
    session.add(TreePlanting(
        merchant_id=merchant.id,
        card_id=card.id,
        tree_count=to_plant,
        test=settings.ECOLOGI_TEST_MODE,
    ))

    warning = None
    if to_plant < due:
        warning = (
            f"Piantati {to_plant} alberi; gli altri {due - to_plant} sono oltre il "
            "cap mensile e restano come punti accumulati"
        )
    return to_plant, warning
