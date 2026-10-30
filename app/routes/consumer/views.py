"""
Route per il frontend lato cliente.
Pagina carta `/c/<token>` (link segreto, nessun login), carta di prova `/carta-di-prova` (per i clienti nuovi
dei negozi non ancora approvati) e informativa `/privacy`. Il cliente non ha
account né sessione: la carta nasce da un DM Instagram e si apre solo con il link della card.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.core.clock import utc_now
from app.core.config import settings
from app.core.dependencies import get_session
from app.core.errors import NotFoundError
from app.models.models import Card, Merchant
from app.services import card_service, instagram_service, tree_service

router = APIRouter(tags=["Consumer Frontend"])
templates = Jinja2Templates(directory="app/templates")

# L'URL della pagina carta contiene il segreto e il saldo cambia a ogni scan: niente cache, niente Referer.
CARD_PAGE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


def _card_page_context(session: Session, card: Card) -> dict:
    """
    Contesto della pagina carta: carta, negozio, avanzamento del pool del mese, avanzamento della
    conversione (solo se attiva) e `scan_code`, il contenuto del QR = id della carta (mai il token).
    """
    merchant = session.get(Merchant, card.merchant_id)
    conversion = (
        card_service.conversion_progress(card.tree_points, merchant.conversion_threshold)
        if merchant.conversion_enabled else None
    )
    return {
        "card": card,
        "merchant": merchant,
        "pool": tree_service.current_pool_progress(session, merchant, utc_now()),
        "conversion": conversion,
        "scan_code": str(card.id),
    }


# 1. PAGINA CARTA DAL LINK DELLA CARD (nessun login: il token nel percorso è il segreto)
@router.get("/c/{token}", response_class=HTMLResponse)
async def card_page(request: Request, token: str, session: Session = Depends(get_session)):
    """
    Pagina della carta del cliente: tree points, cashback, livello del pool e QR con l'id della carta.
    Token sconosciuto o revocato → pagina 404 amichevole che non dice se la carta esista.
    """
    try:
        card = instagram_service.get_card_by_link_token(session, token)
    except NotFoundError:
        return templates.TemplateResponse(
            request=request,
            name="consumer/card_not_found.html",
            context={"keyword": settings.INSTAGRAM_CARD_KEYWORD},
            status_code=404,
            headers=CARD_PAGE_HEADERS,
        )
    return templates.TemplateResponse(
        request=request,
        name="consumer/card.html",
        context=_card_page_context(session, card),
        headers=CARD_PAGE_HEADERS,
    )


# 1b. CARTA DI PROVA (pubblica): la riceve il cliente nuovo di un negozio non ancora approvato
@router.get("/carta-di-prova", response_class=HTMLResponse)
async def demo_card_page(request: Request):
    """
    Carta fittizia con valori di esempio: nessuna sessione, nessun dato letto o salvato, nessun QR vero.
    Stessi header della pagina carta (no-store, no-referrer) e `noindex`. Non dipende dallo stato di nessun negozio.
    """
    return templates.TemplateResponse(
        request=request, name="consumer/test_card.html", headers=CARD_PAGE_HEADERS,
    )


# 2. INFORMATIVA PRIVACY (bozza da far verificare al founder)
@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    """Informativa privacy per i clienti, linkata in fondo alla pagina carta."""
    return templates.TemplateResponse(request=request, name="consumer/privacy.html")
