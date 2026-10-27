"""
Gestione dell'autenticazione per gli esercenti: registrazione, login, logout e cookie di sessione.

L'identità è verificata dal provider di autenticazione (`app/core/auth.py`); la logica di
registrazione e login vive in `merchant_service`. Un merchant appena registrato è in attesa di approvazione:
può collegare Instagram, ma i clienti nuovi vedono una carta di prova e lo scanner può solo togliere saldo,
finché il founder non lo approva. Il login ha un freno ai tentativi
(avviso dal 3° errore, 429 al 6° tentativo dopo 5 errori in 15 minuti, per email).
"""
from fastapi import APIRouter, Form, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from sqlmodel import Session

from app.core.auth import get_auth_provider
from app.core.clock import utc_now
from app.core.dependencies import get_session, set_session_cookie
from app.schemas.merchant import RegisterRequest
from app.services import merchant_service

router = APIRouter(prefix="/merchant", tags=["Merchant Auth"])


@router.post("/register")
async def register(
    body: RegisterRequest,
    session: Session = Depends(get_session),
):
    """
    Registra un nuovo merchant (non approvato) e lo autentica col cookie di sessione.
    Errori: 400 dati non validi (password di 8-128 caratteri), 409 email già in uso.
    """
    data = merchant_service.validate_registration(
        body.business_name, body.email, body.password, body.contact_phone,
    )
    merchant, token = merchant_service.register_merchant(session, get_auth_provider(), data)

    response = JSONResponse({
        "status": "success",
        "merchant_id": merchant.id,
        "is_approved": merchant.is_approved,
    })
    set_session_cookie(response, token)
    return response


@router.post("/login")
async def login(
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    """
    Login del merchant con email e password. Errori: 401 credenziali errate (stesso messaggio per email
    sconosciuta e password errata; dal 3° errore il testo avvisa del blocco), 403 identità valida ma non collegata
    a un merchant, 429 troppi tentativi (header `Retry-After`).
    """
    token = merchant_service.login_merchant(session, get_auth_provider(), email, password, now=utc_now())

    # Redirect al frontend dello scanner con il cookie inserito
    response = RedirectResponse(url="/merchant/scanner", status_code=303)
    set_session_cookie(response, token)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/merchant/login", status_code=303)
    response.delete_cookie("access_token")
    return response
