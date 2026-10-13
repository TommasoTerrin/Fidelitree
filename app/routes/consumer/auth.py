"""
Accesso del cliente finale: richiesta e verifica del codice OTP via email, logout.

L'identità è verificata dal provider di autenticazione (`app/core/auth.py`); al primo accesso
il `Customer` viene creato da `customer_service.get_or_create_customer`. La sessione è lo stesso
cookie `access_token` usato dal merchant.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from sqlmodel import Session

from app.core.auth import get_auth_provider
from app.core.dependencies import get_session, set_session_cookie
from app.core.errors import AuthError
from app.schemas.customer import OtpRequest, OtpVerifyRequest
from app.services import customer_service

router = APIRouter(tags=["Customer Auth"])


@router.post("/api/customer/otp/request")
async def request_otp(body: OtpRequest):
    """
    Invia un codice monouso all'email del cliente. Errori: 400 email non valida.
    La risposta è la stessa per qualsiasi email valida: non rivela se esiste già un account.
    """
    email = customer_service.normalize_email(body.email)
    get_auth_provider().request_otp(email)
    return {"status": "success"}


@router.post("/api/customer/otp/verify")
async def verify_otp(body: OtpVerifyRequest, session: Session = Depends(get_session)):
    """
    Verifica il codice, crea il cliente al primo accesso e imposta il cookie di sessione.
    Errori: 400 email non valida, 401 codice errato o scaduto.
    """
    email = customer_service.normalize_email(body.email)
    provider = get_auth_provider()
    token = provider.verify_otp(email, body.code.strip())
    identity = provider.verify_token(token)
    if identity is None:
        raise AuthError("Codice non valido")
    customer = customer_service.get_or_create_customer(session, identity)

    response = JSONResponse({"status": "success", "customer_id": customer.id})
    set_session_cookie(response, token)
    return response


@router.get("/customer/logout")
async def logout():
    """Chiude la sessione del cliente e torna alla pagina di accesso."""
    response = RedirectResponse(url="/customer/login", status_code=303)
    response.delete_cookie("access_token")
    return response
