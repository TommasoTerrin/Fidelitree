"""
Operazioni CRUD per la gestione degli esercenti (Merchant) nel database.
"""

import logging
from typing import List, Optional
from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.models import Merchant

logger = logging.getLogger(__name__)

# Campi impostabili alla creazione (il chiamante decide cosa passare: l'API admin non espone auth_user_id)
_CREATE_FIELDS = (
    "business_name", "email", "auth_user_id", "contact_phone", "type", "is_approved", "is_paused",
    "conversion_enabled", "conversion_threshold", "conversion_value_cents",
    "bronze_threshold", "silver_threshold", "gold_threshold",
)


def create_merchant(session: Session, merchant_data: dict) -> Merchant:
    """Crea un nuovo merchant; i campi non indicati prendono i default del modello."""
    try:
        # model_validate è necessario: con table=True i validatori
        # non girano sul costruttore diretto
        new_merchant = Merchant.model_validate(
            {k: merchant_data[k] for k in _CREATE_FIELDS if k in merchant_data}
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


def get_merchant_by_webhook_hook_id(session: Session, hook_id: str) -> Optional[Merchant]:
    """Recupera il merchant dall'id opaco nel path del suo webhook Zernio (`Merchant.webhook_hook_id`)."""
    return session.exec(select(Merchant).where(Merchant.webhook_hook_id == hook_id)).first()


def get_merchant_by_zernio_account_id(session: Session, account_id: str) -> Optional[Merchant]:
    """Recupera il merchant a cui è collegato un account Instagram di Zernio (`Merchant.zernio_account_id`, unico)."""
    return session.exec(select(Merchant).where(Merchant.zernio_account_id == account_id)).first()


def get_merchant_by_auth_user_id(session: Session, auth_user_id: str) -> Optional[Merchant]:
    """Recupera il merchant collegato a un'identità del provider di autenticazione."""
    statement = select(Merchant).where(Merchant.auth_user_id == auth_user_id)
    return session.exec(statement).first()


def get_merchant_by_email(session: Session, email: str) -> Optional[Merchant]:
    """Recupera un merchant per email (unica, confronto in minuscolo)."""
    statement = select(Merchant).where(Merchant.email == email.strip().lower())
    return session.exec(statement).first()


def get_all_merchants(session: Session, skip: int = 0, limit: int = 100) -> List[Merchant]:
    """Restituisce la lista di tutti i merchant."""
    statement = select(Merchant).offset(skip).limit(limit)
    return session.exec(statement).all()


def update_merchant(session: Session, merchant: Merchant, update_data: dict) -> Merchant:
    """Aggiorna i dati di un merchant esistente (rivalidando il risultato)."""
    try:
        # Valida su una copia: se fallisce il merchant in sessione resta intatto
        # (i validatori non girano su setattr)
        # getattr (non model_dump): ricarica l'istanza se la sessione l'ha scaduta dopo un commit
        current = {name: getattr(merchant, name) for name in Merchant.model_fields}
        validated = Merchant.model_validate({**current, **update_data})
        for key in update_data:
            setattr(merchant, key, getattr(validated, key))

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
    """Elimina un merchant (carte, movimenti, pool e piantumazioni vanno in cascata)."""
    merchant = session.get(Merchant, merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant non trovato")

    session.delete(merchant)
    session.commit()
