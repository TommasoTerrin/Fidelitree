"""
Schemi Pydantic per la gestione degli esercenti (Merchant).
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal


class MerchantCreateRequest(BaseModel):
    """Richiesta di creazione di un nuovo merchant (endpoint admin)."""
    business_name: str
    phone_number: str
    password: str
    type: Literal['test', 'free', 'pro'] = 'test'
    mode: Literal['trees', 'trees_cashback'] = 'trees_cashback'
    ecologi_api_key: Optional[str] = None  # opzionale solo via admin (test/seed)
    tree_threshold: int = Field(default=10, ge=1)
    monthly_tree_cap: int = Field(default=50, ge=0)


class MerchantRegisterRequest(BaseModel):
    """Registrazione self-service: la chiave Ecologi è obbligatoria e viene validata."""
    business_name: str
    phone_number: str
    password: str = Field(min_length=8)
    ecologi_api_key: str = Field(min_length=1)
    mode: Literal['trees', 'trees_cashback'] = 'trees_cashback'
    tree_threshold: int = Field(default=10, ge=1)
    monthly_tree_cap: int = Field(default=50, ge=0)


class MerchantUpdateRequest(BaseModel):
    """Richiesta di aggiornamento parziale dei dati di un merchant (endpoint admin)."""
    business_name: Optional[str] = None
    phone_number: Optional[str] = None
    password: Optional[str] = None
    type: Optional[Literal['test', 'free', 'pro']] = None
    mode: Optional[Literal['trees', 'trees_cashback']] = None
    ecologi_api_key: Optional[str] = None
    tree_threshold: Optional[int] = Field(default=None, ge=1)
    monthly_tree_cap: Optional[int] = Field(default=None, ge=0)


class MerchantSettingsRequest(BaseModel):
    """Impostazioni modificabili dal merchant autenticato (pagina settings)."""
    mode: Optional[Literal['trees', 'trees_cashback']] = None
    ecologi_api_key: Optional[str] = None  # se presente viene validata e sostituita
    tree_threshold: Optional[int] = Field(default=None, ge=1)
    monthly_tree_cap: Optional[int] = Field(default=None, ge=0)


class MerchantResponse(BaseModel):
    """Schema di risposta per i dati di un merchant (esclude password e chiave Ecologi)."""
    id: int
    business_name: str
    phone_number: str
    type: str
    mode: str
    tree_threshold: int
    monthly_tree_cap: int

    class Config:
        from_attributes = True
