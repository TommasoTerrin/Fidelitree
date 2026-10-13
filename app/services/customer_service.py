"""
Logica di business del cliente: identità, iscrizione a un negozio, wallet e proprietà della carta.

Regole di business
------------------
- Il cliente si iscrive **una volta** con email + OTP (tramite il provider di autenticazione) e
  ha un **wallet**: una carta per ogni negozio a cui si è iscritto (UNIQUE merchant+cliente).
- Il QR statico del negozio (`/join/{negozio}`) crea la carta al primo accesso e la riapre
  dopo; non esistono carte anonime.
- Una carta è visibile **solo al suo proprietario**: per chiunque altro risponde come se non
  esistesse (404), così non si rivela l'esistenza di una carta.
- Nel wallet ogni carta porta il livello del pool del mese corrente del suo negozio.

Il core (`normalize_email`, `safe_next_path`, `build_wallet`) usa solo Pydantic e stdlib e
solleva errori di dominio. La sezione `# --- Shell ---` in fondo parla con DB e provider.
"""

import re
import uuid
from typing import Optional

from pydantic import BaseModel

from app.core.enums import Level
from app.core.errors import InvalidInputError
from app.services.tree_service import PoolProgress

# --- Core puro ---

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

DEFAULT_NEXT_PATH = "/wallet"


def normalize_email(email: str) -> str:
    """
    Email ripulita dagli spazi e in minuscolo.
    Solleva `InvalidInputError` ("Email non valida") se non ha un formato plausibile.
    """
    normalized = (email or "").strip().lower()
    if not _EMAIL_RE.match(normalized):
        raise InvalidInputError("Email non valida")
    return normalized


def safe_next_path(next_path: Optional[str]) -> str:
    """
    Destinazione di un redirect dopo il login, accettata solo se è un percorso interno
    (inizia con una sola `/`, niente schema né backslash): altrimenti `DEFAULT_NEXT_PATH`.
    Evita che `?next=` diventi un open redirect verso siti esterni.
    """
    candidate = (next_path or "").strip()
    if not candidate.startswith("/") or candidate.startswith("//") or "\\" in candidate:
        return DEFAULT_NEXT_PATH
    return candidate


class WalletCardInput(BaseModel):
    """Una carta del cliente con il nome del suo negozio, in ingresso a `build_wallet`."""

    card_id: uuid.UUID
    merchant_id: int
    business_name: str
    cashback_cents: int
    tree_points: int


class WalletEntry(BaseModel):
    """Voce del wallet: la carta più il livello del pool del mese del suo negozio."""

    card_id: uuid.UUID
    merchant_id: int
    business_name: str
    cashback_cents: int
    tree_points: int
    level: Level
    pool_points: int
    next_level: Optional[Level]
    points_to_next: Optional[int]
    percent_to_next: int
    trees_at_month_end: int


def build_wallet(
    cards: list[WalletCardInput],
    pools: dict[int, PoolProgress],
) -> list[WalletEntry]:
    """
    Unisce ogni carta al pool del suo negozio (`pools` è indicizzato per `merchant_id`) e
    ordina le voci per nome del negozio (senza distinguere maiuscole), poi per `merchant_id`.
    Un negozio senza pool risulta a livello `NONE` con zero punti. Lista vuota → `[]`.
    """
    entries = []
    for card in sorted(cards, key=lambda c: (c.business_name.lower(), c.merchant_id)):
        pool = pools.get(card.merchant_id)
        entries.append(WalletEntry(
            card_id=card.card_id,
            merchant_id=card.merchant_id,
            business_name=card.business_name,
            cashback_cents=card.cashback_cents,
            tree_points=card.tree_points,
            level=pool.level if pool else Level.NONE,
            pool_points=pool.points if pool else 0,
            next_level=pool.next_level if pool else None,
            points_to_next=pool.points_to_next if pool else None,
            percent_to_next=pool.percent_to_next if pool else 0,
            trees_at_month_end=pool.trees_at_month_end if pool else 0,
        ))
    return entries


# --- Shell ---

from datetime import datetime  # noqa: E402

from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app.core.auth import AuthIdentity  # noqa: E402
from app.core.clock import utc_now  # noqa: E402
from app.core.errors import ConflictError, NotFoundError  # noqa: E402
from app.models.models import Card, Customer, Merchant  # noqa: E402
from app.services import tree_service  # noqa: E402
from app.services.db_crud import card_crud, customer_crud, merchant_crud  # noqa: E402

_CARD_NOT_FOUND = "Card non trovata"


def get_or_create_customer(session: Session, identity: AuthIdentity) -> Customer:
    """
    Cliente collegato all'identità del provider; lo crea al primo accesso. Idempotente: si
    cerca per `auth_user_id`, poi per email (in quel caso la riga, creata senza identità,
    viene collegata). Due accessi simultanei non producono doppioni.
    Solleva `InvalidInputError` se l'email non è valida e `ConflictError` se esiste un cliente
    con la stessa email ma collegato a un'altra identità.
    """
    customer = customer_crud.get_customer_by_auth_user_id(session, identity.user_id)
    if customer:
        return customer

    email = normalize_email(identity.email)
    customer = customer_crud.get_customer_by_email(session, email)
    if customer:
        if customer.auth_user_id not in (None, identity.user_id):
            raise ConflictError("Esiste già un account con questa email")
        customer.auth_user_id = identity.user_id
        session.add(customer)
        session.commit()
        session.refresh(customer)
        return customer

    try:
        return customer_crud.create_customer(session, email, identity.user_id)
    except IntegrityError:
        # un'altra richiesta ha creato lo stesso cliente nel frattempo: si riusa quello
        session.rollback()
        existing = (
            customer_crud.get_customer_by_auth_user_id(session, identity.user_id)
            or customer_crud.get_customer_by_email(session, email)
        )
        if existing is None:
            raise
        return existing


def join_merchant(session: Session, customer: Customer, merchant_id: int) -> tuple[Card, bool]:
    """
    Iscrive il cliente a un negozio: crea la carta se non esiste per la coppia, altrimenti
    ritorna quella esistente. Ritorna `(carta, creata)`; è idempotente anche con richieste
    simultanee. Solleva `NotFoundError` se il negozio non esiste.
    """
    if merchant_crud.get_merchant_by_id(session, merchant_id) is None:
        raise NotFoundError("Merchant non trovato")

    card = card_crud.get_card_by_merchant_and_customer(session, merchant_id, customer.id)
    if card:
        return card, False
    try:
        return card_crud.create_card(session, merchant_id, customer.id), True
    except IntegrityError:
        # doppio tap o richieste simultanee: la carta è già stata creata dall'altra richiesta
        session.rollback()
        card = card_crud.get_card_by_merchant_and_customer(session, merchant_id, customer.id)
        if card is None:
            raise
        return card, False


def list_wallet(
    session: Session,
    customer: Customer,
    now: Optional[datetime] = None,
) -> list[WalletEntry]:
    """
    Wallet del cliente: le sue carte con il livello del pool del mese di `now` (default:
    adesso, UTC) di ciascun negozio, calcolato con le soglie effettive del negozio.
    """
    now = now or utc_now()
    cards, pools = [], {}
    for card in card_crud.get_cards_by_customer(session, customer.id):
        merchant = session.get(Merchant, card.merchant_id)
        if merchant.id not in pools:
            pools[merchant.id] = tree_service.current_pool_progress(session, merchant, now)
        cards.append(WalletCardInput(
            card_id=card.id,
            merchant_id=merchant.id,
            business_name=merchant.business_name,
            cashback_cents=card.cashback_cents,
            tree_points=card.tree_points,
        ))
    return build_wallet(cards, pools)


def get_owned_card(session: Session, customer: Customer, card_id: uuid.UUID) -> Card:
    """
    Carta del cliente. Solleva `NotFoundError` sia se non esiste sia se appartiene a un
    altro cliente, con lo stesso messaggio: non si rivela l'esistenza delle carte altrui.
    """
    card = card_crud.get_card_by_id(session, card_id)
    if card is None or card.customer_id != customer.id:
        raise NotFoundError(_CARD_NOT_FOUND)
    return card
