"""
Definizione dei modelli database SQLModel per l'applicazione Fidelitree.

Tabelle: Merchant (esercenti), Customer (clienti), Card (carta cliente↔negozio),
PointTransaction (registro movimenti, fonte di verità), MerchantPool (contatore
del pool mensile, cache del registro) e TreePlanting (piantumazioni di fine mese).

Convenzioni: denaro in centesimi interi (`*_cents`), timestamp UTC aware,
mese UTC come `period` 'YYYY-MM'. I validatori pydantic sulle tabelle NON girano
nel costruttore: usare `Model.model_validate(...)`.
"""

import uuid
from datetime import datetime
from typing import Optional, List

from pydantic import field_validator
from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import SQLModel, Field, Relationship

from app.core.clock import utc_now
from app.core.enums import Level, PointTransactionKind


def _created_at_field(index: bool = False):
    """Campo `created_at`: UTC aware alla creazione, colonna con timezone."""
    return Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=index),
    )


def _normalize_email(v: str) -> str:
    """Email senza spazi ai lati e in minuscolo (evita doppioni 'Mario@..' / 'mario@..')."""
    return v.strip().lower()


class Merchant(SQLModel, table=True):
    """
    Esercente registrato. Identificato per email (l'autenticazione è delegata al
    provider auth: nessuna password nel nostro DB). Contiene l'approvazione
    manuale, la configurazione della conversione tree points → cashback e gli
    eventuali override admin delle soglie dei livelli del pool.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    business_name: str
    email: str = Field(unique=True, index=True)  # normalizzata in minuscolo
    auth_user_id: Optional[str] = Field(default=None, unique=True, index=True)
    contact_phone: Optional[str] = Field(default=None)  # facoltativo, formato +39
    type: str = Field(default="test")  # 'test', 'free', 'pro'
    is_approved: bool = Field(default=False)  # solo i negozi approvati contano per gli alberi

    # --- Conversione tree points → cashback (a carico del merchant) ---
    conversion_enabled: bool = Field(default=True)
    conversion_threshold: int = Field(default=50)       # tree points per conversione
    conversion_value_cents: int = Field(default=200)    # cashback per conversione (centesimi)

    # --- Override admin delle soglie del pool (None = default di piattaforma) ---
    bronze_threshold: Optional[int] = Field(default=None)
    silver_threshold: Optional[int] = Field(default=None)
    gold_threshold: Optional[int] = Field(default=None)

    cards: List["Card"] = Relationship(
        back_populates="merchant",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    transactions: List["PointTransaction"] = Relationship(
        back_populates="merchant",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    pools: List["MerchantPool"] = Relationship(
        back_populates="merchant",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    plantings: List["TreePlanting"] = Relationship(
        back_populates="merchant",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return _normalize_email(v)

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Valida che il tipo di merchant sia uno tra quelli ammessi."""
        if v not in ('test', 'free', 'pro'):
            raise ValueError("type deve essere 'test', 'free' o 'pro'")
        return v

    @field_validator("conversion_threshold")
    @classmethod
    def validate_conversion_threshold(cls, v: int) -> int:
        if v < 1:
            raise ValueError("conversion_threshold deve essere almeno 1")
        return v

    @field_validator("conversion_value_cents")
    @classmethod
    def validate_conversion_value(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("conversion_value_cents deve essere maggiore di 0")
        return v

    @field_validator("bronze_threshold", "silver_threshold", "gold_threshold")
    @classmethod
    def validate_tier_override(cls, v: Optional[int]) -> Optional[int]:
        """Un override, se presente, deve essere almeno 1."""
        if v is not None and v < 1:
            raise ValueError("le soglie dei livelli devono essere almeno 1")
        return v

    @field_validator("contact_phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Se valorizzato, il telefono deve avere prefisso italiano +39 e 9-10 cifre."""
        if v is None:
            return v
        if not v.startswith("+39"):
            raise ValueError("ricorda che devi inserire +39")

        digits = v[3:]
        if not digits.isdigit():
            raise ValueError("non sono tutti numeri quelli inseriti")
        if len(digits) not in (9, 10):
            raise ValueError("le cifre devono essere 9 o 10")
        return v


class Customer(SQLModel, table=True):
    """Cliente finale: si iscrive con email e ha una carta per ogni negozio."""
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)  # normalizzata in minuscolo
    auth_user_id: Optional[str] = Field(default=None, unique=True, index=True)
    created_at: datetime = _created_at_field()

    cards: List["Card"] = Relationship(
        back_populates="customer",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return _normalize_email(v)


class Card(SQLModel, table=True):
    """
    Carta fedeltà di un cliente presso un negozio (una sola per coppia).
    Tiene il credito cashback (centesimi) e i tree points accumulati.
    """
    __table_args__ = (UniqueConstraint("merchant_id", "customer_id"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    merchant_id: int = Field(foreign_key="merchant.id", ondelete="CASCADE")
    customer_id: int = Field(foreign_key="customer.id", ondelete="CASCADE")
    cashback_cents: int = Field(default=0)  # credito in centesimi di euro
    tree_points: int = Field(default=0)     # tree points non ancora convertiti

    merchant: Merchant = Relationship(back_populates="cards")
    customer: Customer = Relationship(back_populates="cards")


class PointTransaction(SQLModel, table=True):
    """
    Registro dei movimenti di tree points: fonte di verità e audit.
    `card_id` è un riferimento semplice (non FK) così il registro sopravvive
    all'eliminazione della carta. `period` ('YYYY-MM', mese UTC) è fissato in
    scrittura. Nessun indice extra: il pool si legge da `MerchantPool`.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: int = Field(foreign_key="merchant.id", ondelete="CASCADE")
    card_id: uuid.UUID
    kind: PointTransactionKind
    delta: int
    period: str
    created_at: datetime = _created_at_field()

    merchant: Merchant = Relationship(back_populates="transactions")


class MerchantPool(SQLModel, table=True):
    """
    Contatore del pool mensile di un negozio: somma dei movimenti `scan` del
    `period`. È una cache del registro `PointTransaction`, aggiornata nella
    stessa transazione dello scan e mai ricalcolata in lettura.
    """
    merchant_id: int = Field(foreign_key="merchant.id", ondelete="CASCADE", primary_key=True)
    period: str = Field(primary_key=True)  # 'YYYY-MM' (mese UTC)
    points: int = Field(default=0)

    merchant: Merchant = Relationship(back_populates="pools")


class TreePlanting(SQLModel, table=True):
    """
    Piantumazione di fine mese per un negozio. L'unicità
    `(merchant_id, period, test)` rende la chiusura idempotente: una prova
    (`test=True`) non blocca la chiusura vera. `pool_points` è lo snapshot dei
    punti al momento della chiusura; `ecologi_ref` l'identificativo dell'acquisto.
    """
    __table_args__ = (UniqueConstraint("merchant_id", "period", "test"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: int = Field(foreign_key="merchant.id", ondelete="CASCADE", index=True)
    period: str
    level: Level
    tree_count: int
    pool_points: int
    ecologi_ref: Optional[str] = Field(default=None)
    test: bool = Field(default=False)  # True se piantato in test mode (nessun addebito)
    created_at: datetime = _created_at_field(index=True)

    merchant: Merchant = Relationship(back_populates="plantings")
