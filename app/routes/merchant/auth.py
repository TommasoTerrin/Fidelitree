"""
Gestione dell'autenticazione per gli esercenti.
Include registrazione self-service, login, logout e cookie di sessione JWT.
"""
#
# Endpoint previsti:
#   POST /merchant/register       → Registrazione self-service (chiave Ecologi obbligatoria)
#   POST /merchant/login          → Verifica password, crea sessione/token
#   GET  /merchant/logout         → Invalida sessione
from fastapi import APIRouter, Form, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlmodel import Session

from app.core.dependencies import get_session
from app.models.models import Merchant
from app.core.security import decrypt_key, create_jwt_token
from app.services import ecologi_service
from app.services.db_crud import merchant_crud
from app.schemas.merchant import MerchantRegisterRequest

router = APIRouter(prefix="/merchant", tags=["Merchant Auth"])

from sqlmodel import select

COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 giorni, allineato alla scadenza del JWT


@router.post("/register")
async def register(
    body: MerchantRegisterRequest,
    session: Session = Depends(get_session),
):
    """
    Registrazione self-service di un merchant.
    La chiave Ecologi è il gate d'ingresso: viene validata con una chiamata
    in test mode (nessun addebito) prima di creare l'account.
    """
    if merchant_crud.get_merchant_by_phone(session, body.phone_number):
        raise HTTPException(status_code=409, detail="Esiste già un account con questo numero di telefono")

    try:
        valid = await ecologi_service.validate_api_key(body.ecologi_api_key)
    except ecologi_service.EcologiError:
        raise HTTPException(status_code=503, detail="Ecologi non raggiungibile, riprova tra poco")
    if not valid:
        raise HTTPException(
            status_code=400,
            detail="Chiave Ecologi non valida: controlla di averla copiata dalla dashboard Ecologi",
        )

    merchant_data = body.model_dump()
    merchant_data["type"] = "free"
    merchant = merchant_crud.create_merchant(session, merchant_data)

    # Auto-login: stesso cookie di sessione del login classico
    token = create_jwt_token({"sub": str(merchant.id)})
    response = JSONResponse({"status": "success", "merchant_id": merchant.id})
    response.set_cookie("access_token", token, httponly=True, max_age=COOKIE_MAX_AGE)
    return response


@router.post("/login")
async def login(
    phone_number: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session)
):
    """Esegue il login del merchant cercandolo per numero di telefono."""
    statement = select(Merchant).where(Merchant.phone_number == phone_number)
    merchant = session.exec(statement).first()
    
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant non trovato")
        
    try:
        decrypted_password = decrypt_key(merchant.password)
        if password != decrypted_password:
            raise HTTPException(status_code=401, detail="Password errata")
    except Exception as e:
        print(f"Login error decryption: {e}")
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    
    token = create_jwt_token({"sub": str(merchant.id)})

    # Redirect al frontend dello scanner con il cookie inserito
    response = RedirectResponse(url="/merchant/scanner", status_code=303)
    response.set_cookie("access_token", token, httponly=True, max_age=60*24*7*60)
    return response

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/merchant/login", status_code=303)
    response.delete_cookie("access_token")
    return response
