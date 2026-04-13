# app/routes/merchant/auth.py
# MERCHANT AUTH — Login, logout, verifica sessione
#
# Endpoint previsti:
#   POST /merchant/auth/login     → Verifica password, crea sessione/token
#   POST /merchant/auth/logout    → Invalida sessione
#
# Dipendenze esportate:
#   get_current_merchant()        → Dependency per proteggere gli endpoint merchant
from fastapi import APIRouter, Form, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.core.dependencies import get_session
from app.models.models import Merchant
from app.core.security import decrypt_key, create_jwt_token

router = APIRouter(prefix="/merchant", tags=["Merchant Auth"])

from sqlmodel import select

@router.post("/login")
async def login(
    phone_number: str = Form(...), 
    password: str = Form(...), 
    telegram_id: str = Form(None), # Campo opzionale per l'associazione
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
    
    # Se abbiamo un telegram_id, lo associamo al merchant
    if telegram_id:
        merchant.id_telegram = telegram_id
        session.add(merchant)
        session.commit()
        session.refresh(merchant)
        
    token = create_jwt_token({"sub": str(merchant.id)})
    
    # Se il login avviene da Telegram Mini App, restituiamo il token invece del redirect
    # (Lo gestiremo nel frontend della Mini App)
    
    # Redirect al frontend dello scanner con il cookie inserito
    response = RedirectResponse(url="/merchant/scanner", status_code=303)
    response.set_cookie("access_token", token, httponly=True, max_age=60*24*7*60)
    return response

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/merchant/login", status_code=303)
    response.delete_cookie("access_token")
    return response
