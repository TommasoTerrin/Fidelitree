"""
Modulo di configurazione globale dell'applicazione.
Carica le variabili d'ambiente da .env (in locale) o dall'ambiente (in produzione).
Tutte le variabili senza default sono obbligatorie: l'app non parte se mancano.
"""

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
    ENCRYPTION_KEY: str      # chiave Fernet per cifrare le password dei merchant
    JWT_SECRET_KEY: str      # firma dei token di sessione merchant
    MERCHANT_PASSWORD: str   # password del merchant di test creato via seed
    ADMIN_SECRET_KEY: str    # protegge gli endpoint amministrativi /api/merchant

    # Ecologi (piantumazione alberi) — la chiave API è per-merchant, nel DB
    ECOLOGI_BASE_URL: str = "https://public.ecologi.com"
    ECOLOGI_TEST_MODE: bool = True  # True: nessun addebito reale; mettere False SOLO in produzione

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache()
def get_settings() -> Settings:
    """Ritorna un'istanza singleton delle impostazioni."""
    return Settings()


settings = get_settings()
