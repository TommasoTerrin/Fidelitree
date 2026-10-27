"""
Logica di business delle Card (carte fedeltà): saldi, scan e conversione.

Regole di business
------------------
- Uno **scan** aggiunge (o toglie) tree points a una carta, scrive un movimento nel registro
  (`PointTransaction`, fonte di verità) e incrementa il contatore del pool del mese
  (`MerchantPool`) nella stessa transazione. Lo scan non chiama mai Ecologi.
- Se il negozio ha la conversione attiva, a soglia raggiunta i tree points diventano cashback:
  la conversione scrive un movimento `conversion` e **non** riduce il pool.
- I saldi non scendono mai sotto zero; il cashback è in centesimi interi, senza tolleranze.
- **Stato del servizio** (in attesa / attivo / in pausa, derivato da `is_approved` e `is_paused`): solo un
  negozio attivo può **aggiungere** tree points o cashback; togliere si può sempre. Fuori dallo stato
  attivo non scatta nessuna conversione (sarebbe un accredito). Il controllo precede ogni scrittura.

La sezione `# --- Core puro ---` usa solo Pydantic e stdlib e solleva errori di dominio;
la sezione `# --- Shell ---` esegue le query e conserva gli import di infrastruttura.
"""

from pydantic import BaseModel

from app.core.enums import ServiceState
from app.core.errors import ForbiddenError, InsufficientBalanceError

# --- Core puro ---

_PENDING_MESSAGE = "In attesa di approvazione: non puoi aggiungere punti"
_PAUSED_MESSAGE = "Servizio in pausa: puoi solo togliere il saldo esistente"


def service_state(is_approved: bool, is_paused: bool) -> ServiceState:
    """
    Stato del servizio di un negozio: non approvato → `PENDING` (la pausa non conta); approvato e in
    pausa → `PAUSED`; approvato e non in pausa → `ACTIVE`.
    """
    if not is_approved:
        return ServiceState.PENDING
    return ServiceState.PAUSED if is_paused else ServiceState.ACTIVE


def can_add_balance(state: ServiceState) -> bool:
    """Aggiungere tree points o cashback è consentito solo a un negozio attivo."""
    return state is ServiceState.ACTIVE


def can_remove_balance(state: ServiceState) -> bool:
    """Togliere saldo è consentito sempre, in ogni stato."""
    return True


def check_balance_change(state: ServiceState, delta: int) -> None:
    """
    Controlla che un movimento di saldo (tree points o centesimi di cashback) sia ammesso nello stato dato:
    delta positivo solo se `can_add_balance`, negativo solo se `can_remove_balance`, zero sempre.
    Solleva `ForbiddenError` (403) con un messaggio chiaro per il merchant.
    """
    if delta > 0 and not can_add_balance(state):
        raise ForbiddenError(_PENDING_MESSAGE if state is ServiceState.PENDING else _PAUSED_MESSAGE)
    if delta < 0 and not can_remove_balance(state):
        raise ForbiddenError(_PAUSED_MESSAGE)


class ConversionResult(BaseModel):
    """Esito del calcolo di conversione tree points → cashback."""

    tree_points_left: int
    cashback_added_cents: int
    conversions: int


def apply_tree_points_delta(balance: int, delta: int) -> int:
    """Nuovo saldo di tree points; `InsufficientBalanceError` se scenderebbe sotto zero."""
    new_balance = balance + delta
    if new_balance < 0:
        raise InsufficientBalanceError("Impossibile portare i tree points sotto 0")
    return new_balance


def apply_cashback_delta(balance_cents: int, delta_cents: int) -> int:
    """Nuovo saldo cashback in centesimi; `InsufficientBalanceError` se scenderebbe sotto zero."""
    new_balance = balance_cents + delta_cents
    if new_balance < 0:
        raise InsufficientBalanceError("Impossibile portare il cashback sotto 0")
    return new_balance


def compute_conversion(tree_points: int, threshold: int, value_cents: int) -> ConversionResult:
    """Quante conversioni a soglia entrano nei punti, il residuo e il cashback guadagnato."""
    conversions = tree_points // threshold
    return ConversionResult(
        tree_points_left=tree_points % threshold,
        cashback_added_cents=conversions * value_cents,
        conversions=conversions,
    )


class ConversionProgress(BaseModel):
    """Avanzamento di una carta verso la prossima conversione in cashback."""

    points_to_next: int
    percent: int  # 0..100


def conversion_progress(tree_points: int, threshold: int) -> ConversionProgress:
    """
    Punti che mancano alla prossima conversione e percentuale di avanzamento (per difetto).
    Con un saldo già a soglia o oltre (non dovrebbe capitare: la conversione è automatica)
    risulta 0 punti mancanti e 100%.
    """
    tree_points = max(tree_points, 0)
    if tree_points >= threshold:
        return ConversionProgress(points_to_next=0, percent=100)
    return ConversionProgress(
        points_to_next=threshold - tree_points,
        percent=tree_points * 100 // threshold,
    )


# --- Shell ---

import logging  # noqa: E402
import uuid  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import datetime  # noqa: E402
from typing import Optional  # noqa: E402

from sqlalchemy import update  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.core.clock import utc_now  # noqa: E402
from app.core.enums import PointTransactionKind  # noqa: E402
from app.core.errors import DomainError, NotFoundError  # noqa: E402
from app.core.money import euro_to_cents  # noqa: E402
from app.models.models import Card, Merchant, MerchantPool, PointTransaction  # noqa: E402
from app.services.db_crud import card_crud  # noqa: E402
from app.services.tree_service import period_for  # noqa: E402

logger = logging.getLogger(__name__)

_CARD_NOT_VALID = "Card non valida per questo merchant"


@dataclass
class ScanResult:
    """Esito di uno scan: la carta aggiornata e l'eventuale conversione avvenuta."""

    card: Card
    conversions: int = 0
    cashback_added_cents: int = 0


def merchant_state(merchant: Merchant) -> ServiceState:
    """Stato del servizio del negozio (letto da `is_approved` e `is_paused`)."""
    return service_state(merchant.is_approved, merchant.is_paused)


def _increment_pool(session: Session, merchant_id: int, period: str, delta: int) -> None:
    """Crea la riga del pool se manca, poi incrementa `points` con un UPDATE SQL atomico."""
    if session.get(MerchantPool, (merchant_id, period)) is None:
        session.add(MerchantPool(merchant_id=merchant_id, period=period, points=0))
        session.flush()
    session.execute(
        update(MerchantPool)
        .where(MerchantPool.merchant_id == merchant_id, MerchantPool.period == period)
        .values(points=MerchantPool.points + delta)
    )


def add_tree_points(
    session: Session,
    merchant: Merchant,
    card_id: uuid.UUID,
    points: int,
    now: Optional[datetime] = None,
) -> ScanResult:
    """
    Scan: aggiorna il saldo, scrive il movimento, incrementa il pool del mese ed eventualmente
    converte in cashback. Tutto in un'unica transazione con un solo commit; in caso di errore
    non resta nulla di scritto. Un negozio non attivo può solo togliere (`ForbiddenError` per un delta
    positivo, prima di scrivere) e non converte mai: la conversione sarebbe un accredito di cashback.
    """
    now = now or utc_now()
    state = merchant_state(merchant)
    check_balance_change(state, points)
    try:
        card = session.exec(select(Card).where(Card.id == card_id).with_for_update()).first()
        if card is None or card.merchant_id != merchant.id:
            raise NotFoundError(_CARD_NOT_VALID)

        card.tree_points = apply_tree_points_delta(card.tree_points, points)
        period = period_for(now)
        session.add(PointTransaction(
            merchant_id=merchant.id, card_id=card.id, kind=PointTransactionKind.SCAN,
            delta=points, period=period, created_at=now,
        ))
        _increment_pool(session, merchant.id, period, points)

        result = ScanResult(card=card)
        if merchant.conversion_enabled and can_add_balance(state):
            conversion = compute_conversion(
                card.tree_points, merchant.conversion_threshold, merchant.conversion_value_cents
            )
            if conversion.conversions > 0:
                card.tree_points = conversion.tree_points_left
                card.cashback_cents = apply_cashback_delta(
                    card.cashback_cents, conversion.cashback_added_cents
                )
                session.add(PointTransaction(
                    merchant_id=merchant.id, card_id=card.id, kind=PointTransactionKind.CONVERSION,
                    delta=-(conversion.conversions * merchant.conversion_threshold),
                    period=period, created_at=now,
                ))
                result.conversions = conversion.conversions
                result.cashback_added_cents = conversion.cashback_added_cents

        session.add(card)
        session.commit()
        session.refresh(card)
    except Exception:
        session.rollback()
        raise
    logger.info("Scan su card %s: %+d tree points, %d conversioni", card.id, points, result.conversions)
    return result


def update_cashback(
    session: Session,
    merchant: Merchant,
    card_id: uuid.UUID,
    cb_points: float
) -> Card:
    """
    Aggiunge (o rimuove, se negativo) credito cashback a una carta.
    L'importo arriva in euro e viene convertito in centesimi interi al bordo.
    La carta deve appartenere al merchant autenticato; è sempre disponibile,
    anche con la conversione disattivata. Un negozio non attivo può solo togliere:
    `ForbiddenError` per un importo che in centesimi è positivo, prima di scrivere.
    """
    card = card_crud.get_card_by_id(session, card_id)
    if not card or card.merchant_id != merchant.id:
        raise NotFoundError(_CARD_NOT_VALID)

    try:
        delta_cents = euro_to_cents(cb_points)
    except ValueError as e:
        raise DomainError(str(e))
    check_balance_change(merchant_state(merchant), delta_cents)

    card.cashback_cents = apply_cashback_delta(card.cashback_cents, delta_cents)
    session.add(card)
    session.commit()
    session.refresh(card)
    logger.info("Cashback aggiornato per card %s: %+d centesimi", card.id, delta_cents)
    return card
