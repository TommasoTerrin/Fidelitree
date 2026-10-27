# app/core/dependencies.py
# Dipendenze condivise (session DB, autenticazione corrente, ecc.)
from typing import Optional
from sqlmodel import Session
from fastapi import Request, Response, HTTPException, Depends, Header
from app.core.auth import AuthIdentity, admin_key_matches, get_auth_provider
from app.core.config import settings
from app.core.security import ADMIN_SESSION_HOURS, is_admin_session_token, request_origin_allowed

def get_session():
    """Genera una sessione DB da iniettare con Depends()."""
    # Importiamo engine qui per evitare import circolari
    from app.main import engine
    with Session(engine) as session:
        yield session

def _extract_token(request: Request) -> Optional[str]:
    """Token di sessione dal cookie `access_token` o dall'header `Authorization: Bearer`, se presente."""
    token = request.cookies.get("access_token")
    if not token:
        scheme, _, value = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            token = value.strip()
    return token or None

def get_auth_identity(request: Request) -> AuthIdentity:
    """
    Identità verificata dal provider: il token arriva dal cookie `access_token`
    o dall'header `Authorization: Bearer`. 401 se assente o invalido.
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato")

    identity = get_auth_provider().verify_token(token)
    if identity is None:
        raise HTTPException(status_code=401, detail="Token non valido o scaduto")
    return identity

def get_optional_identity(request: Request) -> Optional[AuthIdentity]:
    """Come `get_auth_identity` ma senza errori: `None` se il token manca o non è valido (pagine HTML)."""
    token = _extract_token(request)
    return get_auth_provider().verify_token(token) if token else None

def get_current_merchant(
    identity: AuthIdentity = Depends(get_auth_identity),
    session: Session = Depends(get_session),
):
    """Merchant collegato all'identità (`auth_user_id`); 403 se l'account non è un esercente."""
    from app.services.db_crud import merchant_crud
    merchant = merchant_crud.get_merchant_by_auth_user_id(session, identity.user_id)
    if not merchant:
        raise HTTPException(status_code=403, detail="Account non registrato come esercente")
    return merchant

def get_optional_merchant(
    identity: Optional[AuthIdentity] = Depends(get_optional_identity),
    session: Session = Depends(get_session),
):
    """
    Come `get_current_merchant` ma senza errori: `None` se non c'è una sessione valida o l'identità non è di
    un esercente (es. il cookie di un vecchio account non esercente). Serve alle pagine HTML merchant, che in quel caso
    rimandano al login invece di mostrare un JSON di errore.
    """
    from app.services.db_crud import merchant_crud
    return merchant_crud.get_merchant_by_auth_user_id(session, identity.user_id) if identity else None

def set_session_cookie(response: Response, token: str) -> None:
    """
    Imposta il cookie di sessione `access_token` (httponly, samesite lax, 7 giorni) del merchant;
    `secure` (solo https) con `ENVIRONMENT=production`.
    """
    response.set_cookie(
        "access_token", token, httponly=True, max_age=60*24*7*60,
        samesite="lax", secure=settings.ENVIRONMENT == "production",
    )

def require_admin_key(x_admin_key: str = Header(default=None)):
    """Protegge gli endpoint amministrativi: richiede l'header X-Admin-Key."""
    if x_admin_key != settings.ADMIN_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Non autorizzato")

ADMIN_COOKIE = "admin_session"
ADMIN_COOKIE_PATH = "/admin"

def admin_auth_method(request: Request) -> Optional[str]:
    """
    Come la richiesta si autentica come admin: `"header"` se porta un `X-Admin-Key` corretto, `"cookie"` se ha
    un cookie `admin_session` valido, `None` altrimenti. Se l'header c'è ma è errato la richiesta è rifiutata
    anche con un cookie valido (nessun ripiego silenzioso). Una chiave admin vuota non autentica mai.
    """
    header = request.headers.get("X-Admin-Key")
    if header is not None:
        return "header" if admin_key_matches(header, settings.ADMIN_SECRET_KEY) else None
    return "cookie" if is_admin_session_token(request.cookies.get(ADMIN_COOKIE)) else None

def require_admin_session(request: Request) -> str:
    """
    Protegge `/admin/api/*`: cookie di sessione admin valido **oppure** header `X-Admin-Key` corretto (per curl
    e smoke test). 401 altrimenti. Ritorna il metodo usato (`"cookie"` o `"header"`).
    """
    method = admin_auth_method(request)
    if method is None:
        raise HTTPException(status_code=401, detail="Non autenticato")
    return method

def require_same_origin(request: Request) -> None:
    """
    Difesa CSRF dei POST della dashboard: `Origin` (o `Referer`) deve essere il nostro host, 403 altrimenti.
    Si salta solo con un `X-Admin-Key` **corretto** (un browser non può mandare quell'header da un altro sito).
    """
    if admin_auth_method(request) == "header":
        return
    if not request_origin_allowed(
        request.headers.get("Origin"), request.headers.get("Referer"), request.headers.get("Host"),
    ):
        raise HTTPException(status_code=403, detail="Origine della richiesta non consentita")

def require_admin_action(request: Request) -> str:
    """Dipendenza dei POST admin con effetto: sessione admin valida (401) e origine corretta (403). Ritorna il metodo."""
    method = require_admin_session(request)
    require_same_origin(request)
    return method

def set_admin_cookie(response: Response, token: str) -> None:
    """
    Imposta il cookie `admin_session` (httponly, samesite strict, 12 ore, solo per `/admin`); `secure`
    (solo https) con `ENVIRONMENT=production`.
    """
    response.set_cookie(
        ADMIN_COOKIE, token, httponly=True, max_age=ADMIN_SESSION_HOURS * 3600, path=ADMIN_COOKIE_PATH,
        samesite="strict", secure=settings.ENVIRONMENT == "production",
    )

def clear_admin_cookie(response: Response) -> None:
    """Cancella il cookie admin: serve lo stesso `path` con cui è stato impostato, altrimenti il browser lo tiene."""
    response.delete_cookie(
        ADMIN_COOKIE, path=ADMIN_COOKIE_PATH, httponly=True, samesite="strict",
        secure=settings.ENVIRONMENT == "production",
    )
