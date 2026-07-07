"""
Integrazione specifica per l'autenticazione tramite Telegram.
Gestisce l'auto-login sicuro dai link forniti dal bot Telegram.
"""

import hashlib
import hmac
import json
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.core.config import settings
from app.core.dependencies import get_session
from app.models.models import Merchant
from app.core.security import create_jwt_token, verify_telegram_hash

router = APIRouter(prefix="/merchant/telegram", tags=["Merchant Telegram Auth"])
templates = Jinja2Templates(directory="app/templates")

def verify_telegram_webapp_data(init_data: str, bot_token: str) -> dict:
    """Valida i dati ricevuti dalla Telegram Web App."""
    if not init_data:
        return None
        
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data))
        hash_received = parsed_data.pop("hash")
        
        # Ordina le chiavi alfabeticamente
        data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(parsed_data.items())])
        
        # Calcola secret key basata sul bot token
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        # Calcola hash dei dati
        hash_calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if hash_calculated == hash_received:
            return parsed_data
    except Exception as e:
        print(f"Errore validazione Telegram data: {e}")
        
    return None

@router.get("/auto-login")
async def telegram_auto_login(
    tid: str, 
    h: str, 
    session: Session = Depends(get_session)
):
    """
    Esegue l'auto-login via link firmato da Telegram.
    Valida l'hash HMAC, cerca il merchant e imposta il cookie JWT.
    """
    if not verify_telegram_hash(tid, h):
        raise HTTPException(status_code=401, detail="Firma di sicurezza non valida")
    
    # Cerca il merchant per id_telegram
    statement = select(Merchant).where(Merchant.id_telegram == tid)
    merchant = session.exec(statement).first()
    
    if not merchant:
        # Se l'hash è valido ma il merchant non c'è, forse è stato rimosso
        # Rimandiamo al login normale per ri-associarlo
        return RedirectResponse(url=f"/merchant/login?telegram_id={tid}", status_code=303)
        
    # Crea JWT token
    token = create_jwt_token({"sub": str(merchant.id)})
    
    # Redirect allo scanner con il cookie impostato
    response = RedirectResponse(url="/merchant/scanner", status_code=303)
    response.set_cookie(
        "access_token", 
        token, 
        httponly=True, 
        max_age=60*24*7*60,
        samesite="lax"
    )
    return response
