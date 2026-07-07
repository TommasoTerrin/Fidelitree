"""
Definizione dei modelli database SQLModel per l'applicazione Fidelitree.
Include le tabelle Merchant (esercenti) e Card (carte fedeltà).
"""

import uuid
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship
from pydantic import field_validator


class Merchant(SQLModel, table=True):
    """
    Rappresenta un esercente registrato nel sistema.
    Contiene le credenziali di accesso e il tipo di piano.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    business_name: str
    phone_number: str
    password: str  # salvata cifrata via Fernet
    type: str = Field(default="test")  # 'test', 'free', 'pro'

    cards: List["Card"] = Relationship(
        back_populates="merchant",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )  # relazione con le carte del merchant (1:N)

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Valida che il tipo di merchant sia uno tra quelli ammessi."""
        if v not in ('test', 'free', 'pro'):
            raise ValueError("type deve essere 'test', 'free' o 'pro'")
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
    Tiene traccia del credito cashback accumulato.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    merchant_id: int = Field(foreign_key="merchant.id")
    cashback_point: float = Field(default=0.0)  # credito in euro

    merchant: Merchant = Relationship(back_populates="cards")
