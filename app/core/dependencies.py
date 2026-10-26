# app/core/dependencies.py
# Dipendenze condivise (session DB, autenticazione corrente, ecc.)
from typing import Optional
from sqlmodel import Session
from fastapi import Request, Response, HTTPException, Depends, Header
from app.core.auth import AuthIdentity, get_auth_provider
from app.core.config import settings

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
    un esercente (es. il cookie di un vecchio cliente). Serve alle pagine HTML merchant, che in quel caso
    rimandano al login invece di mostrare un JSON di errore.
    """
    from app.services.db_crud import merchant_crud
    return merchant_crud.get_merchant_by_auth_user_id(session, identity.user_id) if identity else None

def get_current_customer(
    identity: AuthIdentity = Depends(get_auth_identity),
    session: Session = Depends(get_session),
):
    """Cliente collegato all'identità (`auth_user_id`); al primo accesso viene creato."""
    from app.services import customer_service
    return customer_service.get_or_create_customer(session, identity)

def get_optional_customer(
    identity: Optional[AuthIdentity] = Depends(get_optional_identity),
    session: Session = Depends(get_session),
):
    """Come `get_current_customer` ma ritorna `None` se non c'è una sessione valida (pagine HTML)."""
    from app.services import customer_service
    return customer_service.get_or_create_customer(session, identity) if identity else None

def set_session_cookie(response: Response, token: str) -> None:
    """Imposta il cookie di sessione `access_token` (httponly, 7 giorni), uguale per merchant e clienti."""
    response.set_cookie("access_token", token, httponly=True, max_age=60*24*7*60)

def require_admin_key(x_admin_key: str = Header(default=None)):
    """Protegge gli endpoint amministrativi: richiede l'header X-Admin-Key."""
    if x_admin_key != settings.ADMIN_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Non autorizzato")
