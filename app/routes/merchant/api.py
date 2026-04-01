import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.dependencies import get_session, get_current_merchant
from app.models.models import Merchant
from app.core.security import encrypt_key
from app.core.config import settings
from app.services import card_service
from app.services.db_crud import merchant_crud
from app.schemas.card import AddPointsRequest, CardResponse
from app.schemas.merchant import MerchantCreateRequest, MerchantUpdateRequest, MerchantResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/merchant", tags=["Merchant API"])

# ---------------------------------------------------------------------------
# 1. CRUD Operazioni per Merchant
# ---------------------------------------------------------------------------

@router.post("/", response_model=MerchantResponse)
async def create_merchant(
    merchant_in: MerchantCreateRequest,
    session: Session = Depends(get_session)
):
    """Crea un nuovo merchant tramite CRUD service."""
    return merchant_crud.create_merchant(session, merchant_in.model_dump())


@router.get("/", response_model=list[MerchantResponse])
async def read_merchants(
    skip: int = 0,
    limit: int = 100,
    session: Session = Depends(get_session)
):
    """Restituisce la lista di tutti i merchant tramite CRUD service."""
    return merchant_crud.get_all_merchants(session, skip, limit)


@router.get("/{merchant_id}", response_model=MerchantResponse)
async def read_merchant(
    merchant_id: int,
    session: Session = Depends(get_session)
):
    """Restituisce un merchant specifico tramite CRUD service."""
    merchant = merchant_crud.get_merchant_by_id(session, merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant non trovato")
    return merchant


@router.put("/{merchant_id}", response_model=MerchantResponse)
async def update_merchant(
    merchant_id: int,
    merchant_in: MerchantUpdateRequest,
    session: Session = Depends(get_session)
):
    """Aggiorna i dati di un merchant tramite CRUD service."""
    merchant = merchant_crud.get_merchant_by_id(session, merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant non trovato")
    return merchant_crud.update_merchant(session, merchant, merchant_in.model_dump(exclude_unset=True))


@router.delete("/{merchant_id}")
async def delete_merchant(
    merchant_id: int,
    session: Session = Depends(get_session)
):
    """Elimina un merchant tramite CRUD service."""
    merchant_crud.delete_merchant(session, merchant_id)
    return {"status": "success", "message": f"Merchant {merchant_id} eliminato con successo"}


# ---------------------------------------------------------------------------
# Creazione merchant di test (endpoint di sviluppo)
# ---------------------------------------------------------------------------

@router.post("/create_test_merchant", response_model=MerchantResponse)
async def create_test_merchant(session: Session = Depends(get_session)):
    """Crea un merchant di test usando le credenziali da env."""
    merchant = merchant_crud.get_merchant_by_id(session, 1)
    if merchant:
        return merchant

    test_data = {
        "business_name": "Fidelitree Test",
        "phone_number": "+393319910276",
        "password": settings.MERCHANT_PASSWORD,
        "humami_api_key": settings.HUMANI_SANDBOX_API_KEY,
        "humami_enterprise_id": settings.HUMANI_ENTERPRISE_ID,
        "points_to_tree": 10
    }
    return merchant_crud.create_merchant(session, test_data)


# ---------------------------------------------------------------------------
# 2. Aggiunta punti a una card
# ---------------------------------------------------------------------------

@router.post("/add-point/{card_id}", response_model=CardResponse)
async def add_point(
    card_id: uuid.UUID,
    body: AddPointsRequest,
    session: Session = Depends(get_session),
    merchant: Merchant = Depends(get_current_merchant),
):
    """Aggiunge punti alla card e pianta alberi tramite Business Service."""
    return await card_service.add_points_to_card(
        session=session,
        merchant=merchant,
        card_id=card_id,
        points=body.points,
        cb_points=body.cb_points
    )
