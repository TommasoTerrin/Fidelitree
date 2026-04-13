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
from app.core.security import create_jwt_token

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

@router.get("/scanner", response_class=HTMLResponse)
async def telegram_scanner_view(request: Request):
    """Restituisce la pagina dello scanner configurata per Telegram."""
    return templates.TemplateResponse("merchant/telegram_scanner.html", {"request": request})

@router.post("/login")
async def telegram_login(request: Request, session: Session = Depends(get_session)):
    """Esegue il login del merchant usando i dati della Mini App."""
    body = await request.json()
    init_data = body.get("initData")
    
    # In ambiente di test locale, se il token è 'test_token', saltiamo la validazione rigorosa dell'hash
    # se non vogliamo complicarci la vita con ngrok subito, ma per ora la implementiamo correttamente.
    telegram_data = verify_telegram_webapp_data(init_data, settings.TELEGRAM_BOT_TOKEN)
    
    if not telegram_data:
        # Debug per test locale con 'test_token'
        if settings.TELEGRAM_BOT_TOKEN == "test_token":
             # Estraiamo l'id utente senza validazione hash solo per debug locale
             try:
                user_data = json.loads(dict(urllib.parse.parse_qsl(init_data)).get("user"))
                telegram_id = str(user_data.get("id"))
             except:
                 raise HTTPException(status_code=401, detail="Dati Telegram non validi")
        else:
            raise HTTPException(status_code=401, detail="Firma Telegram non valida")
    else:
        user_data = json.loads(telegram_data.get("user"))
        telegram_id = str(user_data.get("id"))

    # Cerca il merchant per id_telegram
    statement = select(Merchant).where(Merchant.id_telegram == telegram_id)
    merchant = session.exec(statement).first()
    
    if not merchant:
        raise HTTPException(status_code=404, detail="Account non collegato. Usa il bot per autenticarti.")
        
    # Crea JWT token
    token = create_jwt_token({"sub": str(merchant.id)})
    
    response = RedirectResponse(url="/merchant/scanner", status_code=303)
    response.set_cookie("access_token", token, httponly=True, max_age=60*24*7*60)
    return {"status": "ok", "token": token}
