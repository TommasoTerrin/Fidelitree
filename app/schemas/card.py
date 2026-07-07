"""
Schemi Pydantic per la validazione dell'input e dell'output relativi alle Card.
"""

from pydantic import BaseModel, Field
import uuid


class AddPointsRequest(BaseModel):
    """Richiesta di aggiunta/rimozione cashback su una card."""
    cb_points: float = Field(default=0.0)


class CardResponse(BaseModel):
    """Risposta con i dati di una Card."""
    id: uuid.UUID
    merchant_id: int
    cashback_point: float

    class Config:
        from_attributes = True
