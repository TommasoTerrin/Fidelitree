"""
Schemi Pydantic per la gestione degli esercenti (Merchant).
Gli importi escono ed entrano in euro; in DB sono centesimi interi.
"""

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, computed_field
from typing import Annotated, Optional, Literal

from app.core.money import cents_to_euro
from app.services.tree_service import LevelThresholds

NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RegisterRequest(BaseModel):
    """Registrazione self-service di un merchant (la validazione di dominio è in `merchant_service`)."""
    business_name: str
    email: str
    password: str
    contact_phone: Optional[str] = None


class MerchantCreateRequest(BaseModel):
    """Richiesta di creazione di un nuovo merchant (endpoint admin)."""
    business_name: str
    email: str
    contact_phone: Optional[str] = None
    type: Literal['test', 'free', 'pro'] = 'test'
    is_approved: bool = False


class MerchantUpdateRequest(BaseModel):
    """Richiesta di aggiornamento parziale dei dati di un merchant (endpoint admin)."""
    business_name: Optional[str] = None
    email: Optional[str] = None
    contact_phone: Optional[str] = None
    type: Optional[Literal['test', 'free', 'pro']] = None
    is_approved: Optional[bool] = None
    bronze_threshold: Optional[int] = Field(default=None, ge=1)
    silver_threshold: Optional[int] = Field(default=None, ge=1)
    gold_threshold: Optional[int] = Field(default=None, ge=1)


class MerchantSettingsRequest(BaseModel):
    """
    Impostazioni modificabili dal merchant autenticato. Gli altri campi inviati (approvazione,
    tipo, soglie dei livelli...) vengono ignorati: li gestisce solo l'admin.
    """
    business_name: Optional[NonBlankStr] = None
    contact_phone: Optional[str] = None
    conversion_enabled: Optional[bool] = None
    conversion_threshold: Optional[int] = Field(default=None, ge=1)
    conversion_value_eur: Optional[float] = Field(default=None, gt=0)


class MerchantResponse(BaseModel):
    """Schema di risposta per i dati di un merchant."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_name: str
    email: str
    contact_phone: Optional[str] = None
    type: str
    is_approved: bool
    conversion_enabled: bool
    conversion_threshold: int
    conversion_value_cents: int = Field(exclude=True)
    bronze_threshold: Optional[int] = None
    silver_threshold: Optional[int] = None
    gold_threshold: Optional[int] = None

    @computed_field
    @property
    def conversion_value_eur(self) -> float:
        """Valore in euro di una conversione, derivato da `conversion_value_cents`."""
        return cents_to_euro(self.conversion_value_cents)


class MerchantProfileResponse(MerchantResponse):
    """Profilo del merchant autenticato: in più le soglie EFFETTIVE dei livelli (default + override)."""
    effective_thresholds: LevelThresholds
