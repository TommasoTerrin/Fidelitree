
"""
Test per l'autenticazione automatica tramite Telegram.
Verifica il corretto funzionamento dei link firmati e della gestione dei cookie.
"""

from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.core.security import generate_telegram_hash, encrypt_key
from app.models.models import Merchant
from app.core.dependencies import get_session

client = TestClient(app)

def test_telegram_auto_login_flow():
    # 1. Creiamo un merchant per il test via API (usando l'header di protezione)
    payload = {
        "business_name": "TG Test Merchant",
        "phone_number": "+391234567890",
        "password": "testpassword",
        "humami_api_key": "k",
        "humami_enterprise_id": "i"
    }
    headers = {"X-Admin-Token": settings.ADMIN_SECRET_KEY}
    response = client.post("/api/merchant/", json=payload, headers=headers)
    assert response.status_code == 200
    merchant_id = response.json()["id"]

    # Associamo manualmente l'id telegram al merchant nel DB per il test
    # (Oppure potremmo usare l'endpoint di login, ma qui testiamo l'auto-login)
    telegram_id = "999888777"
    with next(get_session()) as session:
        merchant = session.get(Merchant, merchant_id)
        merchant.id_telegram = telegram_id
        session.add(merchant)
        session.commit()

    try:
        # 2. Generiamo l'hash corretto
        valid_hash = generate_telegram_hash(telegram_id)
        
        # 3. Test auto-login con hash VALIDO
        response = client.get(f"/merchant/telegram/auto-login?tid={telegram_id}&h={valid_hash}", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/merchant/scanner"
        assert "access_token" in response.cookies

        # 4. Test auto-login con hash INVALIDO
        response = client.get(f"/merchant/telegram/auto-login?tid={telegram_id}&h=wronghash")
        assert response.status_code == 401
        
        # 5. Test auto-login con merchant INESISTENTE (ma hash valido per quel tid)
        fake_tid = "111222333"
        valid_fake_hash = generate_telegram_hash(fake_tid)
        response = client.get(f"/merchant/telegram/auto-login?tid={fake_tid}&h={valid_fake_hash}", follow_redirects=False)
        # Dovrebbe reindirizzare al login per associazione
        assert response.status_code == 303
        assert "/merchant/login" in response.headers["location"]
        assert f"telegram_id={fake_tid}" in response.headers["location"]

    finally:
        # Cleanup
        client.delete(f"/api/merchant/{merchant_id}")

if __name__ == "__main__":
    test_telegram_auto_login_flow()
    print("Test Auth Telegram completato con successo!")
