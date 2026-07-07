"""
Test di integrazione degli endpoint API (TestClient + SQLite in-memory).
Copre autenticazione, protezione admin e flusso cashback completo.
"""

import uuid

from tests.conftest import TEST_PASSWORD


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# CRUD Merchant (protetto da X-Admin-Key)
# ---------------------------------------------------------------------------

def test_merchant_crud_richiede_admin_key(client, merchant):
    assert client.get("/api/merchant/").status_code == 403
    assert client.get(f"/api/merchant/{merchant.id}").status_code == 403
    assert client.post("/api/merchant/", json={}).status_code == 403
    assert client.delete(f"/api/merchant/{merchant.id}").status_code == 403


def test_merchant_crud_ciclo_completo(client, admin_headers):
    # Crea
    resp = client.post("/api/merchant/", headers=admin_headers, json={
        "business_name": "Bar API",
        "phone_number": "+393337654321",
        "password": "segreta",
    })
    assert resp.status_code == 200
    data = resp.json()
    merchant_id = data["id"]
    assert data["business_name"] == "Bar API"
    assert "password" not in data  # la risposta non espone la password

    # Leggi
    resp = client.get(f"/api/merchant/{merchant_id}", headers=admin_headers)
    assert resp.status_code == 200

    # Aggiorna
    resp = client.put(f"/api/merchant/{merchant_id}", headers=admin_headers,
                      json={"business_name": "Bar Rinominato"})
    assert resp.status_code == 200
    assert resp.json()["business_name"] == "Bar Rinominato"

    # Elimina
    resp = client.delete(f"/api/merchant/{merchant_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert client.get(f"/api/merchant/{merchant_id}", headers=admin_headers).status_code == 404


def test_merchant_telefono_non_valido(client, admin_headers):
    resp = client.post("/api/merchant/", headers=admin_headers, json={
        "business_name": "Bar Sbagliato",
        "phone_number": "12345",
        "password": "segreta",
    })
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Creazione card lato consumer
# ---------------------------------------------------------------------------

def test_get_card_crea_carta_e_link_whatsapp(client, merchant):
    resp = client.post("/api/get-card", json={"merchant_id": merchant.id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["card_path"] == f"/card/{data['card_id']}"
    assert data["whatsapp_link_template"].startswith("https://wa.me/")


def test_get_card_merchant_inesistente(client):
    resp = client.post("/api/get-card", json={"merchant_id": 99999})
    assert resp.status_code == 404


def test_lettura_card_pubblica(client, card):
    resp = client.get(f"/api/card/{card.id}")
    assert resp.status_code == 200
    assert resp.json()["cashback_point"] == 0.0

    assert client.get(f"/api/card/{uuid.uuid4()}").status_code == 404


# ---------------------------------------------------------------------------
# Login merchant (form + cookie JWT)
# ---------------------------------------------------------------------------

def test_login_corretto_setta_cookie(client, merchant):
    resp = client.post("/merchant/login", data={
        "phone_number": merchant.phone_number,
        "password": TEST_PASSWORD,
    }, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/merchant/scanner"
    assert "access_token" in resp.cookies


def test_login_password_errata(client, merchant):
    resp = client.post("/merchant/login", data={
        "phone_number": merchant.phone_number,
        "password": "sbagliata",
    })
    assert resp.status_code == 401


def test_login_merchant_inesistente(client):
    resp = client.post("/merchant/login", data={
        "phone_number": "+393339999999",
        "password": "qualsiasi",
    })
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Gestione cashback (merchant autenticato)
# ---------------------------------------------------------------------------

def test_add_point_richiede_login(client, card):
    resp = client.post(f"/api/merchant/add-point/{card.id}", json={"cb_points": 1.0})
    assert resp.status_code == 401


def test_flusso_cashback_completo(auth_client, card):
    # Aggiunta
    resp = auth_client.post(f"/api/merchant/add-point/{card.id}", json={"cb_points": 10.0})
    assert resp.status_code == 200
    assert resp.json()["cashback_point"] == 10.0

    # Rimozione parziale
    resp = auth_client.post(f"/api/merchant/add-point/{card.id}", json={"cb_points": -4.0})
    assert resp.status_code == 200
    assert resp.json()["cashback_point"] == 6.0

    # Sotto zero: rifiutato
    resp = auth_client.post(f"/api/merchant/add-point/{card.id}", json={"cb_points": -100.0})
    assert resp.status_code == 400


def test_delete_card_solo_del_proprio_merchant(auth_client, card):
    resp = auth_client.delete(f"/api/merchant/card/{uuid.uuid4()}")
    assert resp.status_code == 404

    resp = auth_client.delete(f"/api/merchant/card/{card.id}")
    assert resp.status_code == 200
    assert auth_client.get(f"/api/card/{card.id}").status_code == 404
