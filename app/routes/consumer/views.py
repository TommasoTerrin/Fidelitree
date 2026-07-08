"""
Route per il frontend lato consumatore.
Gestisce il caricamento dei template Jinja2 per il download e la visualizzazione delle card.
"""

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session
import uuid

from app.core.dependencies import get_session
from app.models.models import Merchant, Card

router = APIRouter(tags=["Consumer Frontend"])
templates = Jinja2Templates(directory="app/templates")


# 1. PAGINA DI DOWNLOAD DELLA CARD
@router.get("/download_card", response_class=HTMLResponse)
async def download_card(request: Request):
    """Serve la pagina per ottenere una nuova carta fedeltà."""
    return templates.TemplateResponse(
        request=request,
        name="consumer/download.html"
    )


# 2. VISUALIZZAZIONE DI UNA SPECIFICA CARD (con QR e saldo cashback)
@router.get("/card/{card_id}", response_class=HTMLResponse)
async def view_card(request: Request, card_id: uuid.UUID, session: Session = Depends(get_session)):
    """Mostra la carta al consumer con saldo cashback e QR code."""
    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card non trovata")

    merchant = session.get(Merchant, card.merchant_id)
    return templates.TemplateResponse(
        request=request,
        name="consumer/card.html",
        context={
            "card": card,
            "merchant": merchant,
            "full_url": str(request.url),  # URL per il QR code
        },
    )
