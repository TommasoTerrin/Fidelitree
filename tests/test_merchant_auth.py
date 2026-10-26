"""
Test di registrazione, login, impostazioni e gestione admin del merchant
(provider di autenticazione `dev`, SQLite in-memory).
"""

from pathlib import Path

from sqlmodel import select

from app.models.models import Merchant
from tests.conftest import make_card

REGISTER = {
    "business_name": "  Bar Sole ",
    "email": "Bar@Sole.it",
    "password": "password123",
    "contact_phone": "+393331234567",
}


def _register(client, **overrides):
    return client.post("/merchant/register", json={**REGISTER, **overrides})


# --- Registrazione ---

def test_registrazione_valida(client, session, auth_provider):
    resp = _register(client)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success" and body["is_approved"] is False
    assert "access_token" in resp.cookies

    merchant = session.get(Merchant, body["merchant_id"])
    assert merchant.is_approved is False
    assert merchant.type == "free"
    assert merchant.business_name == "Bar Sole"
    assert merchant.email == "bar@sole.it"
    assert merchant.auth_user_id
    assert "password" not in Merchant.model_fields  # nessuna password nel DB


def test_registrazione_email_gia_usata(client, auth_provider):
    assert _register(client).status_code == 200
    resp = _register(client, email="bar@sole.it", business_name="Altro")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Esiste già un account con questa email"


def test_registrazione_email_di_un_merchant_creato_dall_admin(client, merchant, auth_provider):
    assert _register(client, email=merchant.email).status_code == 409


def test_registrazione_dati_non_validi(client, session, auth_provider):
    assert _register(client, email="senza-chiocciola").status_code == 400
    assert _register(client, password="corta").status_code == 400
    assert _register(client, business_name="   ").status_code == 400
    assert _register(client, contact_phone="3331234567").status_code == 400
    assert session.exec(select(Merchant)).all() == []


def test_registrazione_senza_telefono(client, auth_provider):
    resp = client.post("/merchant/register", json={
        "business_name": "Bar", "email": "no-tel@bar.it", "password": "password123",
    })
    assert resp.status_code == 200


# --- Login ---

def test_login_credenziali_giuste(client, auth_provider):
    _register(client)
    client.cookies.clear()
    resp = client.post(
        "/merchant/login", data={"email": " BAR@sole.it", "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/merchant/scanner"
    assert "access_token" in resp.cookies


def test_login_password_errata(client, auth_provider):
    _register(client)
    resp = client.post("/merchant/login", data={"email": "bar@sole.it", "password": "sbagliata1"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Credenziali non valide"


def test_login_email_sconosciuta(client, auth_provider):
    resp = client.post("/merchant/login", data={"email": "nessuno@test.it", "password": "password123"})
    assert resp.status_code == 401


def test_login_identita_valida_ma_non_merchant(client, auth_provider):
    auth_provider.sign_up("cliente@test.it", "password123")
    resp = client.post("/merchant/login", data={"email": "cliente@test.it", "password": "password123"})
    assert resp.status_code == 403


def test_login_richiede_la_password(client, auth_provider):
    assert client.post("/merchant/login", data={"email": "bar@sole.it"}).status_code == 422


def test_merchant_non_approvato_puo_lavorare(client, session, auth_provider):
    """Registrazione → scanner e add-tree-points funzionano anche senza approvazione."""
    merchant_id = _register(client).json()["merchant_id"]
    assert client.get("/merchant/scanner").status_code == 200

    card = make_card(session, session.get(Merchant, merchant_id))

    resp = client.post(f"/api/merchant/add-tree-points/{card.id}", json={"tree_points": 10})
    assert resp.status_code == 200
    assert session.get(Merchant, merchant_id).is_approved is False


# --- Impostazioni del merchant ---

def test_settings_valori_non_validi(auth_client):
    assert auth_client.put("/api/merchant/me/settings", json={"conversion_threshold": 0}).status_code == 422
    assert auth_client.put("/api/merchant/me/settings", json={"conversion_value_eur": -1}).status_code == 422
    assert auth_client.put("/api/merchant/me/settings", json={"business_name": "   "}).status_code == 422


def test_settings_valore_salvato_in_centesimi_e_riletto_in_euro(auth_client, session, merchant):
    resp = auth_client.put("/api/merchant/me/settings", json={"conversion_value_eur": 2.5})
    assert resp.status_code == 200
    session.refresh(merchant)
    assert merchant.conversion_value_cents == 250
    assert auth_client.get("/api/merchant/me").json()["conversion_value_eur"] == 2.5


def test_settings_nome_e_telefono(auth_client):
    resp = auth_client.put("/api/merchant/me/settings", json={
        "business_name": "  Nuovo Nome ", "contact_phone": "+393339876543",
    })
    assert resp.status_code == 200
    assert resp.json()["business_name"] == "Nuovo Nome"
    assert resp.json()["contact_phone"] == "+393339876543"
    assert auth_client.put("/api/merchant/me/settings", json={"contact_phone": "12345"}).status_code == 400


def test_settings_campi_riservati_all_admin_ignorati(auth_client, session, merchant):
    merchant.is_approved = False
    session.add(merchant)
    session.commit()

    resp = auth_client.put("/api/merchant/me/settings", json={
        "conversion_threshold": 60,
        "is_approved": True, "type": "pro", "bronze_threshold": 10,
    })
    assert resp.status_code == 200
    session.refresh(merchant)
    assert merchant.conversion_threshold == 60
    assert merchant.is_approved is False
    assert merchant.type == "test"
    assert merchant.bronze_threshold is None


def test_me_espone_approvazione_e_soglie_effettive(auth_client):
    data = auth_client.get("/api/merchant/me").json()
    assert data["is_approved"] is True
    assert data["effective_thresholds"] == {"bronze": 100, "silver": 300, "gold": 600}


# --- Admin ---

def test_admin_richiede_la_chiave(client, merchant):
    assert client.post(f"/api/merchant/{merchant.id}/approve").status_code == 403
    assert client.put(f"/api/merchant/{merchant.id}", json={"is_approved": True}).status_code == 403


def test_admin_approva_merchant(client, session, merchant, admin_headers):
    merchant.is_approved = False
    session.add(merchant)
    session.commit()

    resp = client.post(f"/api/merchant/{merchant.id}/approve", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["is_approved"] is True
    session.refresh(merchant)
    assert merchant.is_approved is True
    assert client.post("/api/merchant/9999/approve", headers=admin_headers).status_code == 404


def test_admin_override_soglie_visibile_nel_profilo(auth_client, merchant, admin_headers):
    url = f"/api/merchant/{merchant.id}"
    assert auth_client.put(url, headers=admin_headers, json={"bronze_threshold": 50}).status_code == 200
    assert auth_client.get("/api/merchant/me").json()["effective_thresholds"] == {
        "bronze": 50, "silver": 300, "gold": 600,
    }

    # null ripristina il default
    assert auth_client.put(url, headers=admin_headers, json={"bronze_threshold": None}).status_code == 200
    assert auth_client.get("/api/merchant/me").json()["effective_thresholds"]["bronze"] == 100


def test_admin_soglie_incoerenti_rifiutate(client, session, merchant, admin_headers):
    url = f"/api/merchant/{merchant.id}"
    resp = client.put(url, headers=admin_headers, json={"bronze_threshold": 400})  # >= argento (300)
    assert resp.status_code == 400
    session.refresh(merchant)
    assert merchant.bronze_threshold is None

    assert client.put(url, headers=admin_headers, json={"gold_threshold": 200}).status_code == 400
    assert client.put(url, headers=admin_headers, json={
        "bronze_threshold": 10, "silver_threshold": 20, "gold_threshold": 30,
    }).status_code == 200


def test_admin_cambia_tipo(client, merchant, admin_headers):
    resp = client.put(f"/api/merchant/{merchant.id}", headers=admin_headers, json={"type": "pro"})
    assert resp.json()["type"] == "pro"
    assert client.put(f"/api/merchant/{merchant.id}", headers=admin_headers, json={"type": "boh"}).status_code == 422


def test_create_test_merchant_rimosso(client, admin_headers):
    resp = client.post("/api/merchant/create_test_merchant", headers=admin_headers)
    assert resp.status_code in (404, 405, 422)


def test_nessun_riferimento_a_ecologi_nelle_route_merchant():
    root = Path(__file__).resolve().parent.parent / "app" / "routes" / "merchant"
    for path in root.glob("*.py"):
        assert "ecologi" not in path.read_text(encoding="utf-8").lower(), path.name
