import uuid
import logging

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
# 1. Creazione merchant di test (endpoint di sviluppo)
# ---------------------------------------------------------------------------

@router.post("/create_test_merchant")
async def create_test_merchant(session: Session = Depends(get_session)):
    """Crea un merchant di test usando le credenziali da env.
    Da usare SOLO in sviluppo/staging.
    """
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
    logger.info("Merchant di test creato (id=1).")
    return {"status": "success", "message": "Merchant creato"}


# ---------------------------------------------------------------------------
# 2. Aggiunta punti a una card (logica business + chiamata Humani)
# ---------------------------------------------------------------------------

@router.post("/add-point/{card_id}", response_model=CardResponse)
async def add_point(
    card_id: uuid.UUID,
    body: AddPointsRequest,
    session: Session = Depends(get_session),
    merchant: Merchant = Depends(get_current_merchant),
):
    """Aggiunge punti alla card e pianta alberi quando la soglia viene superata.

    Riceve JSON `{ "points": N }`. Restituisce CardResponse JSON aggiornato.
    """
    # --- Recupero e validazione card ---
    card = session.get(TreeCard, card_id)
    if not card or card.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="TreeCard non valida per questo merchant")

    points = body.points
    if card.current_points + points < 0:
        raise HTTPException(status_code=400, detail="Impossibile portare i punti sotto 0")

    # Applichiamo i punti
    card.current_points += points

    # --- Decifra credenziali Humani del merchant ---
    humani_api = decrypt_key(merchant.humami_api_key)
    humani_enterprise = decrypt_key(merchant.humami_enterprise_id)

    # Nota: SQLAlchemy/SQLModel con Column(JSON) gestiscono trees_list come lista Python nativa.
    # Se per qualche motivo fosse None, resettiamola a lista vuota per sicurezza.
    if card.trees_list is None:
        card.trees_list = []

    humani_errors: list[str] = []

    # --- Ciclo per soddisfare la soglia merchant.points_to_tree ---
    while card.current_points >= merchant.points_to_tree:
        try:
            # Chiamata API Digital Humani
            tree_response = await plant_tree(
                api_key=humani_api,
                enterprise_id=humani_enterprise,
                user=str(card.id),
                project_id="44117777",
                tree_count=1,
            )

            # ESTRATTIAMO SOLO LO UUID (stringa), per evitare errori di validazione Pydantic
            tree_uuid = tree_response.get("uuid")

            if tree_uuid:
                # Modifichiamo la lista e aggiornamo il contatore
                # NOTA: sqlalchemy potrebbe non rilevare modifiche "in-place" su liste JSON.
                # Per stare sicuri, ri-assegnamo il nuovo stato alla fine.
                new_trees = list(card.trees_list)
                new_trees.append(str(tree_uuid))
                card.trees_list = new_trees

                card.trees_planted += 1
                card.current_points -= merchant.points_to_tree
                logger.info("Albero piantato per card %s | uuid=%s", card.id, tree_uuid)
            else:
                msg = "Humani API non ha restituito un UUID"
                logger.warning(msg)
                humani_errors.append(msg)
                break

        except Exception as exc:
            msg = f"Errore chiamata Humani: {exc}"
            logger.error(msg, exc_info=True)
            humani_errors.append(msg)
            break

    # --- Flush e salvataggio ---
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
