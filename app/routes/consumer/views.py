# app/routes/consumer/views.py
# CONSUMER FRONTEND — Restituisce pagine HTML (Jinja2)

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session
import uuid

from app.core.dependencies import get_session
from app.models.models import Merchant, TreeCard

router = APIRouter(tags=["Consumer Frontend"])
templates = Jinja2Templates(directory="app/templates")


# 1. PAGINA DI DOWNLOAD DELLA CARD
@router.get("/download_card", response_class=HTMLResponse)
async def download_card(request: Request):
    """Serve la pagina per ottenere una nuova Treecard."""
    return templates.TemplateResponse("consumer/download.html", {"request": request})


# 2. VISUALIZZAZIONE DI UNA SPECIFICA TREECARD (con QR e punti)
@router.get("/card/{card_id}", response_class=HTMLResponse)
async def view_card(request: Request, card_id: uuid.UUID, session: Session = Depends(get_session)):
    """Mostra la Treecard al consumer con barra progresso e QR code."""
    card = session.get(TreeCard, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="TreeCard not found")

    merchant = session.get(Merchant, card.merchant_id)
    return templates.TemplateResponse(
        "consumer/treecard.html",
        {
            "request": request,
            "card": card,
            "merchant": merchant,
            "full_url": str(request.url),  # URL per il QR code
        },
    )