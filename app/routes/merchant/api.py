"""
Endpoint API dedicati agli esercenti (Merchant).

Due livelli di protezione:
- CRUD merchant e approvazione: riservati all'amministratore (header X-Admin-Key).
- Operazioni sulle card: riservate al merchant autenticato (cookie JWT).
"""

import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.dependencies import get_session, get_current_merchant, require_admin_key
from app.core.clock import utc_now
from app.core.money import cents_to_euro
from app.models.models import Merchant
from app.services import card_service, merchant_service, tree_service
from app.services.db_crud import card_crud, merchant_crud
from app.schemas.card import AddPointsRequest, AddTreePointsRequest, CardResponse, ConvertedInfo, ScanResponse
from app.schemas.merchant import (
    MerchantCreateRequest,
    MerchantUpdateRequest,
    MerchantSettingsRequest,
    MerchantResponse,
    MerchantProfileResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/merchant", tags=["Merchant API"])

# ---------------------------------------------------------------------------
# 1. CRUD Merchant (solo amministratore, header X-Admin-Key)
# ---------------------------------------------------------------------------

@router.post("/", response_model=MerchantResponse, dependencies=[Depends(require_admin_key)])
async def create_merchant(
    merchant_in: MerchantCreateRequest,
    session: Session = Depends(get_session),
):
    """Crea un nuovo merchant."""
    return merchant_crud.create_merchant(session, merchant_in.model_dump())


@router.get("/", response_model=list[MerchantResponse], dependencies=[Depends(require_admin_key)])
async def read_merchants(
    skip: int = 0,
    limit: int = 100,
    session: Session = Depends(get_session)
):
    """Restituisce la lista di tutti i merchant."""
    return merchant_crud.get_all_merchants(session, skip, limit)


# ---------------------------------------------------------------------------
# 1b. Profilo e impostazioni del merchant autenticato (cookie JWT).
# NB: dichiarati prima di /{merchant_id} perché "me" non è un int.
# ---------------------------------------------------------------------------

@router.get("/me", response_model=MerchantProfileResponse)
async def read_own_profile(merchant: Merchant = Depends(get_current_merchant)):
    """Profilo del merchant autenticato (senza segreti): include `is_approved` e le soglie effettive."""
    return MerchantProfileResponse(
        **{name: getattr(merchant, name) for name in MerchantResponse.model_fields},
        effective_thresholds=tree_service.effective_thresholds(merchant),
    )


@router.put("/me/settings", response_model=MerchantProfileResponse)
async def update_own_settings(
    body: MerchantSettingsRequest,
    session: Session = Depends(get_session),
    merchant: Merchant = Depends(get_current_merchant),
):
    """
    Aggiorna nome, telefono e impostazioni di conversione del merchant autenticato.
    Il valore arriva in euro (`conversion_value_eur`) e viene salvato in centesimi.
    Approvazione, tipo e soglie dei livelli non sono modificabili da qui.
    """
    merchant = merchant_service.update_own_settings(
        session, merchant, body.model_dump(exclude_unset=True, exclude_none=True),
    )
    return await read_own_profile(merchant)


@router.get("/{merchant_id}", response_model=MerchantResponse, dependencies=[Depends(require_admin_key)])
async def read_merchant(
    merchant_id: int,
    session: Session = Depends(get_session)
):
    """Restituisce un merchant specifico."""
    merchant = merchant_crud.get_merchant_by_id(session, merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant non trovato")
    return merchant


@router.put("/{merchant_id}", response_model=MerchantResponse, dependencies=[Depends(require_admin_key)])
async def update_merchant(
    merchant_id: int,
    merchant_in: MerchantUpdateRequest,
    session: Session = Depends(get_session)
):
    """Aggiorna i dati di un merchant."""
    merchant = merchant_crud.get_merchant_by_id(session, merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant non trovato")
    return merchant_service.update_merchant_as_admin(
        session, merchant, merchant_in.model_dump(exclude_unset=True),
    )


@router.post("/{merchant_id}/approve", response_model=MerchantResponse, dependencies=[Depends(require_admin_key)])
async def approve_merchant(
    merchant_id: int,
    session: Session = Depends(get_session)
):
    """Approva un merchant: da questo momento il suo pool conta per la piantumazione."""
    merchant = merchant_crud.get_merchant_by_id(session, merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant non trovato")
    return merchant_crud.update_merchant(session, merchant, {"is_approved": True})


@router.delete("/{merchant_id}", dependencies=[Depends(require_admin_key)])
async def delete_merchant(
    merchant_id: int,
    session: Session = Depends(get_session)
):
    """Elimina un merchant e, in cascata, carte, movimenti, pool e piantumazioni."""
    merchant_crud.delete_merchant(session, merchant_id)
    return {"status": "success", "message": f"Merchant {merchant_id} eliminato con successo"}


# ---------------------------------------------------------------------------
# 2. Operazioni sulle card (merchant autenticato via cookie JWT)
# ---------------------------------------------------------------------------

@router.post("/add-point/{card_id}", response_model=CardResponse)
async def add_point(
    card_id: uuid.UUID,
    body: AddPointsRequest,
    session: Session = Depends(get_session),
    merchant: Merchant = Depends(get_current_merchant),
):
    """Aggiunge o rimuove credito cashback sulla card del proprio cliente."""
    return card_service.update_cashback(
        session=session,
        merchant=merchant,
        card_id=card_id,
        cb_points=body.cb_points
    )


@router.post("/add-tree-points/{card_id}", response_model=ScanResponse)
async def add_tree_points(
    card_id: uuid.UUID,
    body: AddTreePointsRequest,
    session: Session = Depends(get_session),
    merchant: Merchant = Depends(get_current_merchant),
):
    """Scan: aggiunge o rimuove tree points, aggiorna il pool del mese (non pianta alberi)."""
    now = utc_now()
    result = card_service.add_tree_points(
        session=session,
        merchant=merchant,
        card_id=card_id,
        points=body.tree_points,
        now=now,
    )
    converted = None
    if result.conversions:
        converted = ConvertedInfo(
            conversions=result.conversions,
            cashback_added=cents_to_euro(result.cashback_added_cents),
        )
    return ScanResponse(
        card=result.card,
        converted=converted,
        pool=tree_service.current_pool_progress(session, merchant, now),
    )


@router.delete("/card/{card_id}")
async def delete_card(
    card_id: uuid.UUID,
    session: Session = Depends(get_session),
    merchant: Merchant = Depends(get_current_merchant),
):
    """Elimina una card, solo se appartiene al merchant autenticato."""
    card = card_crud.get_card_by_id(session, card_id)
    if not card or card.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Card non valida per questo merchant")
    card_crud.delete_card(session, card_id)
    return {"status": "success", "message": f"Card {card_id} eliminata con successo"}
