"""
Logica di business degli esercenti: registrazione, login, impostazioni e gestione admin.

Regole di business
------------------
- Il merchant si registra con email + password tramite il provider di autenticazione:
  nel nostro DB non si salva nessuna password, solo `auth_user_id` ed email.
- Un merchant appena registrato **lavora subito** (scan, tree points) ma è `is_approved=False`:
  il suo pool conta per la piantumazione solo dopo l'approvazione manuale del founder.
- Il merchant può modificare solo nome, telefono e impostazioni di conversione; approvazione,
  tipo e soglie dei livelli le decide l'admin (con soglie sempre coerenti: bronzo < argento < oro).

Il core (`validate_registration`) usa solo Pydantic e stdlib e solleva errori di dominio.
La sezione `# --- Shell ---` in fondo parla con DB e provider di autenticazione.
"""

import re
from typing import Optional

from pydantic import BaseModel

from app.core.errors import InvalidInputError

# --- Core puro ---

MIN_PASSWORD_LENGTH = 8

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+39\d{9,10}$")  # stessa regola del modello Merchant


# Il nome è il titolo della card Instagram: stesso valore di `instagram_service.CARD_TITLE_MAX`
# (non importato per non legare i due moduli; un test li tiene allineati).
MAX_BUSINESS_NAME_LENGTH = 80


def validate_business_name(business_name: Optional[str]) -> str:
    """
    Ripulisce il nome dell'attività dagli spazi e lo valida: obbligatorio e al massimo 80 caratteri,
    così la card del negozio è sempre costruibile. Solleva `InvalidInputError` in italiano.
    """
    name = (business_name or "").strip()
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
    business_name: str,
    email: str,
    password: str,
    contact_phone: Optional[str] = None,
) -> RegistrationData:
    """
    Valida e normalizza i dati di registrazione di un merchant.
    Nome e email vengono ripuliti dagli spazi (email anche in minuscolo); il telefono è
    facoltativo (`None` o stringa vuota = assente) e, se presente, deve essere `+39` + 9-10 cifre.
    Solleva `InvalidInputError` con un messaggio in italiano per il primo campo non valido.
    """
    name = validate_business_name(business_name)

    normalized_email = (email or "").strip().lower()
    if not _EMAIL_RE.match(normalized_email):
        raise InvalidInputError("Email non valida")

    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise InvalidInputError(f"La password deve avere almeno {MIN_PASSWORD_LENGTH} caratteri")

    phone = (contact_phone or "").strip() or None
    if phone is not None and not _PHONE_RE.match(phone):
        raise InvalidInputError("Il telefono deve avere prefisso +39 seguito da 9 o 10 cifre")

    return RegistrationData(
        business_name=name, email=normalized_email, password=password, contact_phone=phone,
    )


# --- Shell ---

from sqlmodel import Session  # noqa: E402

from app.core.auth import AuthProvider  # noqa: E402
from app.core.errors import AuthError, ConflictError, ForbiddenError  # noqa: E402
from app.core.money import euro_to_cents  # noqa: E402
from app.models.models import Merchant  # noqa: E402
from app.services import tree_service  # noqa: E402
from app.services.db_crud import merchant_crud  # noqa: E402

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

    merchant = merchant_crud.create_merchant(session, {
        "business_name": data.business_name,
        "email": data.email,
        "contact_phone": data.contact_phone,
        "type": "free",
        "is_approved": False,
        "auth_user_id": identity.user_id,
    })
    return merchant, provider.sign_in_password(data.email, data.password)


def login_merchant(session: Session, provider: AuthProvider, email: str, password: str) -> str:
    """
    Verifica email+password col provider e ritorna il token di sessione.
    Solleva `AuthError` se le credenziali sono errate, `ForbiddenError` se l'identità
    è valida ma non è collegata a un merchant (es. un cliente).
    """
    token = provider.sign_in_password(email, password)
    identity = provider.verify_token(token)
    if identity is None or merchant_crud.get_merchant_by_auth_user_id(session, identity.user_id) is None:
        raise ForbiddenError("Account non registrato come esercente")
    return token


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
