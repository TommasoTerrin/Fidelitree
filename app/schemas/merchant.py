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
    humami_api_key: str
    humami_enterprise_id: str
    points_to_tree: int = 10
    type: Literal['test', 'free', 'pro'] = 'test'
    cb_points_per_tree: int = 0


class MerchantUpdateRequest(BaseModel):
    """Richiesta di aggiornamento parziale dei dati di un merchant."""
    business_name: Optional[str] = None
    phone_number: Optional[str] = None
    password: Optional[str] = None
    humami_api_key: Optional[str] = None
    humami_enterprise_id: Optional[str] = None
    points_to_tree: Optional[int] = None
    type: Optional[Literal['test', 'free', 'pro']] = None
    cb_points_per_tree: Optional[int] = None


class MerchantResponse(BaseModel):
    """Schema di risposta per i dati di un merchant (esclude password e chiavi API)."""
    id: int
    business_name: str
    phone_number: str
    points_to_tree: int
    type: str
    cb_points_per_tree: int

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    """Richiesta di autenticazione per un merchant."""
    password: str
