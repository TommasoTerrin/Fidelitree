"""
Popola il database con merchant di test e genera i link delle carte.
Sostituisce i vecchi create_test_merchants.py e generate_test_links.py.

Utilizzo (dalla root del progetto):
    python -m scripts.seed_db

Nota: NON cancella i dati esistenti; i merchant vengono creati solo se
il numero di telefono non è già presente. La password di tutti i merchant
di test è MERCHANT_PASSWORD (da .env).
"""

import logging

from sqlmodel import Session, select

from app.main import engine
from app.core.config import settings
from app.models.models import Merchant
from app.services.db_crud import merchant_crud, card_crud

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8000"  # cambia se serve testare un altro ambiente

MERCHANTS = [
    {
        "business_name": "Fidelitree Demo (REALE)",
        "phone_number": "+393319910276",
        "type": "test",
    },
    {
        "business_name": "Merchant Cashback (FAKE)",
        "phone_number": "+390000000002",
        "type": "test",
    },
]


def seed() -> None:
    with Session(engine) as session:
        print(f"\nPassword per tutti i merchant di test: {settings.MERCHANT_PASSWORD}")
        print("\n--- MERCHANT E LINK DI TEST ---")

        for data in MERCHANTS:
            existing = session.exec(
                select(Merchant).where(Merchant.phone_number == data["phone_number"])
            ).first()

            if existing:
                merchant = existing
                logger.info("Merchant già presente: %s", merchant.business_name)
            else:
                merchant = merchant_crud.create_merchant(
                    session, {**data, "password": settings.MERCHANT_PASSWORD}
                )
                logger.info("Creato merchant: %s", merchant.business_name)

            card = card_crud.create_card(session, merchant.id)

            print(f"\nMERCHANT: {merchant.business_name} (id={merchant.id})")
            print(f"  Phone:       {merchant.phone_number}")
            print(f"  DOWNLOAD:    {BASE_URL}/download_card?m={merchant.id}")
            print(f"  VIEW CARD:   {BASE_URL}/card/{card.id}")
            print(f"  MANAGE CARD: {BASE_URL}/merchant/card/{card.id}/manage")

        print("\n-------------------------------\n")


if __name__ == "__main__":
    seed()
