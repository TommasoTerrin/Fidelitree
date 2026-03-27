"""
###############################################################################
# LISTA TEST ESEGUITI IN QUESTO FILE (tests/tests_routes.py)
###############################################################################
# 1. test_health_check: Verifica che l'endpoint /health risponda 200 OK.
# 2. test_merchant_lifecycle_api: 
#    - POST /api/merchant/: Crea un nuovo merchant.
#    - GET /api/merchant/{id}: Recupera il merchant appena creato.
#    - PUT /api/merchant/{id}: Aggiorna il nome del merchant.
#    - DELETE /api/merchant/{id}: Elimina il merchant e verifica la rimozione.
# 3. test_consumer_get_card_api: 
#    - POST /api/get-card: Crea una nuova TreeCard per un merchant esistente.
#    - GET /api/card/{id}: Verifica il recupero della card.
#    - DELETE /api/card/{id}: Pulisce la card creata.
# 4. test_add_points_api (Mock Auth):
#    - POST /api/merchant/add-point/{id}: Testa l'aggiunta punti con mock del merchant corrente.
# 5. test_error_handling_api:
#    - POST /api/merchant/: Verifica errore 422 con dati mancanti.
#    - GET /api/merchant/999999: Verifica errore 404 per merchant inesistente.
#    - GET /api/card/uuid-fittizio: Verifica errore 404 per card inesistente.
###############################################################################
"""

from fastapi.testclient import TestClient
from app.main import app
from app.core.dependencies import get_current_merchant
from app.models.models import Merchant
from app.core.security import encrypt_key
import uuid

client = TestClient(app)

# Mock per bypassare l'autenticazione del merchant nei test delle rotte protette
async def override_get_current_merchant():
    return Merchant(
        id=1,
        business_name="Mock Merchant",
        phone_number="+390000000000",
        password=encrypt_key("hashed_password"),
        humami_api_key=encrypt_key("mock_key"),
        humami_enterprise_id=encrypt_key("mock_id")
    )

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "app": "Fidelitree"}
    print("test_health_check passato")

def test_merchant_lifecycle_api():
    # 1. CREATE
    payload = {
        "business_name": "Route Test Merchant",
        "phone_number": "+399998887770",
        "password": "secretpassword",
        "humami_api_key": "test_api_key_valid",
        "humami_enterprise_id": "test_ent_id_valid",
        "type": "pro"
    }
    response = client.post("/api/merchant/", json=payload)
    assert response.status_code == 200
    merchant_data = response.json()
    merchant_id = merchant_data["id"]
    assert merchant_data["business_name"] == "Route Test Merchant"

    try:
        # 2. READ
        response = client.get(f"/api/merchant/{merchant_id}")
        assert response.status_code == 200
        assert response.json()["business_name"] == "Route Test Merchant"

        # 3. UPDATE
        update_payload = {"business_name": "Updated Route Name"}
        response = client.put(f"/api/merchant/{merchant_id}", json=update_payload)
        assert response.status_code == 200
        assert response.json()["business_name"] == "Updated Route Name"

    finally:
        # 4. DELETE (Cleanup)
        response = client.delete(f"/api/merchant/{merchant_id}")
        assert response.status_code == 200
        
        # Verify deletion
        response = client.get(f"/api/merchant/{merchant_id}")
        assert response.status_code == 404
    print("test_merchant_lifecycle_api passato e pulito")

def test_consumer_get_card_api():
    # Creiamo un merchant temporaneo per la card
    m_payload = {
        "business_name": "Card Owner Merchant",
        "phone_number": "+399998887771",
        "password": "p",
        "humami_api_key": "k",
        "humami_enterprise_id": "i"
    }
    m_resp = client.post("/api/merchant/", json=m_payload)
    m_id = m_resp.json()["id"]

    try:
        # POST /api/get-card
        response = client.post("/api/get-card", json={"merchant_id": m_id})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        card_id = data["card_id"]

        # GET /api/card/{id}
        response = client.get(f"/api/card/{card_id}")
        if response.status_code != 200:
            print(f"DEBUG: Status {response.status_code}, Content: {response.text}")
        assert response.status_code == 200
        assert response.json()["merchant_id"] == m_id

        # Cleanup Card
        client.delete(f"/api/card/{card_id}")
    finally:
        # Cleanup Merchant
        client.delete(f"/api/merchant/{m_id}")
    print("test_consumer_get_card_api passato e pulito")

from app.services.db_crud import merchant_crud
from app.main import engine
from sqlmodel import Session

def test_add_points_api():
    # Override dependency per simulare auth
    app.dependency_overrides[get_current_merchant] = override_get_current_merchant
    
    # Creiamo merchant e card
    m_payload = {
        "business_name": "Auth Merchant", 
        "phone_number": "+399998887772", 
        "password": "p", 
        "humami_api_key": "test_api_key", 
        "humami_enterprise_id": "test_ent_id"
    }
    m_resp = client.post("/api/merchant/", json=m_payload)
    m_id = m_resp.json()["id"]
    
    # Recuperiamo il merchant reale dal DB con tutti i campi (anche quelli non in MerchantResponse)
    with Session(engine) as session:
        real_merchant = merchant_crud.get_merchant_by_id(session, m_id)
        # Detach dal session per usarlo asincronamente nel mock
        session.expunge(real_merchant)
    
    async def override_real_merchant():
        return real_merchant
    app.dependency_overrides[get_current_merchant] = override_real_merchant

    try:
        c_resp = client.post("/api/get-card", json={"merchant_id": m_id})
        card_id = c_resp.json()["card_id"]

        # POST /api/merchant/add-point/{id}
        response = client.post(f"/api/merchant/add-point/{card_id}", json={"points": 5})
        assert response.status_code == 200
        assert response.json()["current_points"] == 5

        # Cleanup Card
        client.delete(f"/api/card/{card_id}")
    finally:
        client.delete(f"/api/merchant/{m_id}")
        del app.dependency_overrides[get_current_merchant]
    print("test_add_points_api (Mock Auth) passato e pulito")

def test_error_handling_api():
    # 1. 422 Unprocessable Entity (dati mancanti)
    response = client.post("/api/merchant/", json={"business_name": "Missing Phone"})
    assert response.status_code == 422
    
    # 2. 404 Not Found (merchant)
    response = client.get("/api/merchant/9999999")
    assert response.status_code == 404

    # 3. 404 Not Found (card)
    fake_uuid = str(uuid.uuid4())
    response = client.get(f"/api/card/{fake_uuid}")
    assert response.status_code == 404
    print("test_error_handling_api passato")

if __name__ == "__main__":
    test_health_check()
    test_merchant_lifecycle_api()
    test_consumer_get_card_api()
    test_add_points_api()
    test_error_handling_api()
    print("\nTutti i test delle rotte completati con successo!")
