"""
Modulo di configurazione globale dell'applicazione.
Carica le variabili d'ambiente da .env (in locale) o dall'ambiente (in produzione).
Tutte le variabili senza default sono obbligatorie: l'app non parte se mancano.
"""

import base64
import binascii
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """Configurazione App Fidelitree"""
    # Server App (solo per l'avvio locale via local_main.py)
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8001

    # Database — URL Postgres completo (Neon in produzione)
    DATABASE_URL: str

    # Sicurezza & Auth
    JWT_SECRET_KEY: str      # firma dei token di sessione merchant
    ADMIN_SECRET_KEY: str    # protegge gli endpoint amministrativi /api/merchant
    # "dev": solo locale/test (rifiutato con ENVIRONMENT=production); "local": password nel nostro DB (ammesso in produzione)
    AUTH_PROVIDER: Literal["dev", "local", "supabase"] = "dev"
    ENVIRONMENT: str = "development"  # "production" in produzione
    # Solo provider dev: password accettata per ogni email non registrata in memoria (il seed gira
    # in un altro processo del server). Vuota = nessun fallback. Non è un segreto: mai in produzione.
    DEV_AUTH_PASSWORD: str = "dev-password"

    # Ecologi (piantumazione alberi) — chiave unica di piattaforma, paga il founder
    ECOLOGI_BASE_URL: str = "https://public.ecologi.com"
    ECOLOGI_API_KEY: str = ""  # chiave REALE (addebita): vuota consentita in dev/test
    # Chiave di PROVA: stesso URL della reale, la richiesta porta il flag "test": true (nessun addebito)
    ECOLOGI_TEST_API_KEY: str = ""
    ECOLOGI_TEST_MODE: bool = True  # True: usa la chiave di test + flag test (nessun addebito); False SOLO in produzione
    ECOLOGI_GLOBAL_MONTHLY_CAP: int = 20  # max alberi piantati in una chiusura mensile

    # Soglie di default dei livelli del pool (punti del mese); override per negozio nel DB
    TIER_BRONZE_POINTS: int = 100
    TIER_SILVER_POINTS: int = 300
    TIER_GOLD_POINTS: int = 600

    # Cifratura e segreti (v0.3.0) — obbligatorie e senza default: l'app non parte se mancano
    ENCRYPTION_KEY: str = Field(min_length=1)    # AES-256-GCM per chiave Zernio e secret webhook: 32 byte, base64 urlsafe
    ENCRYPTION_KEY_ID: str = "1"                 # id salvato col dato cifrato (rotazione futura)
    IGSID_HMAC_KEY: str = Field(min_length=1)    # indice cieco dell'IGSID; NON ruotabile senza scollegare le carte
    CARD_LINK_KEY: str = Field(min_length=1)     # deriva il token del link /c/<token>; cambiarla invalida i link

    # Instagram / Zernio (v0.3.0)
    PUBLIC_BASE_URL: str = "http://127.0.0.1:8001"  # URL pubblico https: link delle carte e webhook su Zernio
    ZERNIO_BASE_URL: str = "https://zernio.com/api"  # base dell'API Zernio
    INSTAGRAM_CARD_KEYWORD: str = "CARTA"            # parola chiave di piattaforma che il cliente scrive in DM
    ZERNIO_MONTHLY_SEND_LIMIT: int = 10000           # invii gratuiti al mese per team Zernio (solo per l'avviso)
    ZERNIO_SEND_WARN_PERCENT: int = 75               # soglia di avviso nel pannello del merchant (%)
    # Solo per `scripts.zernio_check` (collaudo locale): chiave Zernio di prova. Vuota = lo script la chiede a video.
    # SecretStr: non compare in repr né nei log; non serve in produzione.
    ZERNIO_CHECK_API_KEY: SecretStr = SecretStr("")

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        """La chiave di cifratura deve decodificare (base64 urlsafe) in esattamente 32 byte."""
        try:
            raw = base64.urlsafe_b64decode(v)
        except (binascii.Error, ValueError):
            raise ValueError("ENCRYPTION_KEY non è base64 urlsafe valido")
        if len(raw) != 32:
            raise ValueError("ENCRYPTION_KEY deve essere di 32 byte (base64 urlsafe)")
        return v

    # hide_input_in_errors: un errore di avvio non deve mai stampare il valore di una chiave
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)


@lru_cache()
def get_settings() -> Settings:
    """Ritorna un'istanza singleton delle impostazioni."""
    return Settings()


settings = get_settings()
