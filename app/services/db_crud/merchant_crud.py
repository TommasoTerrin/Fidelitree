import logging
from typing import List, Optional
from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.models import Merchant
from app.core.security import encrypt_key

logger = logging.getLogger(__name__)

def create_merchant(session: Session, merchant_data: dict) -> Merchant:
    """Crea un nuovo merchant."""
    try:
        new_merchant = Merchant(
            business_name=merchant_data.get("business_name"),
            phone_number=merchant_data.get("phone_number"),
            password=encrypt_key(merchant_data.get("password")),
            humami_api_key=encrypt_key(merchant_data.get("humami_api_key")),
            humami_enterprise_id=encrypt_key(merchant_data.get("humami_enterprise_id")),
            points_to_tree=merchant_data.get("points_to_tree", 10),
            id_telegram=merchant_data.get("id_telegram", ""),
            type=merchant_data.get("type", "test"),
            cb_points_per_tree=merchant_data.get("cb_points_per_tree", 0)
        )
        session.add(new_merchant)
        session.commit()
        session.refresh(new_merchant)
        return new_merchant
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Errore nella creazione del merchant: {e}")
        raise HTTPException(status_code=500, detail="Errore interno del server durante la creazione del merchant")

def get_merchant_by_id(session: Session, merchant_id: int) -> Optional[Merchant]:
    """Recupera un merchant per ID."""
    return session.get(Merchant, merchant_id)

def get_all_merchants(session: Session, skip: int = 0, limit: int = 100) -> List[Merchant]:
    """Restituisce la lista di tutti i merchant."""
    statement = select(Merchant).offset(skip).limit(limit)
    return session.exec(statement).all()

def update_merchant(session: Session, merchant: Merchant, update_data: dict) -> Merchant:
    """Aggiorna i dati di un merchant esistente."""
    try:
        for key, value in update_data.items():
            if key in ["password", "humami_api_key", "humami_enterprise_id"] and value:
                setattr(merchant, key, encrypt_key(value))
            else:
                setattr(merchant, key, value)
        
        session.add(merchant)
        session.commit()
        session.refresh(merchant)
        return merchant
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Errore aggiornamento merchant {merchant.id}: {e}")
        raise HTTPException(status_code=500, detail="Errore interno durante l'aggiornamento del merchant")

def delete_merchant(session: Session, merchant_id: int):
    """Elimina un merchant."""
    merchant = session.get(Merchant, merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant non trovato")
    
    session.delete(merchant)
    session.commit()
