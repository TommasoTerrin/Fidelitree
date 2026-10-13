"""
Schemi Pydantic per la validazione dell'input e dell'output relativi alle Card.
"""

from pydantic import BaseModel, ConfigDict, Field, computed_field
from typing import Optional
import uuid

from app.core.enums import Level
from app.core.money import cents_to_euro
from app.services.tree_service import PoolProgress


class AddPointsRequest(BaseModel):
    """Richiesta di aggiunta/rimozione cashback (in euro) su una card."""
    cb_points: float = Field(default=0.0)


class AddTreePointsRequest(BaseModel):
    """Richiesta di aggiunta/rimozione tree points su una card."""
    tree_points: int = Field(default=0)


class CardResponse(BaseModel):
    """Risposta con i dati di una Card. Il cashback esce in euro (in DB è in centesimi)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    merchant_id: int
    cashback_cents: int = Field(exclude=True)
    tree_points: int

    @computed_field
    @property
    def cashback_point(self) -> float:
        """Credito cashback in euro, derivato da `cashback_cents`."""
        return cents_to_euro(self.cashback_cents)


class JoinResponse(BaseModel):
    """Esito dell'iscrizione a un negozio: la carta e se è stata appena creata."""
    card_id: uuid.UUID
    created: bool


class WalletEntryResponse(BaseModel):
    """Carta nel wallet con il livello del pool del negozio. Il cashback esce in euro."""
    model_config = ConfigDict(from_attributes=True)

    card_id: uuid.UUID
    merchant_id: int
    business_name: str
    cashback_cents: int = Field(exclude=True)
    tree_points: int
    level: Level
    pool_points: int
    next_level: Optional[Level]
    points_to_next: Optional[int]
    percent_to_next: int
    trees_at_month_end: int

    @computed_field
    @property
    def cashback_point(self) -> float:
        """Credito cashback in euro, derivato da `cashback_cents`."""
        return cents_to_euro(self.cashback_cents)


class ConvertedInfo(BaseModel):
    """Conversione avvenuta durante uno scan; `cashback_added` è in euro."""
    conversions: int
    cashback_added: float


class ScanResponse(BaseModel):
    """Risposta a uno scan: carta, eventuale conversione e pool del mese aggiornato."""
    card: CardResponse
    converted: Optional[ConvertedInfo] = None
    pool: PoolProgress
