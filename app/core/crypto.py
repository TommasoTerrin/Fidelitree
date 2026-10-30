"""
Segreti: cifratura, indice cieco dell'IGSID e token del link della carta.

Le funzioni sono pure: le chiavi arrivano come argomento opzionale e, se
mancano, si usano quelle delle settings (come il tempo nei core degli altri
service). Niente fastapi, niente DB.

Nessun messaggio d'errore contiene mai il dato in chiaro, né il cifrato, né
una chiave.
"""

import base64
import binascii
import hashlib
import hmac
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

NONCE_BYTES = 12
MIN_HMAC_KEY_CHARS = 32


class SecretDecryptionError(Exception):
    """Dato cifrato illeggibile: formato errato, id di chiave sconosciuto o autenticazione fallita."""


# --- Core puro ---

def _decode_key(key: str) -> bytes:
    """Decodifica una chiave AES (base64 urlsafe) e verifica che sia di 32 byte."""
    try:
        raw = base64.urlsafe_b64decode(key)
    except (binascii.Error, ValueError):
        raise ValueError("chiave di cifratura non valida: base64 urlsafe atteso") from None
    if len(raw) != 32:
        raise ValueError("chiave di cifratura non valida: servono 32 byte")
    return raw


def encrypt_secret(plaintext: str, *, key: str | None = None, key_id: str | None = None) -> str:
    """
    Cifra con AES-256-GCM e nonce casuale da 12 byte.
    Formato salvato: `"<key_id>:<base64url(nonce + cifrato)>"`.
    """
    key = settings.ENCRYPTION_KEY if key is None else key
    key_id = settings.ENCRYPTION_KEY_ID if key_id is None else key_id
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(_decode_key(key)).encrypt(nonce, plaintext.encode("utf-8"), None)
    return f"{key_id}:{base64.urlsafe_b64encode(nonce + ciphertext).decode('ascii')}"


def decrypt_secret(stored: str, *, keys: dict[str, str] | None = None) -> str:
    """
    Decifra un valore prodotto da `encrypt_secret`. `keys` mappa id → chiave
    (default: solo la chiave delle settings). Un id sconosciuto è un errore
    esplicito: serve a una rotazione futura che non perda dati in silenzio.
    """
    if keys is None:
        keys = {settings.ENCRYPTION_KEY_ID: settings.ENCRYPTION_KEY}
    key_id, sep, payload = stored.partition(":")
    if not sep:
        raise SecretDecryptionError("formato del dato cifrato non valido")
    key = keys.get(key_id)
    if key is None:
        raise SecretDecryptionError("id della chiave di cifratura sconosciuto")
    try:
        raw = base64.urlsafe_b64decode(payload)
        if len(raw) <= NONCE_BYTES:
            raise SecretDecryptionError("dato cifrato troppo corto")
        return AESGCM(_decode_key(key)).decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], None).decode("utf-8")
    except SecretDecryptionError:
        raise
    except (InvalidTag, binascii.Error, ValueError):
        raise SecretDecryptionError("decifratura fallita: dato alterato o chiave errata") from None


def _hmac_hex(key: str, message: str) -> str:
    return hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def igsid_blind_index(igsid: str, *, key: str | None = None) -> str:
    """Indice cieco dell'IGSID: `HMAC-SHA256(IGSID_HMAC_KEY, igsid)` in esadecimale. L'IGSID non si salva."""
    return _hmac_hex(settings.IGSID_HMAC_KEY if key is None else key, igsid)


def card_link_token(card_id: int, link_version: int, *, key: str | None = None) -> str:
    """
    Token del link `/c/<token>`: `base64url(HMAC-SHA256(CARD_LINK_KEY, "<card_id>:<link_version>"))`
    senza padding. Si ricalcola quando serve; la revoca incrementa `link_version`.
    """
    key = settings.CARD_LINK_KEY if key is None else key
    digest = hmac.new(key.encode("utf-8"), f"{card_id}:{link_version}".encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def token_hash(token: str) -> str:
    """SHA-256 esadecimale del token: è l'unica forma salvata nel DB (`Card.link_token_hash`)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    """Confronto in tempo costante (`hmac.compare_digest` sui byte, così accetta anche testo non ASCII)."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def mask_secret(value: str) -> str:
    """Per log e pannello: `"…"` + ultime 4 cifre. Vuota → `"(vuota)"`; fino a 4 caratteri non si mostra nulla."""
    if not value:
        return "(vuota)"
    return "…" + (value[-4:] if len(value) > 4 else "")


# --- Shell ---

def validate_keys(
    *, encryption_key: str | None = None, igsid_key: str | None = None, link_key: str | None = None
) -> None:
    """
    Controllo all'avvio (lifespan): `ENCRYPTION_KEY` deve decodificare a 32 byte e le chiavi
    HMAC devono avere almeno 32 caratteri. Altrimenti `RuntimeError`: l'app non parte.
    """
    encryption_key = settings.ENCRYPTION_KEY if encryption_key is None else encryption_key
    igsid_key = settings.IGSID_HMAC_KEY if igsid_key is None else igsid_key
    link_key = settings.CARD_LINK_KEY if link_key is None else link_key
    try:
        _decode_key(encryption_key)
    except ValueError:
        raise RuntimeError("ENCRYPTION_KEY non valida: servono 32 byte in base64 urlsafe") from None
    for name, value in (("IGSID_HMAC_KEY", igsid_key), ("CARD_LINK_KEY", link_key)):
        if len(value) < MIN_HMAC_KEY_CHARS:
            raise RuntimeError(f"{name} troppo corta: servono almeno {MIN_HMAC_KEY_CHARS} caratteri")
