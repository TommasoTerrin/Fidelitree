# app/core/dependencies.py
# Dipendenze condivise (session DB, autenticazione corrente, ecc.)
from sqlmodel import Session
from fastapi import Request, HTTPException, Depends
from app.core.config import settings
from app.core.security import decode_jwt_token

def get_session():
    """Genera una sessione DB da iniettare con Depends()."""
    # Importiamo engine qui per evitare import circolari
    from app.main import engine
    with Session(engine) as session:
        yield session

def get_current_merchant(request: Request, session: Session = Depends(get_session)):
    from app.models.models import Merchant
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato")
        
    payload = decode_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token non valido o scaduto")
        
    merchant_id = payload.get("sub")
    if merchant_id is None:
        raise HTTPException(status_code=401, detail="Token non valido")
        
    merchant = session.get(Merchant, int(merchant_id))
    if not merchant:
        raise HTTPException(status_code=401, detail="Merchant non trovato")
        
    return merchant
