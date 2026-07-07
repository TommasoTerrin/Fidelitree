"""
Modulo di configurazione globale dell'applicazione.
Gestisce le variabili d'ambiente, le chiavi API e le impostazioni del database.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    """Configurazione App Fidelitree"""
    # Server App
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8001
    
    # Database
    DATABASE_PASSWORD: str | None = None
    DATABASE_URL: str | None = None
    
    def model_post_init(self, __context):
        """
        Inizializza la URL del database dopo la creazione del modello 
        se non è stata fornita esplicitamente.
        """
        if not self.DATABASE_URL and self.DATABASE_PASSWORD:
            self.DATABASE_URL = f"postgresql://neondb_owner:{self.DATABASE_PASSWORD}@ep-morning-credit-alqqrsao-pooler.c-3.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    
    # Sicurezza & Auth
    ENCRYPTION_KEY: str
    JWT_SECRET_KEY: str
    MERCHANT_PASSWORD: str
    ADMIN_SECRET_KEY: str = "supersecret_fidelitree_2024"
    
    # URL pubblico dell'app (usato per generare i link delle carte via WhatsApp)
    BASE_URL: str = "http://localhost:8000"
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache()
def get_settings() -> Settings:
    """
    Ritorna un'istanza singleton delle impostazioni, caricata con cache LRU.
    """
    return Settings()

settings = get_settings()