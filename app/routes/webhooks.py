"""
Webhook in ingresso: `POST /webhooks/zernio/{hook_id}`.

Un webhook per negozio, con id opaco nel path e secret per negozio. La route legge il corpo **grezzo**
(serve intatto per la firma) e gli header, poi delega tutto a `instagram_service.handle_webhook`. Risponde
sempre 200 `{"status": "ok"}` (nessun dettaglio dell'esito) tranne 404 per `hook_id` sconosciuto e 401 per
firma errata, tradotti dall'handler globale degli errori di dominio.
"""

from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, Request
from sqlmodel import Session

from app.core.clock import utc_now
from app.core.dependencies import get_session
from app.services import instagram_service
from app.services.zernio_service import get_zernio_http

router = APIRouter(tags=["Webhooks"])


@router.post("/webhooks/zernio/{hook_id}", include_in_schema=False)
async def zernio_webhook(
    hook_id: str,
    request: Request,
    x_zernio_signature: Optional[str] = Header(default=None),
    x_zernio_event_id: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
    http: httpx.AsyncClient = Depends(get_zernio_http),
) -> dict:
    """
    Riceve un evento Zernio: firma `X-Zernio-Signature`, dedup su `X-Zernio-Event-Id` (se manca si usa
    `payload.id`). Zernio vuole un 2xx entro 5 secondi: l'elaborazione è sincrona e i timeout verso Zernio
    sono di 3 secondi.
    """
    raw_body = await request.body()
    await instagram_service.handle_webhook(
        session, http, hook_id, raw_body, x_zernio_signature, x_zernio_event_id, utc_now(),
    )
    return {"status": "ok"}
