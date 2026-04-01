import uuid
from sqlmodel import Session, create_engine, select
from app.models.models import Merchant, TreeCard
from app.core.config import settings
from app.services import card_service

engine = create_engine(settings.DATABASE_URL)

def generate_test_links():
    base_url = "http://localhost:8000" # Cambia se necessario
    
    with Session(engine) as session:
        merchants = session.exec(select(Merchant)).all()
        
        print("\n--- TEST LINKS ---")
        for m in merchants:
            # Creiamo una card per ogni merchant
            card = card_service.create_card(session, m.id)
            
            card_url = f"{base_url}/card/{card.id}"
            manage_url = f"{base_url}/merchant/card/{card.id}/manage"
            
            print(f"\nMERCHANT: {m.business_name} (Tipo: {m.default_card_type})")
            print(f"  Phone: {m.phone_number}")
            print(f"  VIEW CARD: {card_url}")
            print(f"  MANAGE CARD: {manage_url}")
        print("\n------------------")

if __name__ == "__main__":
    generate_test_links()
