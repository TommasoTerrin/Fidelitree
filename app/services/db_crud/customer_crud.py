"""
Operazioni CRUD per i clienti (Customer).
"""

from typing import Optional
from sqlmodel import Session, select

from app.models.models import Customer


def create_customer(session: Session, email: str, auth_user_id: Optional[str] = None) -> Customer:
    """Crea un cliente (email normalizzata dal validatore del modello), con l'identità del provider se nota."""
    # model_validate: con table=True i validatori non girano sul costruttore
    customer = Customer.model_validate({"email": email, "auth_user_id": auth_user_id})
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return customer


def get_customer_by_auth_user_id(session: Session, auth_user_id: str) -> Optional[Customer]:
    """Recupera il cliente collegato a un'identità del provider di autenticazione."""
    statement = select(Customer).where(Customer.auth_user_id == auth_user_id)
    return session.exec(statement).first()


def get_customer_by_email(session: Session, email: str) -> Optional[Customer]:
    """Recupera un cliente per email (unica, confronto in minuscolo)."""
    statement = select(Customer).where(Customer.email == email.strip().lower())
    return session.exec(statement).first()
