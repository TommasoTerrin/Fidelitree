"""
Schemi Pydantic per la validazione dell'input e dell'output relativi alle Card.
"""

from pydantic import BaseModel, ConfigDict, Field, computed_field
from typing import Optional
import uuid

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


class ConvertedInfo(BaseModel):
    """Conversione avvenuta durante uno scan; `cashback_added` è in euro."""
    conversions: int
    cashback_added: float


class ScanResponse(BaseModel):
    """Risposta a uno scan: carta, eventuale conversione e pool del mese aggiornato."""
    card: CardResponse
    converted: Optional[ConvertedInfo] = None
    pool: PoolProgress
