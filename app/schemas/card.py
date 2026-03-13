# app/schemas/card.py
# Pydantic schemas per validazione input/output delle TreeCard
#
# Usati dalle business calls (api.py) per garantire dati corretti

from pydantic import BaseModel, Field
import uuid


class AddPointsRequest(BaseModel):
    """Richiesta di aggiunta punti a una card."""
    points: int = Field(default= 1)


class CardResponse(BaseModel):
    """Risposta con i dati di una TreeCard."""
    id: uuid.UUID
    merchant_id: int
    current_points: int
    trees_planted: int
    trees_list: list[str]
