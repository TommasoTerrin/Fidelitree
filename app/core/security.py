"""
Servizi di sicurezza: gestione dei token JWT di sessione.
"""

from datetime import timedelta

from jose import jwt

from app.core.clock import utc_now
from app.core.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 giorni

def create_jwt_token(data: dict) -> str:
    """
    Crea un token JWT con una data di scadenza definita.
    """
    to_encode = data.copy()
    expire = utc_now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
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
