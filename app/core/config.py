"""
Modulo di configurazione globale dell'applicazione.
Carica le variabili d'ambiente da .env (in locale) o dall'ambiente (in produzione).
Tutte le variabili senza default sono obbligatorie: l'app non parte se mancano.
"""

from typing import Literal

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
    AUTH_PROVIDER: Literal["dev", "supabase"] = "dev"  # "dev": solo locale/test
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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache()
def get_settings() -> Settings:
    """Ritorna un'istanza singleton delle impostazioni."""
    return Settings()


settings = get_settings()
