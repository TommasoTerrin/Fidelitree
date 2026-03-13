from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse
from sqlmodel import Session
import uuid
import json

from app.core.dependencies import get_session, get_current_merchant
from app.models.models import Merchant, TreeCard
from app.core.security import encrypt_key, decrypt_key
from app.core.config import settings
from app.services.humani_service import plant_tree

router = APIRouter(prefix="/merchant", tags=["Merchant API"])


# 1. CREAZIONE DI UN NUOVO MERCHANT (endpoint di prova)
@router.post("/create")
async def create_merchant(request: Request, session: Session = Depends(get_session)):
    """Crea un merchant di test prendendo i dati da env."""
    API = settings.HUMANI_SANDBOX_API_KEY
    ENTER = settings.HUMANI_ENTERPRISE_ID
    PASS = settings.MERCHANT_PASSWORD
    
    decrypted_phone = "+391234567890"

    merchant = session.get(Merchant, 1)
    if not merchant:
        new_merchant = Merchant(
            id=1,
            business_name="Test Merchant",
            phone_number=decrypted_phone,
            password=encrypt_key(PASS),
            humami_api_key=encrypt_key(API),
            humami_enterprise_id=encrypt_key(ENTER),
            points_to_tree=10
        )
        session.add(new_merchant)
        session.commit()
        session.refresh(new_merchant)
        return {"status": "success", "message": "Merchant created"}
    return {"status": "success", "message": "Merchant already exists"}


# 2. AGGIUNTA PUNTI A UNA CARD (logica business + futuro Humani)
@router.post("/add-point/{card_id}")
async def add_point(
    card_id: uuid.UUID,
    points: int = Form(...),
    session: Session = Depends(get_session),
    merchant: Merchant = Depends(get_current_merchant)
):
    """Aggiunge punti alla card e pianta alberi se la soglia viene superata."""
    card = session.get(TreeCard, card_id)
    if not card or card.merchant_id != merchant.id:
        raise HTTPException(status_code=404, detail="Treecard non valida per questo merchant")

    # Controlliamo che l'operazione non porti a punti negativi invalidi
    if card.current_points + points < 0:
        raise HTTPException(status_code=400, detail="Impossibile andare sotto a 0 punti")

    card.current_points += points
    
    # Decodifichiamo list uuid in python array
    trees_list = json.loads(card.trees_list)

    # Verifica raggiungimento soglia per piantare alberi
    while card.current_points >= merchant.points_to_tree:
        # Decifriamo le api key del merchant per Humani
        humani_api = decrypt_key(merchant.humami_api_key)
        humani_enterprise = decrypt_key(merchant.humami_enterprise_id)
        
        try:
            # Chiamo Humani API
            tree_response = await plant_tree(
                base_url=settings.HUMANI_SANDBOX_URL,
                api_key=humani_api,
                enterprise_id=humani_enterprise,
                user=str(card.id),
                project_id="44117777",
                tree_count=1
            )
            created_tree_uuid = tree_response.get("uuid")
            if created_tree_uuid:
                trees_list.append(created_tree_uuid)
                card.trees_planted += 1
                card.current_points -= merchant.points_to_tree
                print(f"Albero Piantato per la card {card.id}! UUID Albero: {created_tree_uuid}")
            else:
                raise Exception("Non ho ricevuto lo uuid da Humani")
        except Exception as e:
            print(f"Errore durante l'API Humani: {e}")
            break # Esce dal ciclo se fallisce, così non perdiamo il conto punti
            
    # Salva il nuovo stato JSON strings
    card.trees_list = json.dumps(trees_list)
    
    session.add(card) # Assicuriamoci che l'aggiornamento sia tracciato
    session.commit()
    
    return RedirectResponse(url=f"/merchant/card/{card_id}/manage", status_code=303)
