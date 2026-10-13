"""
Schemi Pydantic per l'accesso del cliente (email + codice OTP).
"""

from pydantic import BaseModel


class OtpRequest(BaseModel):
    """Richiesta di un codice OTP per l'email indicata."""
    email: str


class OtpVerifyRequest(BaseModel):
    """Verifica del codice OTP ricevuto via email."""
    email: str
    code: str
