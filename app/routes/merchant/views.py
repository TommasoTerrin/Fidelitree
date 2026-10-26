"""
Route per il frontend lato esercente.
Gestisce le pagine di registrazione e login, le impostazioni, lo scanner QR e la gestione
manuale dei punti. I dati mostrati (pool del mese, soglie, QR) arrivano dai service.
"""
#
# Endpoint previsti:
#   GET  /merchant/login      → Pagina di login
#   GET  /merchant/register   → Pagina di registrazione
#   GET  /merchant/settings   → Pagina impostazioni (Instagram, conversione, soglie, QR del negozio)
#   GET  /merchant/scanner     → Pagina QR scanner
#   GET  /merchant/card/{id}/manage → Pagina gestione punti di una card

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session
import uuid

from app.core.clock import utc_now
from app.core.dependencies import get_session, get_current_merchant
from app.models.models import Merchant, Card
from app.services import merchant_service, tree_service

router = APIRouter(prefix="/merchant", tags=["Merchant Views"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve la pagina di login del merchant."""
    return templates.TemplateResponse(
        request=request,
        name="merchant/login_merchant.html"
    )

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Serve la pagina di registrazione del merchant."""
    return templates.TemplateResponse(
        request=request,
        name="merchant/register_merchant.html"
    )

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    session: Session = Depends(get_session),
    merchant: Merchant = Depends(get_current_merchant),
):
    """
    Serve la pagina impostazioni: conversione, soglie effettive dei livelli (sola lettura),
    stato di approvazione, sezione Instagram (`instagram` è il pannello: uno stato per volta, mai segreti,
    nessuna chiamata a Zernio) e QR del negozio (`join_path` è il percorso che il QR codifica).
    """
    return templates.TemplateResponse(
        request=request,
        name="merchant/settings.html",
        context={
            "merchant": merchant,
            "thresholds": tree_service.effective_thresholds(merchant),
            "instagram": merchant_service.read_instagram_panel(session, merchant, utc_now()),
            "join_path": f"/join/{merchant.id}",
        }
    )

@router.get("/scanner", response_class=HTMLResponse)
async def scanner_page(request: Request, merchant: Merchant = Depends(get_current_merchant)):
    """Serve la pagina con il QR scanner."""
    return templates.TemplateResponse(
        request=request, 
        name="merchant/qr_scanner.html", 
        context={"merchant": merchant}
    )

@router.get("/card/{card_id}/manage", response_class=HTMLResponse)
async def manage_card_page(
    request: Request, 
    card_id: uuid.UUID, 
    session: Session = Depends(get_session), 
    merchant: Merchant = Depends(get_current_merchant)
):
    """Serve la pagina di gestione della card: saldi, pool del mese del negozio, tree points e cashback."""
    card = session.get(Card, card_id)
    if not card or card.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Card non trovata o non associata a questo merchant")
    
    return templates.TemplateResponse(
        request=request, 
        name="merchant/update_card.html", 
        context={
            "card": card,
            "merchant": merchant,
            "pool": tree_service.current_pool_progress(session, merchant, utc_now()),
        }
    )
