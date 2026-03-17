import uuid
import logging
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.dependencies import get_session, get_current_merchant
from app.models.models import Merchant, TreeCard
from app.core.security import encrypt_key, decrypt_key
from app.core.config import settings
from app.services.humani_service import plant_tree
from app.schemas.card import AddPointsRequest, CardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/merchant", tags=["Merchant API"])

# ---------------------------------------------------------------------------
# Helper robusto per caricare la lista alberi
# ---------------------------------------------------------------------------
def _get_clean_trees_list(card: TreeCard) -> list[str]:
    raw_data = card.trees_list
    
    # Se è già una lista, la usiamo (ma filtriamo eventuali sporcizie)
    if isinstance(raw_data, list):
        actual_list = raw_data
    elif isinstance(raw_data, str) and raw_data.strip():
        try:
            actual_list = json.loads(raw_data)
            # Se dopo il caricamento non è ancora una lista, resettiamo
            if not isinstance(actual_list, list):
                actual_list = []
        except:
            actual_list = []
    else:
        actual_list = []
        
    # PULIZIA: Rimuoviamo elementi spuri tipo '[', ']', '"' che sono finiti dentro
    # a causa del bug precedente nel parsing delle stringhe
    cleaned = [str(t) for t in actual_list if len(str(t)) > 5] # Gli UUID sono lunghi, parentesi e virgolette no
    return cleaned


# ---------------------------------------------------------------------------
# 1. Creazione merchant di test (endpoint di sviluppo)
# ---------------------------------------------------------------------------

@router.post("/create_test_merchant")
async def create_test_merchant(session: Session = Depends(get_session)):
    """Crea un merchant di test usando le credenziali da env."""
    merchant = session.get(Merchant, 1)
    if merchant:
        return {"status": "success", "message": "Merchant già esistente"}

    new_merchant = Merchant(
        id=1,
        business_name="Test Merchant",
        phone_number="+391234567890",
        password=encrypt_key(settings.MERCHANT_PASSWORD),
        humami_api_key=encrypt_key(settings.HUMANI_SANDBOX_API_KEY),
        humami_enterprise_id=encrypt_key(settings.HUMANI_ENTERPRISE_ID),
        points_to_tree=10,
    )
    session.add(new_merchant)
    session.commit()
    session.refresh(new_merchant)
    return {"status": "success", "message": "Merchant creato"}


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
    """Aggiunge punti alla card e pianta alberi."""
    card = session.get(TreeCard, card_id)
    if not card or card.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="TreeCard non valida per questo merchant")

    points = body.points
    if card.current_points + points < 0:
        raise HTTPException(status_code=400, detail="Impossibile portare i punti sotto 0")

    card.current_points += points

    # Decifra credenziali Humani
    humani_api = decrypt_key(merchant.humami_api_key)
    humani_enterprise = decrypt_key(merchant.humami_enterprise_id)

    # Carichiamo la lista in modo sicuro
    current_trees = _get_clean_trees_list(card)
    humani_errors: list[str] = []

    while card.current_points >= merchant.points_to_tree:
        try:
            tree_response = await plant_tree(
                api_key=humani_api,
                enterprise_id=humani_enterprise,
                user=str(card.id),
                project_id="44117777",
                tree_count=1,
            )

            tree_uuid = tree_response.get("uuid")
            if tree_uuid:
                current_trees.append(str(tree_uuid))
                card.trees_planted += 1
                card.current_points -= merchant.points_to_tree
                logger.info("Albero piantato per card %s | uuid=%s", card.id, tree_uuid)
            else:
                humani_errors.append("Humani API: UUID mancante nella risposta")
                break
        except Exception as exc:
            msg = f"Errore Humani: {exc}"
            logger.error(msg)
            humani_errors.append(msg)
            break

    # Salvataggio: ri-assegnamo la lista per far capire a SQLAlchemy che è cambiata
    card.trees_list = current_trees
    
    session.add(card)
    session.commit()
    session.refresh(card)

    return CardResponse(
        id=card.id,
        merchant_id=card.merchant_id,
        current_points=card.current_points,
        trees_planted=card.trees_planted,
        trees_list=card.trees_list,
        warnings=humani_errors if humani_errors else None
    )
