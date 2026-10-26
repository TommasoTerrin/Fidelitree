"""
Interfaccia di autenticazione indipendente dal fornitore.

L'app parla solo con `AuthProvider`: oggi c'è il provider `dev` (memoria + JWT locale, solo
sviluppo/test), in un rilascio successivo `SupabaseAuthProvider`. Nel nostro DB non si salva
nessuna password: ci sono solo `auth_user_id` e email.
Questo modulo non importa fastapi.
"""

import uuid
from typing import Optional, Protocol

from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import AuthError
from app.core.security import create_jwt_token, decode_jwt_token

__all__ = [
    "AuthError", "AuthIdentity", "AuthProvider", "DevAuthProvider", "SupabaseAuthProvider",
    "dev_user_id", "get_auth_provider",
]

_DEV_NAMESPACE = uuid.UUID("6f1d2c1e-5b7a-4e0b-9a43-0c1f7f0d2e11")


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


def _normalize(email: str) -> str:
    """Email in minuscolo e senza spazi ai lati."""
    return email.strip().lower()


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


_instances: dict[str, AuthProvider] = {}


def get_auth_provider() -> AuthProvider:
    """
    Provider scelto da `settings.AUTH_PROVIDER` (un'istanza per processo).
    Solleva `RuntimeError` se è `dev` con `ENVIRONMENT=production`: l'app non deve partire.
    """
    name = settings.AUTH_PROVIDER
    if name == "dev" and settings.ENVIRONMENT == "production":
        raise RuntimeError("AUTH_PROVIDER=dev non è ammesso con ENVIRONMENT=production")
    if name not in _instances:
        _instances[name] = DevAuthProvider() if name == "dev" else SupabaseAuthProvider()
    return _instances[name]
