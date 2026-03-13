# app/schemas/merchant.py
# Pydantic schemas per validazione input/output dei Merchant

from pydantic import BaseModel


class MerchantCreateRequest(BaseModel):
    """Dati per creare un nuovo merchant."""
    business_name: str
    phone_number: str
    password: str
    humami_api_key: str
    humami_enterprise_id: str
    points_to_tree: int = 10


class LoginRequest(BaseModel):
    """Richiesta di login merchant."""
    password: str
