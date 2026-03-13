from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    """Configurazione App Fidelitree"""
    # Server App
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000
    
    # Database (Default SQLite locale)
    DATABASE_URL: str = "sqlite:///./fidelitree.db"
    
    # Digital Humani API URLs
    HUMANI_SANDBOX_URL: str = "https://api.sandbox.digitalhumani.com/v1"
    HUMANI_URL: str = "https://api.digitalhumani.com/v1"
    
    # Digital Humani Credentials (from .env)
    HUMANI_SANDBOX_API_KEY: str
    HUMANI_API_KEY: str
    HUMANI_ENTERPRISE_ID: str
    
    # Sicurezza & Auth
    ENCRYPTION_KEY: str
    JWT_SECRET_KEY: str
    MERCHANT_PASSWORD: str
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()