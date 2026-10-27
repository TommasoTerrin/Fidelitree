"""
Interfaccia di autenticazione indipendente dal fornitore.

L'app parla solo con `AuthProvider`. Provider disponibili:
- `dev` (memoria + JWT locale, solo sviluppo/test, rifiutato con `ENVIRONMENT=production`);
- `local` (pilota): email+password con hash `scrypt` nella tabella `AuthCredential` del nostro DB, separata dai
  dati del negozio, e sessione JWT con `ver` = `token_version` (un reset o un cambio password invalida le sessioni);
- `supabase`: stub, in un rilascio successivo.

Il modulo è diviso come i service: `# --- Core puro ---` (hash delle password, regole sulla password, logica del
freno ai tentativi: solo stdlib e Pydantic, il tempo arriva come argomento) e `# --- Shell ---` (provider, DB,
contatore dei tentativi in memoria). Nessuna password, hash o token finisce in log, repr, risposte o messaggi
d'errore. Questo modulo non importa fastapi.
"""

import base64
import binascii
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Callable, ContextManager, Optional, Protocol, runtime_checkable

from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import AuthError, InvalidInputError, NotFoundError, TooManyAttemptsError
from app.core.security import create_jwt_token, decode_jwt_token

__all__ = [
    "AuthError", "AuthIdentity", "AuthProvider", "DevAuthProvider", "LocalAuthProvider", "LoginThrottle",
    "PasswordAdminProvider", "SupabaseAuthProvider", "dev_user_id", "get_auth_provider", "hash_password",
    "login_throttle", "login_throttle_keys", "validate_password", "verify_password",
]

# --- Core puro ---

# Parametri di scrypt: N=2^14, r=8, p=1 (~16 MiB, qualche decina di ms) sono il valore interattivo della
# letteratura di scrypt. Il formato salvato contiene i parametri usati, quindi cambiarli in futuro non
# invalida gli hash già salvati (la verifica legge i parametri dalla stringa).
SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_SALT_BYTES = 16
SCRYPT_KEY_BYTES = 32
_SCRYPT_PREFIX = "scrypt"
# Tetti sui parametri letti da un hash salvato: un valore assurdo (DB manomesso) non deve esaurire la memoria.
_SCRYPT_MAX_N, _SCRYPT_MAX_R, _SCRYPT_MAX_P = 2 ** 20, 32, 16

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

LOGIN_MAX_FAILURES = 5                           # errori ammessi...
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)     # ...in questa finestra: al successivo → 429


def validate_password(password: object) -> str:
    """
    Controlla la lunghezza della password (8-128 caratteri) e la ritorna invariata (gli spazi contano).
    Accetta qualunque tipo: un valore che non sia testo vale come vuoto. Solleva `InvalidInputError`;
    il messaggio non riporta mai il valore ricevuto.
    """
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidInputError(f"La password deve avere almeno {MIN_PASSWORD_LENGTH} caratteri")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise InvalidInputError(f"La password può avere al massimo {MAX_PASSWORD_LENGTH} caratteri")
    try:
        password.encode("utf-8")
    except UnicodeEncodeError:  # es. un surrogato isolato arrivato da un JSON: non si può derivare la chiave
        raise InvalidInputError("La password contiene caratteri non validi") from None
    return password


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, key_bytes: int) -> bytes:
    """Deriva la chiave con `hashlib.scrypt`; `maxmem` esplicito, così un `n` più alto non fallisce per il tetto di default."""
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=key_bytes, maxmem=2 * 128 * n * r * p + 2 ** 20,
    )


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """
    Hash `scrypt` della password nel formato `scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>`. Il salt è casuale a
    ogni chiamata (`salt` si passa solo nei test). La lunghezza NON si controlla qui: vedi `validate_password`.
    """
    salt = secrets.token_bytes(SCRYPT_SALT_BYTES) if salt is None else salt
    derived = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_KEY_BYTES)
    return "$".join((
        _SCRYPT_PREFIX, str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P),
        base64.b64encode(salt).decode("ascii"), base64.b64encode(derived).decode("ascii"),
    ))


def verify_password(password: str, stored_hash: str) -> bool:
    """
    `True` se la password corrisponde all'hash salvato; il confronto è in tempo costante (`hmac.compare_digest`).
    Un formato malformato o con parametri fuori dai tetti vale `False`, mai un'eccezione.
    """
    try:
        prefix, n, r, p, salt_b64, hash_b64 = stored_hash.split("$")
        n, r, p = int(n), int(r), int(p)
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(hash_b64, validate=True)
        if prefix != _SCRYPT_PREFIX or not expected:
            return False
        if not (2 <= n <= _SCRYPT_MAX_N and 1 <= r <= _SCRYPT_MAX_R and 1 <= p <= _SCRYPT_MAX_P):
            return False
        derived = _scrypt(password, salt, n, r, p, len(expected))
    except (ValueError, TypeError, AttributeError, binascii.Error):
        return False
    return hmac.compare_digest(derived, expected)


def normalize_email(email: str) -> str:
    """Email in minuscolo e senza spazi ai lati (stessa regola di registrazione e login)."""
    return email.strip().lower()


def login_throttle_keys(email: str, client_ip: Optional[str]) -> tuple[str, str]:
    """
    Chiavi del freno ai tentativi: `(email:<normalizzata>, ip:<indirizzo>)`. L'email è normalizzata come fa il
    provider (maiuscole e spazi non aggirano il freno); un IP sconosciuto (`None`) vale `ip:unknown`.
    """
    return f"email:{normalize_email(email)}", f"ip:{client_ip or 'unknown'}"


def recent_failures(failures: list[datetime], now: datetime, window: timedelta = LOGIN_FAILURE_WINDOW) -> list[datetime]:
    """Gli errori ancora dentro la finestra (il più vecchio che sia ancora «recente» è a `now - window` esclusa)."""
    return [t for t in failures if now - t < window]


def login_retry_after(
    failures: list[datetime],
    now: datetime,
    *,
    max_failures: int = LOGIN_MAX_FAILURES,
    window: timedelta = LOGIN_FAILURE_WINDOW,
) -> Optional[timedelta]:
    """
    `None` se un nuovo tentativo è ammesso; altrimenti l'attesa prima che gli errori recenti scendano sotto
    `max_failures` (cioè finché non scade quello che li tiene a soglia). Il tempo arriva da `now`.
    """
    recent = sorted(recent_failures(failures, now, window))
    if len(recent) < max_failures:
        return None
    return recent[len(recent) - max_failures] + window - now


# --- Shell ---

from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.models.models import AuthCredential  # noqa: E402


class AuthIdentity(BaseModel):
    """Identità verificata da un provider: id utente del provider ed email."""
    user_id: str
    email: str


class AuthProvider(Protocol):
    """Contratto di un provider di autenticazione (token = stringa opaca per l'app)."""

    def sign_up(self, email: str, password: str) -> AuthIdentity:
        """Registra un utente con email+password e ne ritorna l'identità."""

    def sign_in_password(self, email: str, password: str) -> str:
        """Ritorna il token se le credenziali sono giuste, altrimenti solleva `AuthError`."""

    def verify_token(self, token: str) -> Optional[AuthIdentity]:
        """Ritorna l'identità del token, `None` se è invalido o scaduto."""


@runtime_checkable
class PasswordAdminProvider(Protocol):
    """
    Provider che gestisce anche le password (oggi solo `local`): reset da parte dell'admin, cambio da parte
    dell'utente e cancellazione dell'utente. Si controlla con `isinstance`: con `dev` e `supabase` non c'è.
    """

    def set_password(self, user_id: str, new_password: str) -> None:
        """Reimposta la password (reset dell'admin) e invalida le sessioni aperte."""

    def change_password(self, user_id: str, current_password: str, new_password: str) -> str:
        """Cambia la password dopo aver verificato quella attuale; ritorna il nuovo token di sessione."""

    def delete_user(self, user_id: str) -> None:
        """Elimina le credenziali dell'utente (nessun errore se non esistono)."""


def _normalize(email: str) -> str:
    """Email in minuscolo e senza spazi ai lati."""
    return normalize_email(email)


_DEV_NAMESPACE = uuid.UUID("6f1d2c1e-5b7a-4e0b-9a43-0c1f7f0d2e11")


def dev_user_id(email: str) -> str:
    """`user_id` deterministico del provider dev: stesso valore per la stessa email."""
    return str(uuid.uuid5(_DEV_NAMESPACE, _normalize(email)))


class DevAuthProvider:
    """
    Provider SOLO per sviluppo e test: utenti in memoria, password dev di fallback per gli utenti non registrati in memoria (`DEV_AUTH_PASSWORD`),
    token = JWT firmato con `JWT_SECRET_KEY` (claim `sub` e `email`).
    Lo stato vive nel processo: si azzera con `reset()` e a ogni riavvio.
    """

    def __init__(self) -> None:
        self._passwords: dict[str, str] = {}

    def reset(self) -> None:
        """Dimentica tutti gli utenti registrati (usato dai test)."""
        self._passwords.clear()

    def issue_token(self, identity: AuthIdentity) -> str:
        """Firma un token per un'identità (anche non registrata): serve al login dev transitorio."""
        return create_jwt_token({"sub": identity.user_id, "email": identity.email})

    def sign_up(self, email: str, password: str) -> AuthIdentity:
        """Registra l'utente (la password resta solo in memoria); rifiuta email già registrate."""
        email = _normalize(email)
        if email in self._passwords:
            raise AuthError("Email già registrata")
        self._passwords[email] = password
        return AuthIdentity(user_id=dev_user_id(email), email=email)

    def sign_in_password(self, email: str, password: str) -> str:
        """
        Token se la password è giusta; `AuthError` altrimenti. Un utente registrato in memoria
        vale solo con la sua password; per gli altri vale `settings.DEV_AUTH_PASSWORD` (se non
        vuota), così gli account creati dal seed accedono anche dopo un riavvio del server.
        """
        email = _normalize(email)
        expected = self._passwords.get(email, settings.DEV_AUTH_PASSWORD)
        if not expected or expected != password:
            raise AuthError("Credenziali non valide")
        return self.issue_token(AuthIdentity(user_id=dev_user_id(email), email=email))

    def verify_token(self, token: str) -> Optional[AuthIdentity]:
        """Identità del token, `None` se spazzatura, scaduto o privo di `sub`/`email`."""
        payload = decode_jwt_token(token)
        if not payload or not payload.get("sub") or not payload.get("email"):
            return None
        return AuthIdentity(user_id=str(payload["sub"]), email=payload["email"])


def _default_session_factory() -> ContextManager:
    """Sessione sul DB dell'app (`Session(engine)`); l'engine si importa qui per evitare import circolari, come `get_session`."""
    from app.main import engine
    return Session(engine)


@lru_cache()
def _dummy_hash() -> str:
    """
    Hash di una password casuale con gli stessi parametri degli hash veri: si verifica contro questo quando
    l'email non esiste, così login con email sconosciuta e con password errata impiegano tempi confrontabili.
    """
    return hash_password(secrets.token_urlsafe(16))


class LocalAuthProvider:
    """
    Provider `local`: email+password con hash `scrypt` in `AuthCredential` (stesso DB dell'app, tabella separata
    dai dati del negozio). Token = JWT con `sub` (= `Merchant.auth_user_id`), `email` e `ver` = `token_version`:
    `verify_token` controlla anche che la credenziale esista e che `ver` coincida, quindi un reset o un cambio
    password invalida le sessioni aperte. Email sconosciuta e password errata hanno lo stesso errore.

    `session_factory` ritorna un context manager che dà una `Session`; di default `Session(engine)` (import
    tardivo come `get_session`), i test ne iniettano una su SQLite in-memory.
    """

    _INVALID = "Credenziali non valide"

    def __init__(self, session_factory: Optional[Callable[[], ContextManager]] = None) -> None:
        self._session_factory = session_factory or _default_session_factory

    @staticmethod
    def _token_for(credential) -> str:
        """Firma il token di sessione per una credenziale (include `ver`)."""
        return create_jwt_token({
            "sub": credential.user_id, "email": credential.email, "ver": credential.token_version,
        })

    def sign_up(self, email: str, password: str) -> AuthIdentity:
        """
        Crea la credenziale. `InvalidInputError` se la password non è di 8-128 caratteri, `AuthError` se l'email
        esiste già (anche per una corsa tra due registrazioni: l'errore del DB non viene mai propagato né loggato,
        perché contiene i parametri dell'INSERT, hash compreso).
        """
        email = _normalize(email)
        password_hash = hash_password(validate_password(password))
        credential = AuthCredential(user_id=str(uuid.uuid4()), email=email, password_hash=password_hash)
        with self._session_factory() as session:
            if session.exec(select(AuthCredential).where(AuthCredential.email == email)).first() is not None:
                raise AuthError("Email già registrata")
            session.add(credential)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise AuthError("Email già registrata") from None
            return AuthIdentity(user_id=credential.user_id, email=credential.email)

    def sign_in_password(self, email: str, password: str) -> str:
        """
        Token se la password è giusta. Altrimenti `AuthError("Credenziali non valide")`, identico per email
        sconosciuta e password errata (con email sconosciuta si verifica comunque contro un hash fittizio).
        """
        email = _normalize(email)
        with self._session_factory() as session:
            credential = session.exec(select(AuthCredential).where(AuthCredential.email == email)).first()
            stored = credential.password_hash if credential is not None else _dummy_hash()
            length_ok = isinstance(password, str) and len(password) <= MAX_PASSWORD_LENGTH
            matches = length_ok and verify_password(password, stored)
            if credential is None or not matches:
                raise AuthError(self._INVALID)
            return self._token_for(credential)

    def verify_token(self, token: str) -> Optional[AuthIdentity]:
        """
        Identità del token; `None` se la firma è errata, è scaduto, mancano `sub`/`email`/`ver`, la credenziale
        non esiste più o `ver` non è l'attuale `token_version` (password cambiata o reimpostata).
        """
        payload = decode_jwt_token(token)
        if not payload:
            return None
        user_id, email, ver = payload.get("sub"), payload.get("email"), payload.get("ver")
        if not (isinstance(user_id, str) and user_id and isinstance(email, str) and email
                and isinstance(ver, int) and not isinstance(ver, bool)):
            return None
        with self._session_factory() as session:
            credential = session.get(AuthCredential, user_id)
            if credential is None or credential.token_version != ver:
                return None
            return AuthIdentity(user_id=credential.user_id, email=credential.email)

    def set_password(self, user_id: str, new_password: str) -> None:
        """
        Reset da parte dell'admin: nuovo hash e `token_version + 1` (le sessioni aperte smettono di valere).
        `InvalidInputError` se la nuova password non è di 8-128 caratteri, `NotFoundError` se l'utente non esiste.
        """
        new_hash = hash_password(validate_password(new_password))
        with self._session_factory() as session:
            credential = session.get(AuthCredential, user_id)
            if credential is None:
                raise NotFoundError("Utente non trovato")
            credential.password_hash = new_hash
            credential.token_version += 1
            session.add(credential)
            session.commit()

    def change_password(self, user_id: str, current_password: str, new_password: str) -> str:
        """
        Cambio da parte dell'utente: `InvalidInputError` se la nuova password non è di 8-128 caratteri,
        `AuthError` se quella attuale è errata, poi come `set_password`. Ritorna il token della sessione corrente,
        riemesso con il nuovo `ver` (le altre sessioni si chiudono).
        """
        new_hash = hash_password(validate_password(new_password))
        with self._session_factory() as session:
            credential = session.get(AuthCredential, user_id)
            current_ok = isinstance(current_password, str) and len(current_password) <= MAX_PASSWORD_LENGTH
            if credential is None or not (current_ok and verify_password(current_password, credential.password_hash)):
                raise AuthError("La password attuale non è corretta")
            credential.password_hash = new_hash
            credential.token_version += 1
            session.add(credential)
            session.commit()
            return self._token_for(credential)

    def delete_user(self, user_id: str) -> None:
        """Elimina la credenziale (idempotente): serve quando il merchant viene cancellato o la registrazione fallisce a metà."""
        with self._session_factory() as session:
            credential = session.get(AuthCredential, user_id)
            if credential is not None:
                session.delete(credential)
                session.commit()


class SupabaseAuthProvider:
    """
    STUB: il collegamento a Supabase Auth è previsto in un rilascio successivo.
    Servirà: URL del progetto, anon key e verifica dei JWT con il JWT secret di Supabase
    (nuove variabili d'ambiente da aggiungere a `Settings`).
    """

    _MSG = "Collegamento Supabase: rilascio successivo"

    def sign_up(self, email: str, password: str) -> AuthIdentity:
        raise NotImplementedError(self._MSG)

    def sign_in_password(self, email: str, password: str) -> str:
        raise NotImplementedError(self._MSG)

    def verify_token(self, token: str) -> Optional[AuthIdentity]:
        raise NotImplementedError(self._MSG)


class LoginThrottle:
    """
    Freno ai tentativi di accesso: contatore **in memoria** degli errori per chiave (email e IP, vedi
    `login_throttle_keys`). Un solo processo su DigitalOcean: basta per il pilota (non è condiviso tra processi
    e si azzera al riavvio). Le regole (soglia, finestra, attesa) sono nel core: `login_retry_after`.
    Riusabile dal login admin.
    """

    _PURGE_ABOVE = 10_000  # chiavi in memoria oltre le quali si buttano quelle senza errori recenti

    def __init__(self) -> None:
        self._failures: dict[str, list[datetime]] = {}

    def reset(self) -> None:
        """Dimentica tutti gli errori (usato dai test)."""
        self._failures.clear()

    def check(self, keys: tuple[str, ...], now: datetime) -> None:
        """Solleva `TooManyAttemptsError` (429) con l'attesa più lunga se una delle chiavi è a soglia."""
        waits = [
            wait for key in keys
            if (wait := login_retry_after(self._failures.get(key, []), now)) is not None
        ]
        if waits:
            raise TooManyAttemptsError(int(max(waits).total_seconds()) + 1)

    def record_failure(self, keys: tuple[str, ...], now: datetime) -> None:
        """Registra un errore su ogni chiave, scartando quelli fuori finestra."""
        for key in keys:
            self._failures[key] = recent_failures(self._failures.get(key, []), now) + [now]
        if len(self._failures) > self._PURGE_ABOVE:
            self._failures = {
                k: kept for k, v in self._failures.items() if (kept := recent_failures(v, now))
            }

    def clear(self, key: str) -> None:
        """Azzera una chiave (dopo un accesso riuscito si azzera solo quella dell'email, mai quella dell'IP)."""
        self._failures.pop(key, None)


login_throttle = LoginThrottle()

_instances: dict[str, AuthProvider] = {}


def get_auth_provider() -> AuthProvider:
    """
    Provider scelto da `settings.AUTH_PROVIDER` (un'istanza per processo).
    Solleva `RuntimeError` se è `dev` con `ENVIRONMENT=production`: l'app non deve partire (il lifespan lo chiama).
    `local` è ammesso in produzione.
    """
    name = settings.AUTH_PROVIDER
    if name == "dev" and settings.ENVIRONMENT == "production":
        raise RuntimeError("AUTH_PROVIDER=dev non è ammesso con ENVIRONMENT=production")
    if name not in _instances:
        _instances[name] = {
            "dev": DevAuthProvider, "local": LocalAuthProvider, "supabase": SupabaseAuthProvider,
        }[name]()
    return _instances[name]
