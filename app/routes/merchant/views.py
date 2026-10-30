"""
Route per il frontend lato esercente.
Gestisce le pagine di registrazione e login, le impostazioni, lo scanner QR e la gestione
manuale dei punti. I dati mostrati (pool del mese, soglie, QR) arrivano dai service.
"""
#
# Endpoint previsti:
#   GET  /merchant/login      → Pagina di login
#   GET  /merchant/register   → Pagina di registrazione
#   GET  /merchant/settings   → Pagina impostazioni (Instagram, conversione, soglie)
#   GET  /merchant/scanner     → Pagina QR scanner
#   GET  /merchant/card/{id}/manage → Pagina gestione punti di una card

from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session
import uuid

from app.core.auth import PasswordAdminProvider, get_auth_provider
from app.core.clock import utc_now
from app.core.dependencies import get_session, get_optional_merchant
from app.models.models import Merchant, Card
from app.services import card_service, merchant_service, tree_service

router = APIRouter(prefix="/merchant", tags=["Merchant Views"])
templates = Jinja2Templates(directory="app/templates")


def _login_redirect() -> RedirectResponse:
    """
    Redirect 303 al login del merchant per le pagine HTML senza sessione valida (cookie assente, scaduto o
    di un account non esercente). Le API `/api/merchant/*` restano 401: qui serve che la PWA installata
    con il cookie scaduto non si apra su un JSON di errore. Nessun parametro `next`.
    """
    return RedirectResponse(url="/merchant/login", status_code=303)


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
    merchant: Optional[Merchant] = Depends(get_optional_merchant),
):
    """
    Serve la pagina impostazioni: conversione, soglie effettive dei livelli (sola lettura),
    stato del servizio (`service_state`: in attesa, attivo, in pausa), sezione Instagram (`instagram` è il pannello: uno stato per volta, mai segreti,
    nessuna chiamata a Zernio) e blocco «Cambia password» (`password_change`, solo se il provider gestisce le password).
    Senza sessione merchant valida → 303 al login.
    """
    if merchant is None:
        return _login_redirect()
    return templates.TemplateResponse(
        request=request,
        name="merchant/settings.html",
        context={
            "merchant": merchant,
            "service_state": card_service.merchant_state(merchant),
            "thresholds": tree_service.effective_thresholds(merchant),
            "instagram": merchant_service.read_instagram_panel(session, merchant, utc_now()),
            "password_change": isinstance(get_auth_provider(), PasswordAdminProvider),
        }
    )

@router.get("/scanner", response_class=HTMLResponse)
async def scanner_page(request: Request, merchant: Optional[Merchant] = Depends(get_optional_merchant)):
    """
    Serve la pagina con il QR scanner, con il banner di stato se il negozio è in attesa o in pausa;
    senza sessione merchant valida → 303 al login.
    """
    if merchant is None:
        return _login_redirect()
    return templates.TemplateResponse(
        request=request, 
        name="merchant/qr_scanner.html", 
        context={"merchant": merchant, "service_state": card_service.merchant_state(merchant)}
    )

@router.get("/card/{card_id}/manage", response_class=HTMLResponse)
async def manage_card_page(
    request: Request, 
    card_id: uuid.UUID, 
    session: Session = Depends(get_session), 
    merchant: Optional[Merchant] = Depends(get_optional_merchant)
):
    """
    Serve la pagina di gestione della card: saldi, pool del mese del negozio, tree points e cashback.
    Se il negozio non è attivo (in attesa o in pausa) mostra il banner e disattiva i pulsanti di aggiunta
    (`can_add`): la rimozione resta attiva.
    Senza sessione merchant valida → 303 al login; carta inesistente o di un altro negozio → 404.
    """
    if merchant is None:
        return _login_redirect()
    card = session.get(Card, card_id)
    if not card or card.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Card non trovata o non associata a questo merchant")
    
    state = card_service.merchant_state(merchant)
    return templates.TemplateResponse(
        request=request, 
        name="merchant/update_card.html", 
        context={
            "card": card,
            "merchant": merchant,
            "service_state": state,
            "can_add": card_service.can_add_balance(state),
            "pool": tree_service.current_pool_progress(session, merchant, utc_now()),
        }
    )
