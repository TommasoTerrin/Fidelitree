import logging
from sqlmodel import Session, create_engine, text
from app.core.config import settings
from app.services.db_crud import merchant_crud

logger = logging.getLogger(__name__)

from sqlmodel import SQLModel

def reset_db_and_create_test_merchant():
    """Utility per resettare il database e creare un merchant di test."""
    engine = create_engine(url=settings.DATABASE_URL)
    
    logger.info("🗑️ Pulizia database in corso...")
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    logger.info("✅ Database ricreato con gli ultimi modelli.")

    with Session(engine) as session:
        # Creazione merchant di prova reale
        logger.info("👤 Creazione merchant di prova...")
        test_data = {
            "business_name": "Fidelitree Real Test",
            "phone_number": "+393319910276",
            "password": settings.MERCHANT_PASSWORD,
            "humami_api_key": settings.HUMANI_SANDBOX_API_KEY,
            "humami_enterprise_id": settings.HUMANI_ENTERPRISE_ID,
            "points_to_tree": 10,
            "default_card_type": "just_trees"
        }
        
        merchant = merchant_crud.create_merchant(session, test_data)
        logger.info(f"✅ Merchant creato: {merchant.business_name} (ID: {merchant.id})")
        return merchant
