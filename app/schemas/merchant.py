"""
Schemi Pydantic per la gestione degli esercenti (Merchant).
"""

from pydantic import BaseModel
from typing import Optional, Literal


class MerchantCreateRequest(BaseModel):
    """Richiesta di creazione di un nuovo merchant."""
    business_name: str
    phone_number: str
    password: str
    type: Literal['test', 'free', 'pro'] = 'test'


class MerchantUpdateRequest(BaseModel):
    """Richiesta di aggiornamento parziale dei dati di un merchant."""
    business_name: Optional[str] = None
    phone_number: Optional[str] = None
    password: Optional[str] = None
    type: Optional[Literal['test', 'free', 'pro']] = None


class MerchantResponse(BaseModel):
    """Schema di risposta per i dati di un merchant (esclude la password)."""
    id: int
    business_name: str
    phone_number: str
    type: str

    class Config:
        from_attributes = True
