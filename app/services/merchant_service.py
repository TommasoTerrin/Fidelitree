"""
Logica di business degli esercenti: registrazione, login, impostazioni e gestione admin.

Regole di business
------------------
- Il merchant si registra con email + password tramite il provider di autenticazione: la tabella `merchant`
  non ha nessuna password, solo `auth_user_id` ed email (con il provider `local` l'hash sta in `AuthCredential`).
- Il login ha un freno ai tentativi (5 errori in 15 minuti per email e per IP → 429, vedi `auth.LoginThrottle`);
  il merchant cambia la password dalle impostazioni, il reset lo fa il founder (ticket 13).
- Un merchant appena registrato **lavora subito** (scan, tree points) ma è `is_approved=False`:
  il suo pool conta per la piantumazione solo dopo l'approvazione manuale del founder.
- Il merchant può modificare solo nome, telefono e impostazioni di conversione; approvazione,
  tipo e soglie dei livelli le decide l'admin (con soglie sempre coerenti: bronzo < argento < oro).

Onboarding Instagram (v0.3.0)
-----------------------------
- Il merchant incolla la **sua** chiave Zernio (validata con una chiamata reale, salvata cifrata, mai restituita:
  si mostra solo `…1234`), sceglie l'account Instagram e l'app registra da sola il webhook (id opaco nel path e
  secret per negozio) e, solo se il menu è vuoto, la voce "🌳 La mia carta". Diventa attivo al primo DM di prova
  (lo stato lo cambia il webhook, ticket 06).
- La configurazione è tutto-o-niente: se la registrazione del webhook fallisce non si salva né l'account né
  l'id del webhook. Un errore sul menu invece non blocca: si segnala nel pannello.
- "Scollega" prova a rimuovere il webhook da Zernio (un solo tentativo, l'errore si logga) e cancella comunque
  chiave, secret e campi Zernio; le carte restano.
- Tutte le chiamate a Zernio passano da `zernio_service`; chiave e secret li decifra solo
  `zernio_credentials_for`. Gli errori di Zernio diventano errori di dominio: chiave rifiutata → 400,
  ogni altro errore → `ExternalServiceError` (502), con messaggi fissi senza dettagli.

Il core (`validate_registration`, `validate_zernio_key`, `webhook_url_for`, `classify_persistent_menu`,
`instagram_panel`) usa solo Pydantic e stdlib e solleva errori di dominio.
La sezione `# --- Shell ---` in fondo parla con DB, provider di autenticazione e Zernio.
"""

import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from app.core.auth import MIN_PASSWORD_LENGTH, validate_password  # noqa: F401  (MIN_PASSWORD_LENGTH: nome storico)
from app.core.enums import InstagramStatus
from app.core.errors import InvalidInputError
from app.services.instagram_service import CARD_POSTBACK_PAYLOAD, QuotaStatus, quota_status

# --- Core puro ---

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+39\d{9,10}$")  # stessa regola del modello Merchant


# Il nome è il titolo della card Instagram: stesso valore di `instagram_service.CARD_TITLE_MAX`
# (non importato: un test li tiene allineati).
MAX_BUSINESS_NAME_LENGTH = 80


def validate_business_name(business_name: object) -> str:
    """
    Ripulisce il nome dell'attività dagli spazi e lo valida: obbligatorio e al massimo 80 caratteri,
    così la card del negozio è sempre costruibile. Un valore che non sia testo vale come vuoto.
    Solleva `InvalidInputError` in italiano.
    """
    name = business_name.strip() if isinstance(business_name, str) else ""
    if not name:
        raise InvalidInputError("Il nome dell'attività è obbligatorio")
    if len(name) > MAX_BUSINESS_NAME_LENGTH:
        raise InvalidInputError(
            f"Il nome dell'attività può avere al massimo {MAX_BUSINESS_NAME_LENGTH} caratteri"
        )
    return name


class RegistrationData(BaseModel):
    """Dati di registrazione già validati e normalizzati."""

    business_name: str
    email: str
    password: str
    contact_phone: Optional[str] = None


def validate_registration(
    business_name: object,
    email: object,
    password: object,
    contact_phone: object = None,
) -> RegistrationData:
    """
    Valida e normalizza i dati di registrazione di un merchant.
    Nome e email vengono ripuliti dagli spazi (email anche in minuscolo); la password deve avere 8-128
    caratteri (`auth.validate_password`); il telefono è facoltativo (`None` o stringa vuota = assente) e,
    se presente, deve essere `+39` + 9-10 cifre. Accetta qualunque tipo (un valore che non sia testo vale
    come vuoto: lo schema HTTP non valida, così nessun 422 rimanda indietro la password).
    Solleva `InvalidInputError` con un messaggio in italiano per il primo campo non valido.
    """
    name = validate_business_name(business_name)

    normalized_email = email.strip().lower() if isinstance(email, str) else ""
    if not _EMAIL_RE.match(normalized_email):
        raise InvalidInputError("Email non valida")

    password = validate_password(password)

    phone = (contact_phone.strip() if isinstance(contact_phone, str) else "") or None
    if phone is not None and not _PHONE_RE.match(phone):
        raise InvalidInputError("Il telefono deve avere prefisso +39 seguito da 9 o 10 cifre")

    return RegistrationData(
        business_name=name, email=normalized_email, password=password, contact_phone=phone,
    )


# --- Core puro: onboarding Instagram ---

ZERNIO_KEY_PREFIXES = ("sk_", "zrk_")  # chiave piena e chiave con gruppi disattivati
STANDBY_WARNING_WINDOW = timedelta(days=7)  # l'avviso standby si mostra per una settimana dall'ultimo evento


def validate_zernio_key(api_key: object) -> str:
    """
    Ripulisce la chiave Zernio dagli spazi ai lati e ne controlla la forma: deve iniziare con `sk_` o `zrk_`,
    avere almeno un carattere dopo il prefisso e nessuno spazio dentro. Accetta qualunque tipo (un valore che
    non sia testo vale come vuoto) così il controllo resta qui e non in Pydantic. Solleva `InvalidInputError`;
    il messaggio non riporta mai il valore ricevuto.
    """
    key = api_key.strip() if isinstance(api_key, str) else ""
    prefix = next((p for p in ZERNIO_KEY_PREFIXES if key.startswith(p)), None)
    if prefix is None or len(key) == len(prefix) or any(ch.isspace() for ch in key):
        raise InvalidInputError("Incolla la chiave Zernio: inizia con sk_ o zrk_")
    return key


def webhook_url_for(public_base_url: str, hook_id: str) -> str:
    """
    URL del webhook del negozio: `<base>/webhooks/zernio/<hook_id>`. La base deve iniziare con `https://`
    (Zernio non consegna a un indirizzo http); `InvalidInputError` altrimenti.
    """
    base = (public_base_url or "").strip().rstrip("/")
    if not base.startswith("https://") or base == "https://":
        raise InvalidInputError(
            "L'indirizzo pubblico dell'app (PUBLIC_BASE_URL) deve iniziare con https://: "
            "senza, Instagram non può avvisare l'app dei messaggi"
        )
    return f"{base}/webhooks/zernio/{hook_id}"


class MenuState(str, Enum):
    """Che cosa c'è nel menu persistente dell'account Instagram."""
    EMPTY = "empty"  # nessuna voce: possiamo impostare la nostra
    OURS = "ours"    # c'è già la nostra voce (postback `FIDELITREE_CARD`)
    OTHER = "other"  # ci sono voci di altri (es. ManyChat): non si toccano


def _menu_actions(node: object) -> list[dict]:
    """Tutte le voci (`call_to_actions`, anche annidate) di un menu nel formato Meta, comunque incapsulato."""
    found: list[dict] = []
    if isinstance(node, list):
        for item in node:
            found += _menu_actions(item)
    elif isinstance(node, dict):
        actions = node.get("call_to_actions")
        for action in actions if isinstance(actions, list) else []:
            if isinstance(action, dict):
                found.append(action)
                found += _menu_actions(action)
        if "persistent_menu" in node:
            found += _menu_actions(node["persistent_menu"])
    return found


def classify_persistent_menu(data: object) -> MenuState:
    """
    Classifica il menu letto da Zernio: `OURS` se una voce ha il nostro payload (anche accanto ad altre),
    `OTHER` se ci sono solo voci di altri, `EMPTY` se non ce n'è nessuna (anche con dati inattesi).
    """
    actions = _menu_actions(data)
    if any(a.get("payload") == CARD_POSTBACK_PAYLOAD for a in actions):
        return MenuState.OURS
    return MenuState.OTHER if actions else MenuState.EMPTY


class InstagramWarning(BaseModel):
    """Avviso del pannello Instagram: `code` stabile (menu, standby, key_invalid, quota), `message` in italiano."""

    code: str
    message: str


class InstagramPanelInput(BaseModel):
    """
    Dati del negozio che servono al pannello, già estratti dalla shell: il core non vede mai chiave né secret
    (`key_masked` è già `…1234`). `standby_detected_at` può arrivare senza fuso (SQLite): vale UTC.
    """

    status: InstagramStatus
    username: Optional[str] = None
    account_connected: bool = False
    key_saved: bool = False
    key_masked: Optional[str] = None
    persistent_menu_set: bool = False
    standby_detected_at: Optional[datetime] = None


class InstagramPanel(BaseModel):
    """
    Pannello Instagram del merchant: stato, `@username`, chiave mascherata, parola chiave da mostrare,
    quota del mese (solo con un account collegato) e avvisi. Nessun segreto.
    """

    status: InstagramStatus
    username: Optional[str] = None
    key_saved: bool = False
    key_masked: Optional[str] = None
    keyword: str
    quota: Optional[QuotaStatus] = None
    warnings: list[InstagramWarning] = []


def _as_utc(value: datetime) -> datetime:
    """Un datetime senza fuso (come li restituisce SQLite) è UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def instagram_panel(
    fields: InstagramPanelInput, counter_sent: int, now: datetime, *, keyword: str, send_limit: int, warn_percent: int,
) -> InstagramPanel:
    """
    Compone il pannello. Avvisi: `menu` (account collegato ma voce di menu non impostata), `standby` (un'altra
    app ha preso un messaggio negli ultimi 7 giorni), `key_invalid` (Zernio ha rifiutato la chiave) e `quota`
    (dal `warn_percent`% del `send_limit`, con un testo distinto a quota esaurita). `counter_sent` sono gli invii
    del mese; `keyword` è la parola chiave di piattaforma. Il tempo arriva da `now`.
    """
    warnings: list[InstagramWarning] = []
    if fields.status == InstagramStatus.KEY_INVALID:
        warnings.append(InstagramWarning(
            code="key_invalid",
            message="Zernio ha rifiutato la chiave: incollane una nuova per riattivare la carta.",
        ))
    if fields.account_connected and not fields.persistent_menu_set:
        warnings.append(InstagramWarning(
            code="menu",
            message=(
                "La voce di menu «🌳 La mia carta» non è stata impostata (il tuo account ha già un menu o "
                f"l'impostazione non è riuscita). I clienti possono comunque scrivere {keyword}."
            ),
        ))
    if fields.standby_detected_at is not None and now - _as_utc(fields.standby_detected_at) <= STANDBY_WARNING_WINDOW:
        warnings.append(InstagramWarning(
            code="standby",
            message=(
                "Un'altra app (per esempio ManyChat) gestisce i messaggi del tuo Instagram: finché non la "
                "scolleghi, Fidelitree non può rispondere ai clienti."
            ),
        ))
    quota = quota_status(counter_sent, send_limit, warn_percent) if fields.account_connected else None
    if quota is not None and quota.exhausted:
        warnings.append(InstagramWarning(
            code="quota",
            message=(
                f"Invii mensili di Zernio esauriti ({quota.sent} su {quota.limit}): "
                "fino al mese prossimo le carte non vengono inviate."
            ),
        ))
    elif quota is not None and quota.warning:
        warnings.append(InstagramWarning(
            code="quota",
            message=(
                f"Hai usato il {quota.percent}% degli invii gratuiti del mese ({quota.sent} su {quota.limit}). "
                "Oltre il limite Zernio ferma gli invii."
            ),
        ))
    return InstagramPanel(
        status=fields.status,
        username=fields.username,
        key_saved=fields.key_saved,
        key_masked=fields.key_masked,
        keyword=keyword,
        quota=quota,
        warnings=warnings,
    )


# --- Shell ---

import logging  # noqa: E402
import secrets  # noqa: E402

import httpx  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app.core import crypto  # noqa: E402
from app.core.auth import AuthProvider, PasswordAdminProvider, login_throttle, login_throttle_keys  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.errors import (  # noqa: E402
    AuthError, ConflictError, DomainError, ExternalServiceError, ForbiddenError, NotFoundError,
)
from app.core.money import euro_to_cents  # noqa: E402
from app.models.models import Merchant, ZernioSendCounter  # noqa: E402
from app.services import tree_service, zernio_service  # noqa: E402
from app.services.db_crud import merchant_crud  # noqa: E402
from app.services.instagram_service import MENU_ITEM_TITLE  # noqa: E402

logger = logging.getLogger(__name__)

_DUPLICATE_EMAIL = "Esiste già un account con questa email"

_THRESHOLD_FIELDS = ("bronze_threshold", "silver_threshold", "gold_threshold")


def register_merchant(
    session: Session,
    provider: AuthProvider,
    data: RegistrationData,
) -> tuple[Merchant, str]:
    """
    Registra un merchant: crea l'utente sul provider e la riga `Merchant` (non approvato, tipo
    `free`) collegata tramite `auth_user_id`. Ritorna `(merchant, token)` per l'auto-login.
    Solleva `ConflictError` se l'email è già in uso (nel DB o presso il provider).
    """
    if merchant_crud.get_merchant_by_email(session, data.email):
        raise ConflictError(_DUPLICATE_EMAIL)
    try:
        identity = provider.sign_up(data.email, data.password)
    except AuthError as e:
        raise ConflictError(_DUPLICATE_EMAIL) from e

    try:
        merchant = merchant_crud.create_merchant(session, {
            "business_name": data.business_name,
            "email": data.email,
            "contact_phone": data.contact_phone,
            "type": "free",
            "is_approved": False,
            "auth_user_id": identity.user_id,
        })
    except Exception:
        # Niente credenziale orfana: senza questa pulizia l'email resterebbe bloccata (409) senza un merchant.
        session.rollback()
        remove_auth_user(provider, identity.user_id)
        raise
    return merchant, provider.sign_in_password(data.email, data.password)


def remove_auth_user(provider: AuthProvider, user_id: Optional[str]) -> None:
    """
    Elimina le credenziali di un utente presso il provider, se questo le gestisce (`local`); con `dev` e
    `supabase`, o senza `user_id` (merchant creato dall'admin), non fa nulla. Idempotente.
    """
    if user_id and isinstance(provider, PasswordAdminProvider):
        provider.delete_user(user_id)


def login_merchant(
    session: Session,
    provider: AuthProvider,
    email: str,
    password: str,
    *,
    client_ip: Optional[str],
    now: datetime,
    throttle=login_throttle,
) -> str:
    """
    Verifica email+password col provider e ritorna il token di sessione, con il freno ai tentativi:
    il controllo è PRIMA di ogni verifica (a soglia anche la password giusta riceve 429), ogni errore di
    credenziali (anche email sconosciuta) conta sull'email e sull'IP, un accesso riuscito azzera solo l'email.
    Solleva `TooManyAttemptsError` (429), `AuthError` se le credenziali sono errate, `ForbiddenError` se
    l'identità è valida ma non è collegata a un merchant (es. un account rimasto senza negozio).
    """
    keys = login_throttle_keys(email, client_ip)
    throttle.check(keys, now)
    try:
        token = provider.sign_in_password(email, password)
    except AuthError:
        throttle.record_failure(keys, now)
        raise
    throttle.clear(keys[0])
    identity = provider.verify_token(token)
    if identity is None or merchant_crud.get_merchant_by_auth_user_id(session, identity.user_id) is None:
        raise ForbiddenError("Account non registrato come esercente")
    return token


def change_own_password(provider: AuthProvider, merchant: Merchant, current_password: object, new_password: object) -> str:
    """
    Cambio password del merchant dalle impostazioni. Ritorna il token riemesso (nuovo `ver`) da rimettere nel
    cookie. `InvalidInputError` se la nuova password non è di 8-128 caratteri o se il provider non gestisce le
    password (`dev`, `supabase`), `AuthError` se la password attuale è errata.
    """
    if not isinstance(provider, PasswordAdminProvider) or not merchant.auth_user_id:
        raise InvalidInputError("Il cambio password non è disponibile per questo account")
    return provider.change_password(merchant.auth_user_id, current_password, new_password)


def update_own_settings(session: Session, merchant: Merchant, changes: dict) -> Merchant:
    """
    Applica le modifiche del merchant a se stesso. `conversion_value_eur` (euro) viene
    convertito in `conversion_value_cents`; i campi non indicati restano invariati.
    Un `business_name` nuovo è ripulito e validato (solleva `InvalidInputError` se vuoto o oltre 80 caratteri).
    """
    changes = dict(changes)
    if changes.get("business_name") is not None:
        changes["business_name"] = validate_business_name(changes["business_name"])
    if "conversion_value_eur" in changes:
        changes["conversion_value_cents"] = euro_to_cents(changes.pop("conversion_value_eur"))
    return merchant_crud.update_merchant(session, merchant, changes)


def update_merchant_as_admin(session: Session, merchant: Merchant, changes: dict) -> Merchant:
    """
    Applica le modifiche dell'admin. Se toccano le soglie dei livelli (anche `None` per tornare
    al default) verifica la coerenza finale con i default di piattaforma prima di salvare:
    solleva `InvalidThresholdsError` se bronzo < argento < oro non regge.
    """
    overrides = {k: changes[k] for k in _THRESHOLD_FIELDS if k in changes}
    if overrides:
        tree_service.effective_thresholds(merchant, overrides)
    return merchant_crud.update_merchant(session, merchant, changes)


# --- Shell: onboarding Instagram ---

_INSTAGRAM_FIELDS = (  # tutto ciò che lo scollegamento cancella
    "zernio_api_key_enc", "zernio_account_id", "zernio_profile_id", "zernio_team_id", "instagram_username",
    "webhook_hook_id", "webhook_secret_enc", "zernio_webhook_id", "standby_detected_at", "standby_owner_app_id",
)


def _key_failure(error: "zernio_service.ZernioError") -> DomainError:
    """
    Errore di dominio per una chiamata fatta con la chiave del merchant: chiave rifiutata → 400
    «Chiave Zernio non valida», chiave mancante → 400, ogni altro errore → `ExternalServiceError` (502).
    """
    if error.kind == zernio_service.ZernioErrorKind.AUTH:
        return InvalidInputError("Chiave Zernio non valida")
    if error.kind == zernio_service.ZernioErrorKind.NOT_CONFIGURED:
        return InvalidInputError("Incolla prima la chiave Zernio")
    return ExternalServiceError(f"Operazione non riuscita: {error}")


def _has_instagram_configuration(merchant: Merchant) -> bool:
    """`True` se il negozio ha già qualcosa di Zernio da scollegare (chiave, account, webhook)."""
    return any((
        merchant.zernio_api_key_enc, merchant.zernio_account_id, merchant.webhook_hook_id, merchant.zernio_webhook_id,
    ))


def _clear_instagram_configuration(merchant: Merchant) -> None:
    """Azzera in memoria i campi Zernio e riporta lo stato a `NOT_CONNECTED` (chi chiama fa il commit)."""
    for name in _INSTAGRAM_FIELDS:
        setattr(merchant, name, None)
    merchant.instagram_status = InstagramStatus.NOT_CONNECTED
    merchant.persistent_menu_set = False


async def _delete_webhook_quietly(
    http: httpx.AsyncClient, creds: "zernio_service.ZernioCredentials", webhook_id: str, merchant_id: int,
) -> None:
    """Un solo tentativo di eliminare il webhook su Zernio: se fallisce si logga (tipo dell'errore) e si prosegue."""
    try:
        await zernio_service.delete_webhook(http, creds, webhook_id)
    except zernio_service.ZernioError as error:
        logger.warning("Webhook non rimosso su Zernio negozio=%s (%s)", merchant_id, error.kind.value)


async def _remove_remote_webhook(http: httpx.AsyncClient, merchant: Merchant) -> None:
    """Rimuove da Zernio il webhook del negozio, se c'è, con la sua chiave; mai un errore verso l'alto."""
    if not merchant.zernio_webhook_id:
        return
    try:
        creds = zernio_service.zernio_credentials_for(merchant, require_account=False)
    except zernio_service.ZernioError:
        logger.warning("Webhook non rimosso su Zernio negozio=%s (credenziali illeggibili)", merchant.id)
        return
    await _delete_webhook_quietly(http, creds, merchant.zernio_webhook_id, merchant.id)


async def save_zernio_key(
    session: Session, http: httpx.AsyncClient, merchant: Merchant, api_key: object,
) -> list["zernio_service.ZernioAccount"]:
    """
    Passo 1 dell'onboarding: valida la chiave con una chiamata reale (`GET /v1/accounts`), la salva cifrata con
    `zernio_team_id` e ritorna gli account Instagram tra cui scegliere. Prima valida la nuova chiave: solo se è
    buona scollega l'eventuale configurazione precedente (webhook rimosso con la vecchia chiave, campi azzerati),
    così una chiave sbagliata non cancella un collegamento funzionante.
    Solleva `InvalidInputError` (chiave vuota o malformata senza chiamare Zernio, chiave rifiutata, nessun account
    Instagram collegato) o `ExternalServiceError` (Zernio non risponde).
    """
    key = validate_zernio_key(api_key)
    creds = zernio_service.credentials_from_key(key)
    try:
        accounts = await zernio_service.list_instagram_accounts(http, creds)
    except zernio_service.ZernioError as error:
        raise _key_failure(error) from None
    if not accounts:
        raise InvalidInputError(
            "Questa chiave non ha nessun account Instagram collegato: su Zernio collega il tuo Instagram "
            "(Business o Creator), poi riprova"
        )
    team_id = await zernio_service.get_team_identity(http, creds)

    if _has_instagram_configuration(merchant):
        await _remove_remote_webhook(http, merchant)
        _clear_instagram_configuration(merchant)
    merchant.zernio_api_key_enc = crypto.encrypt_secret(key)
    merchant.zernio_team_id = team_id
    session.add(merchant)
    session.commit()
    session.refresh(merchant)
    return accounts


async def list_zernio_accounts(http: httpx.AsyncClient, merchant: Merchant) -> list["zernio_service.ZernioAccount"]:
    """Account Instagram collegati alla chiave già salvata (la pagina li ricarica senza richiedere la chiave)."""
    try:
        creds = zernio_service.zernio_credentials_for(merchant, require_account=False)
        return await zernio_service.list_instagram_accounts(http, creds)
    except zernio_service.ZernioError as error:
        raise _key_failure(error) from None


async def _ensure_card_menu(http: httpx.AsyncClient, creds: "zernio_service.ZernioCredentials", merchant_id: int) -> bool:
    """
    Imposta la voce "🌳 La mia carta" solo se il menu è vuoto. Ritorna `True` se la nostra voce c'è
    (impostata ora o già presente), `False` se il menu è di altri o la chiamata è fallita: il menu non è
    essenziale (la parola chiave funziona comunque), quindi un errore si logga e non blocca il collegamento.
    """
    try:
        state = classify_persistent_menu(await zernio_service.get_persistent_menu(http, creds))
        if state == MenuState.EMPTY:
            await zernio_service.set_persistent_menu(http, creds, MENU_ITEM_TITLE, CARD_POSTBACK_PAYLOAD)
            return True
        return state == MenuState.OURS
    except zernio_service.ZernioError as error:
        logger.warning("Menu persistente non impostato negozio=%s (%s)", merchant_id, error.kind.value)
        return False


async def connect_instagram_account(
    session: Session, http: httpx.AsyncClient, merchant: Merchant, account_id: object,
) -> Merchant:
    """
    Passo 2 dell'onboarding: collega l'account Instagram scelto. Controlli prima di ogni scrittura su Zernio:
    `PUBLIC_BASE_URL` https, nessun collegamento già attivo (409: prima «Scollega»), account tra quelli della
    chiave (404) e non di un altro negozio (409). Poi registra il webhook (id opaco nel path e secret generati
    qui), imposta il menu se vuoto e salva tutto insieme con lo stato `AWAITING_TEST_DM`. Se il webhook non si
    registra non si salva nulla (`ExternalServiceError`); un errore sul menu non blocca.
    Solleva `InvalidInputError`, `NotFoundError`, `ConflictError`, `ExternalServiceError`.
    """
    account_id = account_id.strip() if isinstance(account_id, str) else ""
    if not account_id:
        raise InvalidInputError("Scegli l'account Instagram da collegare")
    hook_id = secrets.token_urlsafe(24)
    url = webhook_url_for(settings.PUBLIC_BASE_URL, hook_id)  # https prima di ogni chiamata a Zernio
    if merchant.webhook_hook_id:
        raise ConflictError("Instagram è già collegato: scollegalo prima di collegare un altro account")

    try:
        creds = zernio_service.zernio_credentials_for(merchant, require_account=False)
        accounts = await zernio_service.list_instagram_accounts(http, creds)
    except zernio_service.ZernioError as error:
        raise _key_failure(error) from None
    account = next((a for a in accounts if a.id == account_id), None)
    if account is None:
        raise NotFoundError("Account Instagram non trovato tra quelli collegati a Zernio")
    owner = merchant_crud.get_merchant_by_zernio_account_id(session, account.id)
    if owner is not None and owner.id != merchant.id:
        raise ConflictError("Questo account Instagram è già collegato a un altro negozio")

    merchant_id = merchant.id
    creds = creds.model_copy(update={
        "account_id": account.id,
        "profile_id": account.profile_id,
        "quota_scope": zernio_service.quota_scope_for(merchant.zernio_team_id, account.id),
    })
    secret = secrets.token_urlsafe(32)
    try:
        webhook_id = await zernio_service.register_webhook(http, creds, url, secret)
    except zernio_service.ZernioError as error:
        raise ExternalServiceError(f"Operazione non riuscita: {error}") from None
    menu_set = await _ensure_card_menu(http, creds, merchant_id)

    # solo ora, a Zernio configurato, si tocca il merchant: un errore prima non lascia nulla di salvato
    merchant.zernio_account_id = account.id
    merchant.zernio_profile_id = account.profile_id
    merchant.instagram_username = account.username
    merchant.webhook_hook_id = hook_id
    merchant.webhook_secret_enc = crypto.encrypt_secret(secret)
    merchant.zernio_webhook_id = webhook_id
    merchant.persistent_menu_set = menu_set
    merchant.standby_detected_at = None
    merchant.standby_owner_app_id = None
    merchant.instagram_status = InstagramStatus.AWAITING_TEST_DM
    session.add(merchant)
    try:
        session.commit()
    except IntegrityError:  # un altro negozio ha preso lo stesso account nel frattempo
        session.rollback()
        await _delete_webhook_quietly(http, creds, webhook_id, merchant_id)
        raise ConflictError("Questo account Instagram è già collegato a un altro negozio") from None
    session.refresh(merchant)
    return merchant


async def disconnect_instagram(session: Session, http: httpx.AsyncClient, merchant: Merchant) -> Merchant:
    """
    «Scollega»: prova a rimuovere il webhook da Zernio (un solo tentativo; l'errore si logga) e cancella comunque
    chiave, secret e tutti i campi Zernio, stato `NOT_CONNECTED`. Le carte restano. Senza configurazione non
    chiama Zernio.
    """
    await _remove_remote_webhook(http, merchant)
    _clear_instagram_configuration(merchant)
    session.add(merchant)
    session.commit()
    session.refresh(merchant)
    return merchant


def read_instagram_panel(session: Session, merchant: Merchant, now: datetime) -> InstagramPanel:
    """
    Pannello Instagram del negozio (nessuna chiamata a Zernio). La chiave si mostra mascherata (`…1234`),
    ricavata da `zernio_credentials_for`; gli invii del mese si leggono con lo stesso ambito di quota e lo stesso
    mese UTC con cui li conta il webhook.
    """
    key_masked = None
    if merchant.zernio_api_key_enc:
        try:
            key = zernio_service.zernio_credentials_for(merchant, require_account=False).api_key.get_secret_value()
            key_masked = crypto.mask_secret(key)
        except zernio_service.ZernioError:
            key_masked = None  # chiave illeggibile: lo stato dice il resto, niente da mostrare
    sent = 0
    if merchant.zernio_account_id:
        scope = zernio_service.quota_scope_for(merchant.zernio_team_id, merchant.zernio_account_id)
        counter = session.get(ZernioSendCounter, (scope, now.astimezone(timezone.utc).strftime("%Y-%m")))
        sent = counter.sent if counter else 0
    fields = InstagramPanelInput(
        status=merchant.instagram_status,
        username=merchant.instagram_username,
        account_connected=bool(merchant.zernio_account_id),
        key_saved=bool(merchant.zernio_api_key_enc),
        key_masked=key_masked,
        persistent_menu_set=merchant.persistent_menu_set,
        standby_detected_at=merchant.standby_detected_at,
    )
    return instagram_panel(
        fields, sent, now,
        keyword=settings.INSTAGRAM_CARD_KEYWORD,
        send_limit=settings.ZERNIO_MONTHLY_SEND_LIMIT,
        warn_percent=settings.ZERNIO_SEND_WARN_PERCENT,
    )
