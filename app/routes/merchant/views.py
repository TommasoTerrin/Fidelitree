# app/routes/merchant/views.py
# MERCHANT FRONTEND — Restituisce pagine HTML (Jinja2)
#
# Endpoint previsti:
#   GET  /merchant/login      → Pagina di login
#   GET  /merchant/dashboard   → Dashboard merchant (dopo auth)
#   GET  /merchant/scanner     → Pagina QR scanner
#   GET  /merchant/card/{id}/manage → Pagina gestione punti di una card

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session
import uuid

from app.core.dependencies import get_session, get_current_merchant
from app.models.models import Merchant, TreeCard

router = APIRouter(prefix="/merchant", tags=["Merchant Views"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve la pagina di login del merchant."""
    return templates.TemplateResponse("merchant/login_merchant.html", {"request": request})

@router.get("/scanner", response_class=HTMLResponse)
async def scanner_page(request: Request, merchant: Merchant = Depends(get_current_merchant)):
    """Serve la pagina con il QR scanner."""
    return templates.TemplateResponse("merchant/qr_scanner.html", {"request": request, "merchant": merchant})

@router.get("/card/{card_id}/manage", response_class=HTMLResponse)
async def manage_card_page(
    request: Request, 
    card_id: uuid.UUID, 
    session: Session = Depends(get_session), 
    merchant: Merchant = Depends(get_current_merchant)
):
    """Serve la pagina per aggiungere punti alla singola Treecard."""
    card = session.get(TreeCard, card_id)
    if not card or card.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Card non trovata o non associata a questo merchant")
    
    return templates.TemplateResponse("merchant/update_card.html", {
        "request": request,
        "card": card,
        "merchant": merchant
    })
