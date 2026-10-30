"""
Servizi di sicurezza: token JWT di sessione (merchant e admin) e controllo dell'origine delle richieste.
"""

from datetime import timedelta
from typing import Optional
from urllib.parse import urlsplit

from jose import jwt

from app.core.clock import utc_now
from app.core.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 giorni
ADMIN_SESSION_HOURS = 12                  # scadenza della sessione della dashboard admin
ADMIN_ROLE = "admin"

def create_jwt_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Crea un token JWT con una data di scadenza definita (`expires_delta`, di default 7 giorni).
    """
    to_encode = data.copy()
    expire = utc_now() + (expires_delta if expires_delta is not None else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_jwt_token(token: str) -> dict | None:
    """
    Decodifica e valida un token JWT.
    Ritorna il payload se valido, None altrimenti.
    """
    try:
        decoded_token = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
        return decoded_token
    except jwt.JWTError:
        return None

def create_admin_session_token() -> str:
    """
    Token della sessione admin: JWT firmato con `JWT_SECRET_KEY`, claim `role=admin` e scadenza di 12 ore.
    Non ha `sub` né `email`: nessun provider merchant lo accetta come sessione di un negozio.
    """
    return create_jwt_token({"role": ADMIN_ROLE}, expires_delta=timedelta(hours=ADMIN_SESSION_HOURS))

def is_admin_session_token(token: Optional[str]) -> bool:
    """
    `True` se il token è firmato, non scaduto e con `role` esattamente `admin`. Un token di sessione merchant
    (stessa chiave di firma, ma senza quel claim) non vale.
    """
    payload = decode_jwt_token(token) if token else None
    return bool(payload) and payload.get("role") == ADMIN_ROLE

# --- Core puro: controllo dell'origine ---

def request_origin_allowed(origin: Optional[str], referer: Optional[str], host: Optional[str]) -> bool:
    """
    `True` se la richiesta viene dal nostro stesso host: il netloc di `Origin` (o, se manca, di `Referer`) deve
    coincidere con l'header `Host`. Lo schema non si confronta (dietro il proxy di DigitalOcean la richiesta
    arriva in http). Senza `Origin` né `Referer`, con `Origin: null` (è il valore che il browser manda con
    `Referrer-Policy: no-referrer`, trattato come estraneo) o senza `Host` → `False`.
    """
    source = origin if origin is not None else referer
    if not source or not host or source.strip().lower() == "null":
        return False
    try:
        netloc = urlsplit(source).netloc
    except ValueError:
        return False
    return bool(netloc) and netloc.lower() == host.strip().lower()
