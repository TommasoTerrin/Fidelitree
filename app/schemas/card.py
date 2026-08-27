"""
Schemi Pydantic per la validazione dell'input e dell'output relativi alle Card.
"""

from pydantic import BaseModel, Field
from typing import Optional
import uuid


class AddPointsRequest(BaseModel):
    """Richiesta di aggiunta/rimozione cashback su una card."""
    cb_points: float = Field(default=0.0)


class AddTreePointsRequest(BaseModel):
    """Richiesta di aggiunta/rimozione tree points su una card."""
    tree_points: int = Field(default=0)


class CardResponse(BaseModel):
    """Risposta con i dati di una Card."""
    id: uuid.UUID
    merchant_id: int
    cashback_point: float
    tree_points: int
    trees_planted: int

    class Config:
        from_attributes = True


class TreePointsResponse(BaseModel):
    """Risposta all'aggiornamento tree points: carta + esito piantumazione."""
    card: CardResponse
    planted_now: int                 # alberi piantati con questa operazione
    warning: Optional[str] = None    # es. cap mensile raggiunto, Ecologi non raggiungibile
