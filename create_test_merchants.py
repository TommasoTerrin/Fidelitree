import logging
from sqlmodel import Session, create_engine
from app.models.models import Merchant
from app.core.config import settings
from app.core.security import encrypt_key

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

engine = create_engine(settings.DATABASE_URL)

def create_test_merchants():
    with Session(engine) as session:
        # Pulizia merchant esistenti per evitare conflitti se necessario
        from sqlmodel import delete
        session.exec(delete(Merchant))
        session.commit()

        merchants_data = [
            {
                "business_name": "Merchant Alberi e Cashback (REALE)",
                "phone_number": "+393319910276",
                "password": settings.MERCHANT_PASSWORD,
                "humami_api_key": settings.HUMANI_SANDBOX_API_KEY,
                "humami_enterprise_id": settings.HUMANI_ENTERPRISE_ID,
                "points_to_tree": 5,
                "default_card_type": "cards_and_cb_points",
                "type": "test"
            },
            {
                "business_name": "Merchant Solo Alberi (FAKE)",
                "phone_number": "+390000000001",
                "password": settings.MERCHANT_PASSWORD,
                "humami_api_key": settings.HUMANI_SANDBOX_API_KEY,
                "humami_enterprise_id": settings.HUMANI_ENTERPRISE_ID,
                "points_to_tree": 10,
                "default_card_type": "just_trees",
                "type": "test"
            },
            {
                "business_name": "Merchant Solo Cashback (FAKE)",
                "phone_number": "+390000000002",
                "password": settings.MERCHANT_PASSWORD,
                "humami_api_key": settings.HUMANI_SANDBOX_API_KEY,
                "humami_enterprise_id": settings.HUMANI_ENTERPRISE_ID,
                "points_to_tree": 10,
                "default_card_type": "just_cb_points",
                "type": "test"
            }
        ]

        print(f"PASSWORD USATA PER TUTTI: {settings.MERCHANT_PASSWORD}")
        for data in merchants_data:
            # Criptiamo le chiavi e la password
            data["humami_api_key"] = encrypt_key(data["humami_api_key"])
            data["humami_enterprise_id"] = encrypt_key(data["humami_enterprise_id"])
            data["password"] = encrypt_key(data["password"])
            
            merchant = Merchant(**data)
            session.add(merchant)
            logger.info(f"Creazione merchant: {data['business_name']} ({data['phone_number']})")
        
        session.commit()
        logger.info("✅ Tutti i merchant di test sono stati creati.")

if __name__ == "__main__":
    create_test_merchants()
