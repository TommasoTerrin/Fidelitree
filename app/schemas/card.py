# app/schemas/card.py
# Pydantic schemas per validazione input/output delle TreeCard
#
# Usati dalle business calls (api.py) per garantire dati corretti

from pydantic import BaseModel, Field, field_validator
import uuid
import json


class AddPointsRequest(BaseModel):
    """Richiesta di aggiunta punti a una card."""
    points: int = Field(default= 1)


class CardUpdateRequest(BaseModel):
    """Richiesta per l'aggiornamento diretto dei dati di una TreeCard."""
    current_points: int | None = None
    cashback_point: int | None = None
    trees_planted: int | None = None


class CardResponse(BaseModel):
    """Risposta con i dati di una TreeCard."""
    id: uuid.UUID
    merchant_id: int
    current_points: int
    cashback_point: int
    trees_planted: int
    trees_list: list[str]
    warnings: list[str] | None = None

    @field_validator("trees_list", "warnings", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            try:
                decoded = json.loads(v)
                return decoded if isinstance(decoded, list) else []
            except:
                return []
        return v

    class Config:
        from_attributes = True
