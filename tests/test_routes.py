"""
Test di integrazione degli endpoint API (TestClient + SQLite in-memory).
Copre autenticazione, protezione admin e flusso cashback completo.
"""

import uuid

from app.models.models import Card


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
        "email": "Bar@Api.it",
    })
    assert resp.status_code == 200
    data = resp.json()
    merchant_id = data["id"]
    assert data["business_name"] == "Bar API"
    assert data["email"] == "bar@api.it"  # normalizzata
    assert data["is_approved"] is False
    assert "password" not in data

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


def test_admin_crea_merchant_gia_approvato(client, admin_headers):
    resp = client.post("/api/merchant/", headers=admin_headers, json={
        "business_name": "Bar Approvato",
        "email": "approvato@bar.it",
        "is_approved": True,
    })
    assert resp.status_code == 200
    assert resp.json()["is_approved"] is True


def test_merchant_contact_phone_non_valido(client, admin_headers):
    resp = client.post("/api/merchant/", headers=admin_headers, json={
        "business_name": "Bar Sbagliato",
        "email": "sbagliato@bar.it",
        "contact_phone": "12345",
    })
    assert resp.status_code == 400


# Registrazione e login merchant: vedi tests/test_merchant_auth.py
# Iscrizione cliente, wallet e proprietà della carta: vedi tests/test_customer.py


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


def test_delete_card_solo_del_proprio_merchant(auth_client, session, card):
    resp = auth_client.delete(f"/api/merchant/card/{uuid.uuid4()}")
    assert resp.status_code == 404

    resp = auth_client.delete(f"/api/merchant/card/{card.id}")
    assert resp.status_code == 200
    assert session.get(Card, card.id) is None
