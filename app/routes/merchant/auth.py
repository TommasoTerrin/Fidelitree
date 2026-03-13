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

@router.post("/login")
async def login(password: str = Form(...), session: Session = Depends(get_session)):
    # Nell'MVP usiamo il merchant 1 di test
    merchant = session.get(Merchant, 1)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant non trovato")
        
    try:
        decrypted_password = decrypt_key(merchant.password)
        if password != decrypted_password:
            raise HTTPException(status_code=401, detail="Password errata")
    except Exception:
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
