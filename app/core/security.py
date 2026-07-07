"""
Servizi di sicurezza, crittografia e gestione token JWT.
Include utility per la validazione di Telegram e crittografia delle chiavi API.
"""

from cryptography.fernet import Fernet
import hmac
import hashlib
from jose import jwt
from datetime import datetime, timedelta
from app.core.config import settings

cipher_suite = Fernet(settings.ENCRYPTION_KEY.encode() if isinstance(settings.ENCRYPTION_KEY, str) else settings.ENCRYPTION_KEY)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 giorni

def encrypt_key(api_key: str) -> str:
    """Cripta una stringa (es. API Key) utilizzando Fernet."""
    return cipher_suite.encrypt(api_key.encode()).decode()

def decrypt_key(encrypted_key: str) -> str:
    """Decripta una stringa precedentemente criptata con Fernet."""
    return cipher_suite.decrypt(encrypted_key.encode()).decode()

def create_jwt_token(data: dict) -> str:
    """
    Crea un token JWT con una data di scadenza definita.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
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

def generate_telegram_hash(telegram_id: str) -> str:
    """Genera un hash HMAC per validare l'ID Telegram."""
    return hmac.new(
        settings.TELEGRAM_BOT_TOKEN.encode(),
        telegram_id.encode(),
        hashlib.sha256
    ).hexdigest()

def verify_telegram_hash(telegram_id: str, hash_to_verify: str) -> bool:
    """Verifica se l'hash HMAC per l'ID Telegram è valido."""
    expected_hash = generate_telegram_hash(telegram_id)
    return hmac.compare_digest(expected_hash, hash_to_verify)
