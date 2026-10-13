"""
Route per il frontend lato cliente.
Gestisce le pagine Jinja2: accesso, ingresso da QR del negozio, wallet e singola carta.
Le pagine riservate mandano al login (con `next`) chi non ha una sessione valida.
"""

from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session
import uuid

from app.core.auth import DEV_OTP_CODE
from app.core.clock import utc_now
from app.core.config import settings
from app.core.dependencies import get_optional_customer, get_session
from app.models.models import Customer, Merchant
from app.services import card_service, customer_service, tree_service

router = APIRouter(tags=["Consumer Frontend"])
templates = Jinja2Templates(directory="app/templates")


def _login_redirect(path: str) -> RedirectResponse:
    """Redirect 303 al login del cliente che, dopo l'accesso, riporta su `path`."""
    return RedirectResponse(url=f"/customer/login?next={quote(path, safe='/')}", status_code=303)


# 1. PAGINA DI ACCESSO (email + OTP)
@router.get("/customer/login", response_class=HTMLResponse)
async def customer_login(request: Request, next: Optional[str] = None):
    """
    Pagina di accesso del cliente; `next` (solo percorsi interni) è dove tornare dopo il login.
    Con `AUTH_PROVIDER=dev` la pagina mostra il codice OTP di sviluppo.
    """
    dev_code = DEV_OTP_CODE if settings.AUTH_PROVIDER == "dev" else None
    return templates.TemplateResponse(
        request=request,
        name="consumer/login.html",
        context={"next": customer_service.safe_next_path(next), "dev_code": dev_code},
    )


# 2. INGRESSO DAL QR STATICO DEL NEGOZIO
@router.get("/join/{merchant_id}", response_class=HTMLResponse)
async def join_page(
    request: Request,
    merchant_id: int,
    customer: Optional[Customer] = Depends(get_optional_customer),
    session: Session = Depends(get_session),
):
    """
    Pagina pubblica del QR del negozio. Il contesto dice se il cliente è già loggato
    (`customer`): in quel caso la pagina può chiamare `POST /api/customer/join/{id}`.
    """
    merchant = session.get(Merchant, merchant_id)
    return templates.TemplateResponse(
        request=request,
        name="consumer/join.html",
        context={"merchant": merchant, "customer": customer, "merchant_id": merchant_id},
        status_code=200 if merchant else 404,  # negozio inesistente: pagina 404 amichevole
    )


# 3. WALLET (tutte le carte del cliente)
@router.get("/wallet", response_class=HTMLResponse)
async def wallet_page(
    request: Request,
    customer: Optional[Customer] = Depends(get_optional_customer),
    session: Session = Depends(get_session),
):
    """Wallet del cliente con le sue carte e il livello di ciascun negozio; senza login → login."""
    if customer is None:
        return _login_redirect("/wallet")
    return templates.TemplateResponse(
        request=request,
        name="consumer/wallet.html",
        context={"customer": customer, "wallet": customer_service.list_wallet(session, customer)},
    )


# 4. VISUALIZZAZIONE DI UNA SPECIFICA CARD (con QR e saldo cashback)
@router.get("/card/{card_id}", response_class=HTMLResponse)
async def view_card(
    request: Request,
    card_id: uuid.UUID,
    customer: Optional[Customer] = Depends(get_optional_customer),
    session: Session = Depends(get_session),
):
    """
    Mostra la carta al suo proprietario con saldo cashback e QR code.
    Senza login → login (con `next`); carta inesistente o altrui → 404.
    """
    if customer is None:
        return _login_redirect(f"/card/{card_id}")
    card = customer_service.get_owned_card(session, customer, card_id)

    merchant = session.get(Merchant, card.merchant_id)
    conversion = (
        card_service.conversion_progress(card.tree_points, merchant.conversion_threshold)
        if merchant.conversion_enabled else None
    )
    return templates.TemplateResponse(
        request=request,
        name="consumer/card.html",
        context={
            "card": card,
            "merchant": merchant,
            "pool": tree_service.current_pool_progress(session, merchant, utc_now()),
            "conversion": conversion,
            "full_url": str(request.url),  # URL per il QR code
        },
    )
