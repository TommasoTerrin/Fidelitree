from sqlmodel import Session, create_engine, select
from app.core.config import settings
from app.models.models import Merchant, TreeCard

# Configura l'engine usando le settings (che leggono .env)
engine = create_engine(settings.DATABASE_URL)

def get_data():
    with Session(engine) as session:
        # 1. Trova il merchant
        phone = "+393319910276"
        statement = select(Merchant).where(Merchant.phone_number == phone)
        merchant = session.exec(statement).first()
        
        if not merchant:
            print(f"Merchant con numero {phone} non trovato.")
            return
        
        print(f"--- DATI MERCHANT ---")
        print(f"ID: {merchant.id}")
        print(f"Business Name: {merchant.business_name}")
        
        # 2. Trova TUTTE le card associate
        card_statement = select(TreeCard).where(TreeCard.merchant_id == merchant.id)
        cards = session.exec(card_statement).all()
        
        if not cards:
            print(f"\nNessuna card trovata per questo merchant.")
        else:
            print(f"\n--- DATI CARD ({len(cards)} trovate) ---")
            for c in cards:
                print(f"Card ID: {c.id} | Punti: {c.current_points}")

if __name__ == "__main__":
    get_data()
