import uuid 
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship
from pydantic import field_validator

class Merchant(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key= True) #fattto così perchè sqlmodel lo mette da solo
    business_name: str #intanto solo questa come info minimal
    phone_number: str
    password: str # salvata cifrata via Fernet
    humami_api_key: str #da criptare
    humami_enterprise_id: str #da criptare
    points_to_tree: int = Field(default= 10) #quanti punti per completare
    
    cards: List["TreeCard"] = Relationship(back_populates= "merchant") #relazione con le carte del merchant (1:N)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v:str):
        #controllo +39 (per ora solo italia)
        if not v.startswith("+39"):
            raise ValueError("ricorda che devi inserire +39")

        # cifre devono essere 9 o 10
        digits= v[3:] 
        if not digits.isdigit():
            raise ValueError("non sono tutti numeri quelli inseriti")
        if len(digits) not in (9,10):
            raise ValueError("le cifre devono essere 9 o 10")
        return v




class TreeCard(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    merchant_id: int= Field(foreign_key="merchant.id") #campo per la l'id necessario associazione a merchant
    current_points: int = Field(default=0)
    trees_planted: int = Field(default=0) # contatore alberi piantati
    trees_list: str = Field(default="[]") # JSON serializzato di List[uuid] degli ID degli alberi

    merchant: Merchant = Relationship(back_populates="cards")