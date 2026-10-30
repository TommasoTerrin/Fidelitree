"""
Definizione dei modelli database SQLModel per l'applicazione Fidelitree.

Tabelle: AuthCredential (password dei merchant col provider `local`), Merchant (esercenti), Card (carta del cliente Instagram presso un negozio),
PointTransaction (registro movimenti, fonte di verità),
MerchantPool (contatore del pool mensile, cache del registro), TreePlanting
(piantumazioni di fine mese), ProcessedWebhookEvent (dedup dei webhook Zernio) e
ZernioSendCounter (contatore mensile degli invii, per l'avviso di quota).

Convenzioni: denaro in centesimi interi (`*_cents`), timestamp UTC aware,
mese UTC come `period` 'YYYY-MM'. I validatori pydantic sulle tabelle NON girano
nel costruttore: usare `Model.model_validate(...)`.
"""

import uuid
from datetime import datetime
from typing import Optional, List

from pydantic import field_validator
from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import SQLModel, Field, Relationship

from app.core.clock import utc_now
from app.core.enums import InstagramStatus, Level, PointTransactionKind, WebhookOutcome


def _created_at_field(index: bool = False):
    """Campo `created_at`: UTC aware alla creazione, colonna con timezone."""
    return Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=index),
    )


def _normalize_email(v: str) -> str:
    """Email senza spazi ai lati e in minuscolo (evita doppioni 'Mario@..' / 'mario@..')."""
    return v.strip().lower()


class AuthCredential(SQLModel, table=True):
    """
    Credenziale del provider di autenticazione `local`: hash `scrypt` della password, separato dai dati del
    negozio come farebbe un provider esterno. Nessuna FK verso `merchant`: il legame è
    `Merchant.auth_user_id == AuthCredential.user_id`. `token_version` entra nel token di sessione: ogni
    cambio o reset della password lo incrementa e invalida le sessioni aperte. L'hash non compare nel `repr`.
    """
    user_id: str = Field(primary_key=True)  # uuid, è anche Merchant.auth_user_id
    email: str = Field(unique=True, index=True)  # normalizzata in minuscolo
    password_hash: str = Field(repr=False)  # "scrypt$n$r$p$salt$hash", mai in log né risposte
    token_version: int = Field(default=1)
    created_at: datetime = _created_at_field()


class Merchant(SQLModel, table=True):
    """
    Esercente registrato. Identificato per email (l'autenticazione è delegata al
    provider auth: con `local` l'hash sta in `AuthCredential`, non qui). Contiene l'approvazione
    manuale, la pausa, la configurazione della conversione tree points → cashback e gli
    eventuali override admin delle soglie dei livelli del pool. Lo stato del servizio
    (in attesa / attivo / in pausa) si deriva da `is_approved` e `is_paused`
    (`card_service.service_state`).
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    business_name: str
    email: str = Field(unique=True, index=True)  # normalizzata in minuscolo
    auth_user_id: Optional[str] = Field(default=None, unique=True, index=True)
    contact_phone: Optional[str] = Field(default=None)  # facoltativo, formato +39
    type: str = Field(default="test")  # 'test', 'free', 'pro'
    is_approved: bool = Field(default=False)  # approvato dal founder: conta per gli alberi e per lo stato del servizio
    is_paused: bool = Field(default=False)  # in pausa (prova finita, abbonamento non pagato); conta solo se approvato
    created_at: datetime = _created_at_field()  # iscrizione (UTC), per la lista admin

    # --- Conversione tree points → cashback (a carico del merchant) ---
    conversion_enabled: bool = Field(default=True)
    conversion_threshold: int = Field(default=50)       # tree points per conversione
    conversion_value_cents: int = Field(default=200)    # cashback per conversione (centesimi)

    # --- Override admin delle soglie del pool (None = default di piattaforma) ---
    bronze_threshold: Optional[int] = Field(default=None)
    silver_threshold: Optional[int] = Field(default=None)
    gold_threshold: Optional[int] = Field(default=None)

    # --- Instagram via Zernio (v0.3.0). Solo zernio_service decifra/legge la chiave Zernio ---
    zernio_api_key_enc: Optional[str] = Field(default=None)  # AES-256-GCM "<key_id>:<base64(nonce+cifrato)>"
    zernio_account_id: Optional[str] = Field(default=None, unique=True)  # account Instagram scelto
    zernio_profile_id: Optional[str] = Field(default=None)
    zernio_team_id: Optional[str] = Field(default=None)      # team Zernio della chiave (oggi sempre vuoto: Zernio non lo espone)
    instagram_username: Optional[str] = Field(default=None)  # handle PUBBLICO del negozio, per il pannello
    webhook_hook_id: Optional[str] = Field(default=None, unique=True, index=True)  # id opaco nel path del webhook
    webhook_secret_enc: Optional[str] = Field(default=None)  # secret del webhook del negozio, cifrato
    zernio_webhook_id: Optional[str] = Field(default=None)   # id del webhook su Zernio (per rimuoverlo)
    instagram_status: InstagramStatus = Field(default=InstagramStatus.NOT_CONNECTED)
    persistent_menu_set: bool = Field(default=False)  # False con account collegato = menu altrui, avviso
    standby_detected_at: Optional[datetime] = Field(  # ultimo messaggio in standby (UTC)
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    standby_owner_app_id: Optional[str] = Field(default=None)  # app proprietaria, se Meta la indica

    cards: List["Card"] = Relationship(
        back_populates="merchant",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    webhook_events: List["ProcessedWebhookEvent"] = Relationship(
        back_populates="merchant",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    transactions: List["PointTransaction"] = Relationship(
        back_populates="merchant",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    pools: List["MerchantPool"] = Relationship(
        back_populates="merchant",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    plantings: List["TreePlanting"] = Relationship(
        back_populates="merchant",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return _normalize_email(v)

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        """Valida che il tipo di merchant sia uno tra quelli ammessi."""
        if v not in ('test', 'free', 'pro'):
            raise ValueError("type deve essere 'test', 'free' o 'pro'")
        return v

    @field_validator("conversion_threshold")
    @classmethod
    def validate_conversion_threshold(cls, v: int) -> int:
        if v < 1:
            raise ValueError("conversion_threshold deve essere almeno 1")
        return v

    @field_validator("conversion_value_cents")
    @classmethod
    def validate_conversion_value(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("conversion_value_cents deve essere maggiore di 0")
        return v

    @field_validator("bronze_threshold", "silver_threshold", "gold_threshold")
    @classmethod
    def validate_tier_override(cls, v: Optional[int]) -> Optional[int]:
        """Un override, se presente, deve essere almeno 1."""
        if v is not None and v < 1:
            raise ValueError("le soglie dei livelli devono essere almeno 1")
        return v

    @field_validator("contact_phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Se valorizzato, il telefono deve avere prefisso italiano +39 e 9-10 cifre."""
        if v is None:
            return v
        if not v.startswith("+39"):
            raise ValueError("ricorda che devi inserire +39")

        digits = v[3:]
        if not digits.isdigit():
            raise ValueError("non sono tutti numeri quelli inseriti")
        if len(digits) not in (9, 10):
            raise ValueError("le cifre devono essere 9 o 10")
        return v


class Card(SQLModel, table=True):
    """
    Carta fedeltà di un cliente Instagram presso un negozio (una sola per coppia).
    Tiene il credito cashback (centesimi) e i tree points accumulati.

    La carta nasce da un DM Instagram ed è identificata da `(merchant_id, igsid_hash)`: dell'IGSID
    si salva solo l'indice cieco. Il token del link non si salva, solo il suo hash. `igsid_hash` e
    `link_token_hash` sono obbligatori (colonne NOT NULL: il costruttore di una tabella SQLModel non
    valida, l'errore arriva dal DB al salvataggio).
    """
    __table_args__ = (UniqueConstraint("merchant_id", "igsid_hash"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)  # è anche il contenuto del QR
    merchant_id: int = Field(foreign_key="merchant.id", ondelete="CASCADE")
    cashback_cents: int = Field(default=0)  # credito in centesimi di euro
    tree_points: int = Field(default=0)     # tree points non ancora convertiti

    igsid_hash: str                                  # HMAC-SHA256 dell'IGSID
    link_version: int = Field(default=1)             # +1 = revoca del link
    link_token_hash: str = Field(unique=True, index=True)  # SHA-256 del token
    zernio_conversation_id: Optional[str] = Field(default=None)  # handle per rispondere, aggiornato a ogni messaggio
    last_inbound_at: Optional[datetime] = Field(  # sentAt dell'ultimo messaggio del cliente (UTC)
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = _created_at_field()

    merchant: Merchant = Relationship(back_populates="cards")


class ProcessedWebhookEvent(SQLModel, table=True):
    """
    Evento webhook Zernio già visto (`X-Zernio-Event-Id`): la riga si inserisce per prima
    e fa da dedup dei retry (consegna at-least-once). Conservata 7 giorni; `outcome`
    registra come è finita l'elaborazione.
    """
    event_id: str = Field(primary_key=True)
    merchant_id: int = Field(foreign_key="merchant.id", ondelete="CASCADE")
    received_at: datetime = _created_at_field(index=True)
    outcome: WebhookOutcome = Field(default=WebhookOutcome.RECEIVED)

    merchant: Merchant = Relationship(back_populates="webhook_events")


class ZernioSendCounter(SQLModel, table=True):
    """
    Invii riusciti del mese per ambito di quota (team Zernio che invia). Serve solo
    all'avviso di quota: è Zernio a fermare gli invii. `quota_scope` oggi è sempre
    "account:<account_id>" (Zernio non espone l'id del team: `zernio_team_id` resta vuoto; il ramo
    "zernio:<team_id>" scatterebbe solo se comparisse), domani "platform"; nessuna FK.
    """
    quota_scope: str = Field(primary_key=True)
    period: str = Field(primary_key=True)  # 'YYYY-MM' (mese UTC)
    sent: int = Field(default=0)


class PointTransaction(SQLModel, table=True):
    """
    Registro dei movimenti di tree points: fonte di verità e audit.
    `card_id` è un riferimento semplice (non FK) così il registro sopravvive
    all'eliminazione della carta. `period` ('YYYY-MM', mese UTC) è fissato in
    scrittura. Nessun indice extra: il pool si legge da `MerchantPool`.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: int = Field(foreign_key="merchant.id", ondelete="CASCADE")
    card_id: uuid.UUID
    kind: PointTransactionKind
    delta: int
    period: str
    created_at: datetime = _created_at_field()

    merchant: Merchant = Relationship(back_populates="transactions")


class MerchantPool(SQLModel, table=True):
    """
    Contatore del pool mensile di un negozio: somma dei movimenti `scan` del
    `period`. È una cache del registro `PointTransaction`, aggiornata nella
    stessa transazione dello scan e mai ricalcolata in lettura.
    """
    merchant_id: int = Field(foreign_key="merchant.id", ondelete="CASCADE", primary_key=True)
    period: str = Field(primary_key=True)  # 'YYYY-MM' (mese UTC)
    points: int = Field(default=0)

    merchant: Merchant = Relationship(back_populates="pools")


class TreePlanting(SQLModel, table=True):
    """
    Piantumazione di fine mese per un negozio. L'unicità
    `(merchant_id, period, test)` rende la chiusura idempotente: una prova
    (`test=True`) non blocca la chiusura vera. `pool_points` è lo snapshot dei
    punti al momento della chiusura; `ecologi_ref` l'identificativo dell'acquisto.
    """
    __table_args__ = (UniqueConstraint("merchant_id", "period", "test"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: int = Field(foreign_key="merchant.id", ondelete="CASCADE", index=True)
    period: str
    level: Level
    tree_count: int
    pool_points: int
    ecologi_ref: Optional[str] = Field(default=None)
    test: bool = Field(default=False)  # True se piantato in test mode (nessun addebito)
    created_at: datetime = _created_at_field(index=True)

    merchant: Merchant = Relationship(back_populates="plantings")
