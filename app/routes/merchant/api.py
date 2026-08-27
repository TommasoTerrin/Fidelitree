"""
Endpoint API dedicati agli esercenti (Merchant).

Due livelli di protezione:
- CRUD merchant: riservato all'amministratore (header X-Admin-Key).
- Operazioni sulle card: riservate al merchant autenticato (cookie JWT).
"""

import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.dependencies import get_session, get_current_merchant, require_admin_key
from app.models.models import Merchant
from app.core.config import settings
from app.services import card_service, tree_service, ecologi_service
from app.services.db_crud import card_crud, merchant_crud
from app.schemas.card import AddPointsRequest, AddTreePointsRequest, CardResponse, TreePointsResponse
from app.schemas.merchant import (
    MerchantCreateRequest,
    MerchantUpdateRequest,
    MerchantSettingsRequest,
    MerchantResponse,
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

@router.get("/me", response_model=MerchantResponse)
async def read_own_profile(merchant: Merchant = Depends(get_current_merchant)):
    """Restituisce il profilo del merchant autenticato (senza segreti)."""
    return merchant


@router.put("/me/settings", response_model=MerchantResponse)
async def update_own_settings(
    body: MerchantSettingsRequest,
    session: Session = Depends(get_session),
    merchant: Merchant = Depends(get_current_merchant),
):
    """
    Aggiorna le impostazioni tree points del merchant autenticato.
    Se viene fornita una nuova chiave Ecologi, viene validata prima di salvarla.
    """
    update_data = body.model_dump(exclude_unset=True, exclude_none=True)

    new_key = update_data.get("ecologi_api_key")
    if new_key:
        try:
            valid = await ecologi_service.validate_api_key(new_key)
        except ecologi_service.EcologiError:
            raise HTTPException(status_code=503, detail="Ecologi non raggiungibile, riprova tra poco")
        if not valid:
            raise HTTPException(status_code=400, detail="Chiave Ecologi non valida")

    return merchant_crud.update_merchant(session, merchant, update_data)


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
    return merchant_crud.update_merchant(session, merchant, merchant_in.model_dump(exclude_unset=True))


@router.delete("/{merchant_id}", dependencies=[Depends(require_admin_key)])
async def delete_merchant(
    merchant_id: int,
    session: Session = Depends(get_session)
):
    """Elimina un merchant e, in cascata, le sue carte."""
    merchant_crud.delete_merchant(session, merchant_id)
    return {"status": "success", "message": f"Merchant {merchant_id} eliminato con successo"}


@router.post("/create_test_merchant", response_model=MerchantResponse, dependencies=[Depends(require_admin_key)])
async def create_test_merchant(session: Session = Depends(get_session)):
    """Crea un merchant di test usando le credenziali da env (idempotente)."""
    merchant = merchant_crud.get_merchant_by_id(session, 1)
    if merchant:
        return merchant

    test_data = {
        "business_name": "Fidelitree Test",
        "phone_number": "+393319910276",
        "password": settings.MERCHANT_PASSWORD,
    }
    return merchant_crud.create_merchant(session, test_data)


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


@router.post("/add-tree-points/{card_id}", response_model=TreePointsResponse)
async def add_tree_points(
    card_id: uuid.UUID,
    body: AddTreePointsRequest,
    session: Session = Depends(get_session),
    merchant: Merchant = Depends(get_current_merchant),
):
    """
    Aggiunge o rimuove tree points sulla card del proprio cliente.
    Al raggiungimento della soglia gli alberi vengono piantati via Ecologi
    (rispettando il cap mensile del merchant).
    """
    card, planted_now, warning = await tree_service.update_tree_points(
        session=session,
        merchant=merchant,
        card_id=card_id,
        points=body.tree_points,
    )
    return TreePointsResponse(card=card, planted_now=planted_now, warning=warning)


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
