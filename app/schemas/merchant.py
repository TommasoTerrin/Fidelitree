"""
Schemi Pydantic per la gestione degli esercenti (Merchant).
Gli importi escono ed entrano in euro; in DB sono centesimi interi.
"""

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, computed_field
from typing import Annotated, Any, Optional, Literal

from app.core.money import cents_to_euro
from app.services.merchant_service import InstagramPanel
from app.services.tree_service import LevelThresholds

NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RegisterRequest(BaseModel):
    """
    Registrazione self-service di un merchant. Nessun vincolo Pydantic e tutti i campi con un default: la
    validazione sta in `merchant_service.validate_registration` (400), perché un 422 di FastAPI su un campo
    mancante o del tipo sbagliato rimanderebbe indietro il corpo della richiesta, password compresa.
    """
    business_name: Any = ""
    email: Any = ""
    password: Any = ""
    contact_phone: Any = None


class ChangePasswordRequest(BaseModel):
    """
    Cambio password del merchant autenticato. Come `RegisterRequest`: nessun vincolo né campo obbligatorio,
    si valida nel service (400/401) e nessuna risposta riporta le password.
    """
    current_password: Any = ""
    new_password: Any = ""


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


class InstagramKeyRequest(BaseModel):
    """
    Chiave Zernio incollata dal merchant. Resta un valore qualunque senza vincoli Pydantic: la forma si controlla
    in `merchant_service.validate_zernio_key` (400), perché l'errore 422 di FastAPI rimanderebbe indietro il valore.
    """
    api_key: Any = ""


class InstagramAccountRequest(BaseModel):
    """Account Instagram scelto tra quelli collegati alla chiave Zernio (`id` di Zernio)."""
    account_id: Any = ""


class InstagramAccountResponse(BaseModel):
    """Account Instagram collegato a Zernio, come lo vede il merchant (nessun dato riservato)."""
    id: str
    username: Optional[str] = None


class InstagramAccountsResponse(BaseModel):
    """Elenco degli account Instagram tra cui scegliere."""
    accounts: list[InstagramAccountResponse]


class InstagramPanelResponse(InstagramPanel):
    """
    Pannello Instagram del merchant: stato, `@username`, chiave mascherata (`…1234`), parola chiave, quota e avvisi.
    **Non contiene mai** la chiave Zernio, il secret o l'id del webhook.
    """
