# app/schemas/merchant.py
from pydantic import BaseModel
from typing import Optional, Literal


class MerchantCreateRequest(BaseModel):
    business_name: str
    phone_number: str
    password: str
    humami_api_key: str
    humami_enterprise_id: str
    points_to_tree: int = 10
    id_telegram: str = ""
    type: Literal['test', 'free', 'pro'] = 'test'
    cb_points_per_tree: int = 0


class MerchantUpdateRequest(BaseModel):
    business_name: Optional[str] = None
    phone_number: Optional[str] = None
    password: Optional[str] = None
    humami_api_key: Optional[str] = None
    humami_enterprise_id: Optional[str] = None
    points_to_tree: Optional[int] = None
    id_telegram: Optional[str] = None
    type: Optional[Literal['test', 'free', 'pro']] = None
    cb_points_per_tree: Optional[int] = None


class MerchantResponse(BaseModel):
    id: int
    business_name: str
    phone_number: str
    points_to_tree: int
    id_telegram: str
    type: str
    cb_points_per_tree: int

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    password: str
