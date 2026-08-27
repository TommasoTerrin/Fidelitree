"""
Definizione dei modelli database SQLModel per l'applicazione Fidelitree.
Include le tabelle Merchant (esercenti), Card (carte fedeltà)
e TreePlanting (log delle piantumazioni via Ecologi).
"""

import uuid
from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship
from pydantic import field_validator


class Merchant(SQLModel, table=True):
    """
    Rappresenta un esercente registrato nel sistema.
    Contiene le credenziali di accesso, il tipo di piano
    e la configurazione tree points (chiave Ecologi, soglia, cap).
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    business_name: str
    phone_number: str = Field(unique=True, index=True)
    password: str  # salvata cifrata via Fernet
    type: str = Field(default="test")  # 'test', 'free', 'pro'

    # --- Tree points ---
    mode: str = Field(default="trees_cashback")  # 'trees' | 'trees_cashback'
    ecologi_api_key: Optional[str] = Field(default=None)  # cifrata via Fernet
    tree_threshold: int = Field(default=10)   # tree points necessari per piantare 1 albero
    monthly_tree_cap: int = Field(default=50)  # max alberi/mese (spend cap); 0 = piantumazione sospesa

    cards: List["Card"] = Relationship(
        back_populates="merchant",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )  # relazione con le carte del merchant (1:N)

    plantings: List["TreePlanting"] = Relationship(
        back_populates="merchant",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )  # log piantumazioni del merchant (1:N)

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Valida che il tipo di merchant sia uno tra quelli ammessi."""
        if v not in ('test', 'free', 'pro'):
            raise ValueError("type deve essere 'test', 'free' o 'pro'")
        return v

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """Valida la modalità della carta: solo tree points o anche cashback."""
        if v not in ('trees', 'trees_cashback'):
            raise ValueError("mode deve essere 'trees' o 'trees_cashback'")
        return v

    @field_validator("tree_threshold")
    @classmethod
    def validate_tree_threshold(cls, v: int) -> int:
        if v < 1:
            raise ValueError("tree_threshold deve essere almeno 1")
        return v

    @field_validator("monthly_tree_cap")
    @classmethod
    def validate_monthly_tree_cap(cls, v: int) -> int:
        if v < 0:
            raise ValueError("monthly_tree_cap non può essere negativo")
        return v

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Valida il formato del numero di telefono (solo prefisso italiano +39)."""
        if not v.startswith("+39"):
            raise ValueError("ricorda che devi inserire +39")

        digits = v[3:]
        if not digits.isdigit():
            raise ValueError("non sono tutti numeri quelli inseriti")
        if len(digits) not in (9, 10):
            raise ValueError("le cifre devono essere 9 o 10")
        return v


class Card(SQLModel, table=True):
    """
    Carta fedeltà digitale associata a un cliente e a un merchant.
    Tiene traccia del credito cashback e dei tree points accumulati.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    merchant_id: int = Field(foreign_key="merchant.id")
    cashback_point: float = Field(default=0.0)  # credito in euro
    tree_points: int = Field(default=0)         # punti verso il prossimo albero
    trees_planted: int = Field(default=0)       # alberi piantati da questa carta

    merchant: Merchant = Relationship(back_populates="cards")


class TreePlanting(SQLModel, table=True):
    """
    Log di ogni piantumazione richiesta a Ecologi: audit trail per il
    conteggio del cap mensile e per il contatore pubblico degli alberi.
    card_id è un riferimento semplice (non FK) così il log sopravvive
    all'eliminazione della carta.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: int = Field(foreign_key="merchant.id", index=True)
    card_id: uuid.UUID
    tree_count: int
    test: bool = Field(default=False)  # True se piantato in test mode (nessun addebito)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    merchant: Merchant = Relationship(back_populates="plantings")
