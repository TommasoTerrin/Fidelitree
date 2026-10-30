"""
Dashboard admin del founder: `/admin`.

Accesso con `ADMIN_SECRET_KEY` (una sola password, nessun account admin): il form di `/admin/login` imposta il
cookie `admin_session` (JWT con `role=admin`, httpOnly, SameSite=Strict, 12 ore, valido solo sotto `/admin`);
le API accettano anche l'header `X-Admin-Key` (curl, smoke test). Le pagine HTML senza sessione rimandano con
303 al login, le API rispondono 401. I POST con effetto controllano che `Origin` (o `Referer`) sia il nostro
host (403 altrimenti): niente token CSRF a parte. Tutte le risposte portano `Cache-Control: no-store` e
`noindex` (contengono email e telefoni dei merchant). Nessuna risposta riporta chiavi, secret, `hook_id` o hash;
la password temporanea del reset compare solo nella risposta del reset.

Endpoint:
  GET  /admin/login, POST /admin/login, GET /admin/logout
  GET  /admin                                        → pagina con la lista dei merchant
  GET  /admin/api/merchants                          → lista JSON
  POST /admin/api/merchants/{id}/approve|pause|resume|reset-password
"""

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.core.auth import get_auth_provider
from app.core.clock import utc_now
from app.core.dependencies import (
    ADMIN_COOKIE, admin_auth_method, clear_admin_cookie, get_session, require_admin_action, require_admin_session,
    require_same_origin, set_admin_cookie,
)
from app.core.security import is_admin_session_token
from app.schemas.merchant import AdminMerchantsResponse, AdminResetPasswordResponse
from app.services import merchant_service
from app.services.merchant_service import AdminAction, AdminMerchantRow

router = APIRouter(prefix="/admin", tags=["Admin"])
templates = Jinja2Templates(directory="app/templates")

# Pagine e API con dati personali: niente cache, niente indicizzazione. `Referrer-Policy: same-origin` (non
# `no-referrer`): con `no-referrer` il browser manderebbe `Origin: null` sui POST e il controllo CSRF li rifiuterebbe.
_PRIVATE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex",
    "Referrer-Policy": "same-origin",
}


def _private(response: Response) -> None:
    """Aggiunge alla risposta le intestazioni delle pagine riservate (`no-store`, `noindex`)."""
    response.headers.update(_PRIVATE_HEADERS)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Pagina di accesso (un solo campo password). Con una sessione già valida rimanda a `/admin`."""
    if is_admin_session_token(request.cookies.get(ADMIN_COOKIE)):
        return RedirectResponse(url="/admin", status_code=303, headers=_PRIVATE_HEADERS)
    return templates.TemplateResponse(request=request, name="admin/login.html", headers=_PRIVATE_HEADERS)


@router.post("/login", dependencies=[Depends(require_same_origin)])
async def login(password: str = Form(default="")):
    """
    Accesso con `ADMIN_SECRET_KEY`: se giusta imposta il cookie e rimanda (303) a `/admin`. Errori: 401 password
    errata (nessun cookie), 403 origine estranea, 429 dopo 5 errori in 15 minuti (`Retry-After`). La password non
    compare in nessuna risposta o log; il campo mancante vale come errore, non come 422.
    """
    token = merchant_service.login_admin(password, now=utc_now())
    response = RedirectResponse(url="/admin", status_code=303, headers=_PRIVATE_HEADERS)
    set_admin_cookie(response, token)
    return response


@router.get("/logout")
async def logout():
    """Chiude la sessione (cancella il cookie) e torna al login. Il token non è revocabile: scade da solo in 12 ore."""
    response = RedirectResponse(url="/admin/login", status_code=303, headers=_PRIVATE_HEADERS)
    clear_admin_cookie(response)
    return response


@router.get("", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Pagina della dashboard (la lista si carica da `/admin/api/merchants`). Senza sessione → 303 al login."""
    if admin_auth_method(request) is None:
        return RedirectResponse(url="/admin/login", status_code=303, headers=_PRIVATE_HEADERS)
    return templates.TemplateResponse(request=request, name="admin/dashboard.html", headers=_PRIVATE_HEADERS)


@router.get("/api/merchants", response_model=AdminMerchantsResponse, dependencies=[Depends(require_admin_session)])
async def list_merchants(response: Response, session: Session = Depends(get_session)):
    """
    Lista dei merchant dal più recente (al massimo 200): nome attività, email, telefono, iscrizione, stato del
    servizio, stato Instagram, carte e punti del mese. Nessun segreto. 401 senza sessione né `X-Admin-Key`.
    """
    _private(response)
    return AdminMerchantsResponse(merchants=merchant_service.list_admin_merchants(session, utc_now()))


def _change_state(session: Session, merchant_id: int, action: AdminAction) -> AdminMerchantRow:
    """Applica l'azione al merchant (404 se non esiste, 409 per pausa o riattivazione di un negozio in attesa) e ne ritorna la riga."""
    merchant = merchant_service.get_merchant_for_admin(session, merchant_id)
    merchant = merchant_service.set_merchant_state(session, merchant, action)
    return merchant_service.admin_row_for(session, merchant, utc_now())


@router.post("/api/merchants/{merchant_id}/approve", response_model=AdminMerchantRow, dependencies=[Depends(require_admin_action)])
async def approve(merchant_id: int, response: Response, session: Session = Depends(get_session)):
    """Avvia il merchant: lo approva e ne toglie la pausa (diventa attivo). Ritorna la riga aggiornata."""
    _private(response)
    return _change_state(session, merchant_id, AdminAction.APPROVE)


@router.post("/api/merchants/{merchant_id}/pause", response_model=AdminMerchantRow, dependencies=[Depends(require_admin_action)])
async def pause(merchant_id: int, response: Response, session: Session = Depends(get_session)):
    """Mette in pausa un merchant approvato (409 se è ancora in attesa). Ritorna la riga aggiornata."""
    _private(response)
    return _change_state(session, merchant_id, AdminAction.PAUSE)


@router.post("/api/merchants/{merchant_id}/resume", response_model=AdminMerchantRow, dependencies=[Depends(require_admin_action)])
async def resume(merchant_id: int, response: Response, session: Session = Depends(get_session)):
    """Riattiva un merchant approvato e in pausa (409 se è ancora in attesa). Ritorna la riga aggiornata."""
    _private(response)
    return _change_state(session, merchant_id, AdminAction.RESUME)


@router.post(
    "/api/merchants/{merchant_id}/reset-password",
    response_model=AdminResetPasswordResponse,
    dependencies=[Depends(require_admin_action)],
)
async def reset_password(merchant_id: int, response: Response, session: Session = Depends(get_session)):
    """
    Reimposta la password del merchant con una temporanea casuale, mostrata **solo in questa risposta**: le
    sessioni aperte del merchant decadono e il suo freno di login si azzera. 404 id sconosciuto, 409 negozio senza
    credenziale (creato dall'API admin), 400 se il provider non gestisce le password.
    """
    _private(response)
    merchant = merchant_service.get_merchant_for_admin(session, merchant_id)
    temporary = merchant_service.reset_merchant_password(get_auth_provider(), merchant)
    return AdminResetPasswordResponse(merchant_id=merchant.id, temporary_password=temporary)
