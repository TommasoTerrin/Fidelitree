"""
Logica di business degli esercenti: registrazione, login, impostazioni e gestione admin.

Regole di business
------------------
- Il merchant si registra con email + password tramite il provider di autenticazione: la tabella `merchant`
  non ha nessuna password, solo `auth_user_id` ed email (con il provider `local` l'hash sta in `AuthCredential`).
- Il login ha un freno ai tentativi (5 errori in 15 minuti per email → 429, avviso dal 3° errore, vedi `auth.LoginThrottle`);
  il merchant cambia la password dalle impostazioni, il reset lo fa il founder dalla dashboard con una password
  temporanea (`reset_merchant_password`), che azzera anche il freno di quell'email.
- Un merchant appena registrato è `is_approved=False` (**in attesa**): può collegare Instagram e fare il DM di
  prova, ma i clienti nuovi vedono la carta di prova e lo scanner può solo togliere saldo. Dopo l'approvazione
  manuale del founder è **attivo**; può essere messo **in pausa** (`is_paused`). Stato e permessi:
  `card_service.service_state` e `check_balance_change`.
- Il merchant può modificare solo nome, telefono e impostazioni di conversione; approvazione,
  tipo e soglie dei livelli le decide l'admin (con soglie sempre coerenti: bronzo < argento < oro).

Dashboard admin (ticket 13)
---------------------------
- Il founder entra in `/admin` con `ADMIN_SECRET_KEY` (`login_admin`: freno condiviso con il login dei merchant,
  chiave fissa `admin`, 5 errori in 15 minuti → 429) e dalla lista dei merchant (`list_admin_merchants`) li avvia
  (`approve`: imposta `is_approved` e toglie la pausa), li mette in pausa (`pause`, solo se approvati), li riattiva
  (`resume`, solo se approvati) e reimposta la password (`reset_merchant_password`: password temporanea casuale,
  mostrata una sola volta, mai salvata in chiaro né loggata). Il founder non crea né elimina profili da lì.

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
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Optional

from pydantic import BaseModel

from app.core.auth import (  # noqa: F401  (MIN_PASSWORD_LENGTH: nome storico)
    LOGIN_FAILURE_WINDOW, LOGIN_MAX_FAILURES, LOGIN_WARN_AFTER, MIN_PASSWORD_LENGTH, admin_key_matches, validate_password,
)
from app.core.enums import InstagramStatus, ServiceState
from app.core.errors import ConflictError, InvalidInputError
from app.services.card_service import service_state
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


# --- Core puro: dashboard admin ---

ADMIN_THROTTLE_KEY = "admin"  # chiave fissa del freno del login admin (una sola password per tutti)
ADMIN_LOCK_SUFFIX = "oppure accedi con l'header X-Admin-Key"  # chiude il messaggio 429 del login admin
ADMIN_LIST_LIMIT = 200  # righe della lista: con ~100 merchant basta, nessuna paginazione
TEMP_PASSWORD_LENGTH = 12
# Senza caratteri ambigui (0/O, 1/l/I): la password si comunica a voce o per messaggio.
TEMP_PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"


def admin_login_failure_message(failures: int) -> str:
    """
    Messaggio di un login admin fallito, dato il numero di errori recenti (quello appena avvenuto compreso):
    dal 3° avvisa del blocco, al 5° dice che l'accesso si è fermato. Non nomina il founder (è lui che accede).
    """
    window = int(LOGIN_FAILURE_WINDOW.total_seconds() // 60)
    if failures >= LOGIN_MAX_FAILURES:
        return f"Password non valida. Accesso sospeso per {window} minuti"
    if failures >= LOGIN_WARN_AFTER:
        return f"Password non valida. Attenzione: dopo {LOGIN_MAX_FAILURES} errori l'accesso si ferma per {window} minuti"
    return "Password non valida"


def generate_temporary_password(choice: Callable[[str], str] = secrets.choice) -> str:
    """
    Password temporanea di 12 caratteri dell'alfabeto senza caratteri ambigui (~69 bit). Ogni carattere lo
    sceglie `choice` (di default `secrets.choice`, casuale crittografico): nei test si inietta una funzione
    deterministica. Rispetta sempre le regole di `validate_password` (8-128 caratteri).
    """
    return "".join(choice(TEMP_PASSWORD_ALPHABET) for _ in range(TEMP_PASSWORD_LENGTH))


class AdminAction(str, Enum):
    """Azioni della dashboard sullo stato del servizio di un merchant."""
    APPROVE = "approve"  # avvia: approva e toglie la pausa
    PAUSE = "pause"      # metti in pausa (prova finita, abbonamento non pagato)
    RESUME = "resume"    # riattiva dalla pausa


def apply_admin_action(action: AdminAction, is_approved: bool, is_paused: bool) -> tuple[bool, bool]:
    """
    Nuovo `(is_approved, is_paused)` dopo l'azione. `APPROVE` approva e toglie la pausa (da ogni stato);
    `PAUSE` e `RESUME` valgono solo per un negozio già approvato (la pausa non conta su un negozio in attesa):
    su uno in attesa solleva `ConflictError` (409). Ripetere un'azione già applicata non cambia nulla.
    """
    if action is AdminAction.APPROVE:
        return True, False
    if not is_approved:
        verb = "metterlo in pausa" if action is AdminAction.PAUSE else "riattivarlo"
        raise ConflictError(f"Il negozio è in attesa di approvazione: avvialo prima di {verb}")
    return True, action is AdminAction.PAUSE


class AdminMerchantRow(BaseModel):
    """
    Riga della lista admin. Solo dati che il founder deve vedere: **mai** chiave Zernio, secret del webhook,
    `hook_id`, hash della password o id del provider. `can_reset_password` dice se il negozio ha una credenziale.
    """

    id: int
    business_name: str
    email: str
    contact_phone: Optional[str] = None
    created_at: datetime
    service_state: ServiceState
    instagram_status: InstagramStatus
    instagram_username: Optional[str] = None
    cards_count: int
    month_points: int
    can_reset_password: bool


def admin_row(merchant, cards_count: int, month_points: int) -> AdminMerchantRow:
    """
    Riga della lista admin di un merchant (`Merchant` o qualunque oggetto con gli stessi attributi). Funzione pura:
    conteggi e punti del mese arrivano già calcolati. `created_at` senza fuso (SQLite) vale UTC.
    """
    return AdminMerchantRow(
        id=merchant.id,
        business_name=merchant.business_name,
        email=merchant.email,
        contact_phone=merchant.contact_phone,
        created_at=_as_utc(merchant.created_at),
        service_state=service_state(merchant.is_approved, merchant.is_paused),
        instagram_status=merchant.instagram_status,
        instagram_username=merchant.instagram_username,
        cards_count=cards_count,
        month_points=month_points,
        can_reset_password=bool(merchant.auth_user_id),
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

import httpx  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app.core import crypto  # noqa: E402
from app.core.auth import AuthProvider, PasswordAdminProvider, login_failure_message, login_throttle, login_throttle_key  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.errors import (  # noqa: E402
    AuthError, DomainError, ExternalServiceError, ForbiddenError, NotFoundError,
)
from app.core.money import euro_to_cents  # noqa: E402
from app.core.security import create_admin_session_token  # noqa: E402
from app.models.models import Merchant, ZernioSendCounter  # noqa: E402
from app.services import tree_service, zernio_service  # noqa: E402
from app.services.db_crud import card_crud, merchant_crud  # noqa: E402
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
    now: datetime,
    throttle=login_throttle,
) -> str:
    """
    Verifica email+password col provider e ritorna il token di sessione, con il freno ai tentativi:
    il controllo è PRIMA di ogni verifica (a soglia anche la password giusta riceve 429), ogni errore di
    credenziali (anche email sconosciuta) conta sull'email e dal 3° errore il messaggio avvisa del blocco;
    un accesso riuscito azzera il contatore.
    Solleva `TooManyAttemptsError` (429), `AuthError` se le credenziali sono errate, `ForbiddenError` se
    l'identità è valida ma non è collegata a un merchant (es. un account rimasto senza negozio).
    """
    key = login_throttle_key(email)
    throttle.check(key, now)
    try:
        token = provider.sign_in_password(email, password)
    except AuthError as error:
        failures = throttle.record_failure(key, now)
        raise AuthError(login_failure_message(failures)) from error
    throttle.clear(key)
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


# --- Shell: dashboard admin ---

def login_admin(password: object, *, now: datetime, throttle=login_throttle) -> str:
    """
    Accesso alla dashboard con `ADMIN_SECRET_KEY` (confronto in tempo costante, `admin_key_matches`). Ritorna il
    token di sessione admin (12 ore). Stesso freno del login dei merchant con chiave fissa `admin`: il controllo
    precede la verifica (a soglia anche la password giusta riceve 429), ogni errore conta, il successo azzera.
    Solleva `TooManyAttemptsError` (429) e `AuthError` (401); la password non finisce mai in messaggi o log.
    """
    throttle.check(ADMIN_THROTTLE_KEY, now, ADMIN_LOCK_SUFFIX)
    if not admin_key_matches(password, settings.ADMIN_SECRET_KEY):
        failures = throttle.record_failure(ADMIN_THROTTLE_KEY, now)
        raise AuthError(admin_login_failure_message(failures))
    throttle.clear(ADMIN_THROTTLE_KEY)
    return create_admin_session_token()


def get_merchant_for_admin(session: Session, merchant_id: int) -> Merchant:
    """Il merchant per id; `NotFoundError` (404) se non esiste."""
    merchant = merchant_crud.get_merchant_by_id(session, merchant_id)
    if merchant is None:
        raise NotFoundError("Merchant non trovato")
    return merchant


def _admin_rows(session: Session, merchants: list[Merchant], now: datetime) -> list[AdminMerchantRow]:
    """Righe admin per i merchant dati: carte e punti del mese UTC con due sole query raggruppate."""
    ids = [m.id for m in merchants]
    cards = card_crud.count_cards_by_merchant(session, ids)
    points = tree_service.pool_points_by_merchant(session, ids, tree_service.period_for(now))
    return [admin_row(m, cards.get(m.id, 0), points.get(m.id, 0)) for m in merchants]


def list_admin_merchants(session: Session, now: datetime) -> list[AdminMerchantRow]:
    """Lista della dashboard: i merchant dal più recente (al massimo 200), con stato, carte e punti del mese."""
    return _admin_rows(session, merchant_crud.get_newest_merchants(session, ADMIN_LIST_LIMIT), now)


def admin_row_for(session: Session, merchant: Merchant, now: datetime) -> AdminMerchantRow:
    """Riga admin di un solo merchant (risposta delle azioni, così la pagina aggiorna la riga)."""
    return _admin_rows(session, [merchant], now)[0]


def set_merchant_state(session: Session, merchant: Merchant, action: AdminAction) -> Merchant:
    """
    Applica un'azione della dashboard (`apply_admin_action`): salva `is_approved` e `is_paused` solo se
    cambiano. `ConflictError` per pausa o riattivazione di un negozio in attesa.
    """
    is_approved, is_paused = apply_admin_action(action, merchant.is_approved, merchant.is_paused)
    if (is_approved, is_paused) == (merchant.is_approved, merchant.is_paused):
        return merchant
    return merchant_crud.update_merchant(session, merchant, {"is_approved": is_approved, "is_paused": is_paused})


def approve_merchant(session: Session, merchant: Merchant) -> Merchant:
    """Approva un merchant e ne toglie la pausa (stessa azione «Avvia» della dashboard e dell'API admin)."""
    return set_merchant_state(session, merchant, AdminAction.APPROVE)


def reset_merchant_password(
    provider: AuthProvider,
    merchant: Merchant,
    *,
    throttle=login_throttle,
    choice: Callable[[str], str] = secrets.choice,
) -> str:
    """
    Reset da parte del founder: genera una password temporanea, la imposta col provider (`set_password`: le sessioni
    aperte del merchant decadono) e ne azzera il freno del login, altrimenti chi si è bloccato (il 429 gli dice di
    chiedere il reset) non potrebbe usarla per 15 minuti. Ritorna la password: l'unico posto dove esiste in chiaro
    è la risposta; non si salva né si logga. `InvalidInputError` (400) se il provider non gestisce le password,
    `ConflictError` (409) se il negozio non ha una credenziale (creato dall'API admin).
    """
    if not isinstance(provider, PasswordAdminProvider):
        raise InvalidInputError("Il reset della password non è disponibile con questo provider di accesso")
    no_credential = "Questo negozio non ha una credenziale (creato dall'API admin): non può accedere né reimpostare la password"
    if not merchant.auth_user_id:
        raise ConflictError(no_credential)
    temporary = generate_temporary_password(choice)
    try:
        provider.set_password(merchant.auth_user_id, temporary)
    except NotFoundError:
        raise ConflictError(no_credential) from None
    throttle.clear(login_throttle_key(merchant.email))
    return temporary


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
