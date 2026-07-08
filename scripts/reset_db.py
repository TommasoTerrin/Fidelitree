"""
Reset completo del database: elimina e ricrea tutte le tabelle.
DA USARE CON CAUTELA: cancella tutti i dati (merchant e card).

Utilizzo (dalla root del progetto):
    python -m scripts.reset_db            # chiede conferma
    python -m scripts.reset_db --force    # procede senza conferma
"""

import logging
import sys

from sqlmodel import SQLModel

from app.main import engine
import app.models.models  # noqa: F401 — registra le tabelle nel metadata

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def reset_db() -> None:
    """Elimina e ricrea lo schema del database puntato da DATABASE_URL."""
    logger.info("Drop di tutte le tabelle...")
    SQLModel.metadata.drop_all(engine)
    logger.info("Ricreazione dello schema...")
    SQLModel.metadata.create_all(engine)
    logger.info("Database resettato.")


if __name__ == "__main__":
    if "--force" in sys.argv:
        reset_db()
    else:
        confirm = input("ATTENZIONE: questo script eliminera' TUTTI i dati dal database. Sei sicuro? (s/n): ")
        if confirm.lower() == "s":
            reset_db()
        else:
            print("Operazione annullata.")
