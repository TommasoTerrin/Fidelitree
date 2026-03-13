from cryptography.fernet import Fernet
from jose import jwt
from datetime import datetime, timedelta
from app.core.config import settings

cipher_suite = Fernet(settings.ENCRYPTION_KEY.encode() if isinstance(settings.ENCRYPTION_KEY, str) else settings.ENCRYPTION_KEY)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 giorni

def encrypt_key(api_key: str) -> str:
    return cipher_suite.encrypt(api_key.encode()).decode()

def decrypt_key(encrypted_key: str) -> str:
    return cipher_suite.decrypt(encrypted_key.encode()).decode()

def create_jwt_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_jwt_token(token: str) -> dict | None:
    try:
        decoded_token = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
        return decoded_token
    except jwt.JWTError:
        return None
