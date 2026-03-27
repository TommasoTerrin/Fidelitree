"""
###############################################################################
# LISTA TEST ESEGUITI IN QUESTO FILE (tests/test_views.py)
###############################################################################
# 1. test_consumer_download_view: GET /download_card (HTML 200)
# 2. test_consumer_card_view: GET /card/{id} (HTML 200)
# 3. test_merchant_login_view: GET /merchant/login (HTML 200)
# 4. test_merchant_scanner_view (Auth): GET /merchant/scanner (HTML 200 con mock)
# 5. test_merchant_manage_card_view (Auth): GET /merchant/card/{id}/manage (HTML 200 con mock)
###############################################################################
"""

from fastapi.testclient import TestClient
from app.main import app, engine
from app.core.dependencies import get_current_merchant
from app.models.models import Merchant, TreeCard
from sqlmodel import Session
import uuid

client = TestClient(app)

# Mock per autenticazione merchant
async def override_get_current_merchant():
    return Merchant(
        id=1,
        business_name="Test Merchant",
        phone_number="+390000000000",
        password="pass",
        humami_api_key="key",
        humami_enterprise_id="id"
    )

def test_consumer_download_view():
    response = client.get("/download_card")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    print("test_consumer_download_view passato")

def test_consumer_card_view():
    # Creiamo un merchant e una card reali nel DB per la view
    with Session(engine) as session:
        m = Merchant(business_name="V", phone_number="+391", password="p", humami_api_key="k", humami_enterprise_id="i")
        session.add(m)
        session.commit()
        session.refresh(m)
        c = TreeCard(merchant_id=m.id)
        session.add(c)
        session.commit()
        session.refresh(c)
        c_id = c.id
        m_id = m.id

    try:
        response = client.get(f"/card/{c_id}")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    finally:
        with Session(engine) as session:
            # Cleanup
            card = session.get(TreeCard, c_id)
            if card: session.delete(card)
            merch = session.get(Merchant, m_id)
            if merch: session.delete(merch)
            session.commit()
    print("test_consumer_card_view passato")

def test_merchant_login_view():
    response = client.get("/merchant/login")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    print("test_merchant_login_view passato")

def test_merchant_scanner_view():
    app.dependency_overrides[get_current_merchant] = override_get_current_merchant
    try:
        response = client.get("/merchant/scanner")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    finally:
        del app.dependency_overrides[get_current_merchant]
    print("test_merchant_scanner_view passato")

def test_merchant_manage_card_view():
    app.dependency_overrides[get_current_merchant] = override_get_current_merchant
    
    # Creiamo dati reali per il test
    with Session(engine) as session:
        m = Merchant(id=1, business_name="V", phone_number="+391", password="p", humami_api_key="k", humami_enterprise_id="i")
        session.add(m)
        session.commit()
        session.refresh(m)
        c = TreeCard(merchant_id=1)
        session.add(c)
        session.commit()
        session.refresh(c)
        c_id = c.id

    try:
        response = client.get(f"/merchant/card/{c_id}/manage")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    finally:
        with Session(engine) as session:
            card = session.get(TreeCard, c_id)
            if card: session.delete(card)
            merch = session.get(Merchant, 1)
            if merch: session.delete(merch)
            session.commit()
        del app.dependency_overrides[get_current_merchant]
    print("test_merchant_manage_card_view passato")

if __name__ == "__main__":
    test_consumer_download_view()
    test_consumer_card_view()
    test_merchant_login_view()
    test_merchant_scanner_view()
    test_merchant_manage_card_view()
    print("\nTutti i test delle views completati con successo!")
