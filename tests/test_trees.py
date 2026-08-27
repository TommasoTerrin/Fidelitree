"""
Test della feature Tree Points: accumulo punti, piantumazione a soglia,
cap mensile, registrazione self-service e impostazioni merchant.
Le chiamate a Ecologi sono sempre mockate (fixture mock_ecologi).
"""

from sqlmodel import select

from app.models.models import Merchant, TreePlanting
from app.core.security import decrypt_key
from tests.conftest import TEST_PASSWORD, VALID_ECOLOGI_KEY


# ---------------------------------------------------------------------------
# Accumulo e piantumazione
# ---------------------------------------------------------------------------

def test_add_tree_points_richiede_login(client, tree_card):
    resp = client.post(f"/api/merchant/add-tree-points/{tree_card.id}", json={"tree_points": 1})
    assert resp.status_code == 401


def test_accumulo_sotto_soglia_non_pianta(tree_auth_client, tree_card, mock_ecologi):
    resp = tree_auth_client.post(f"/api/merchant/add-tree-points/{tree_card.id}", json={"tree_points": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert data["card"]["tree_points"] == 3
    assert data["planted_now"] == 0
    assert data["warning"] is None
    assert mock_ecologi == []


def test_a_soglia_pianta_un_albero(tree_auth_client, tree_card, mock_ecologi, session):
    # soglia del tree_merchant = 5
    resp = tree_auth_client.post(f"/api/merchant/add-tree-points/{tree_card.id}", json={"tree_points": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert data["planted_now"] == 1
    assert data["card"]["tree_points"] == 0
    assert data["card"]["trees_planted"] == 1

    # la chiamata a Ecologi usa la chiave decifrata e nessun dato personale
    assert len(mock_ecologi) == 1
    assert mock_ecologi[0]["api_key"] == VALID_ECOLOGI_KEY
    assert mock_ecologi[0]["number"] == 1

    # audit trail registrato
    plantings = session.exec(select(TreePlanting)).all()
    assert len(plantings) == 1
    assert plantings[0].tree_count == 1


def test_punti_multipli_piantano_piu_alberi(tree_auth_client, tree_card, mock_ecologi):
    # 12 punti con soglia 5 → 2 alberi, restano 2 punti
    resp = tree_auth_client.post(f"/api/merchant/add-tree-points/{tree_card.id}", json={"tree_points": 12})
    data = resp.json()
    assert data["planted_now"] == 2
    assert data["card"]["tree_points"] == 2
    assert mock_ecologi[0]["number"] == 2


def test_cap_mensile_limita_le_piantumazioni(tree_auth_client, tree_card, mock_ecologi):
    # 25 punti con soglia 5 → 5 alberi dovuti, ma cap mensile = 3
    resp = tree_auth_client.post(f"/api/merchant/add-tree-points/{tree_card.id}", json={"tree_points": 25})
    data = resp.json()
    assert data["planted_now"] == 3
    assert data["warning"] is not None
    # i punti oltre il cap restano accumulati (25 - 3*5 = 10)
    assert data["card"]["tree_points"] == 10

    # a cap esaurito non si pianta più nulla questo mese
    resp = tree_auth_client.post(f"/api/merchant/add-tree-points/{tree_card.id}", json={"tree_points": 0})
    data = resp.json()
    assert data["planted_now"] == 0
    assert "cap" in data["warning"].lower()


def test_punti_non_scendono_sotto_zero(tree_auth_client, tree_card, mock_ecologi):
    resp = tree_auth_client.post(f"/api/merchant/add-tree-points/{tree_card.id}", json={"tree_points": -1})
    assert resp.status_code == 400


def test_senza_chiave_ecologi_i_punti_restano(auth_client, card, mock_ecologi):
    # il merchant "base" della suite non ha la chiave Ecologi configurata
    resp = auth_client.post(f"/api/merchant/add-point/{card.id}", json={"cb_points": 1.0})
    assert resp.status_code == 200  # il cashback continua a funzionare

    resp = auth_client.post(f"/api/merchant/add-tree-points/{card.id}", json={"tree_points": 10})
    data = resp.json()
    assert data["planted_now"] == 0
    assert data["card"]["tree_points"] == 10
    assert "chiave" in data["warning"].lower()
    assert mock_ecologi == []


def test_errore_ecologi_non_perde_punti(tree_auth_client, tree_card, monkeypatch):
    from app.services import ecologi_service

    async def broken_purchase(api_key, number=1, name=None):
        raise ecologi_service.EcologiError("giù")

    monkeypatch.setattr(ecologi_service, "purchase_trees", broken_purchase)

    resp = tree_auth_client.post(f"/api/merchant/add-tree-points/{tree_card.id}", json={"tree_points": 5})
    assert resp.status_code == 200  # lo scan del merchant non fallisce
    data = resp.json()
    assert data["planted_now"] == 0
    assert data["card"]["tree_points"] == 5  # punti conservati
    assert data["warning"] is not None


def test_cashback_bloccato_in_modalita_solo_alberi(client, session, mock_ecologi):
    from app.core.dependencies import get_current_merchant
    from app.main import app
    from app.services.db_crud import merchant_crud
    from app.models.models import Card

    merchant = merchant_crud.create_merchant(session, {
        "business_name": "Solo Alberi",
        "phone_number": "+393330001112",
        "password": TEST_PASSWORD,
        "ecologi_api_key": VALID_ECOLOGI_KEY,
        "mode": "trees",
    })
    card = Card(merchant_id=merchant.id)
    session.add(card)
    session.commit()
    session.refresh(card)

    app.dependency_overrides[get_current_merchant] = lambda: merchant
    try:
        resp = client.post(f"/api/merchant/add-point/{card.id}", json={"cb_points": 1.0})
        assert resp.status_code == 400

        resp = client.post(f"/api/merchant/add-tree-points/{card.id}", json={"tree_points": 1})
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_merchant, None)


# ---------------------------------------------------------------------------
# Registrazione self-service (gate: chiave Ecologi valida)
# ---------------------------------------------------------------------------

REGISTER_PAYLOAD = {
    "business_name": "Bar Verde",
    "phone_number": "+393334445556",
    "password": "password-sicura",
    "ecologi_api_key": VALID_ECOLOGI_KEY,
    "mode": "trees_cashback",
}


def test_registrazione_ok_autentica_subito(client, session, mock_ecologi):
    resp = client.post("/merchant/register", json=REGISTER_PAYLOAD)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert "access_token" in resp.cookies  # auto-login

    merchant = session.exec(
        select(Merchant).where(Merchant.phone_number == REGISTER_PAYLOAD["phone_number"])
    ).first()
    assert merchant is not None
    assert merchant.type == "free"
    # la chiave è salvata cifrata, non in chiaro
    assert merchant.ecologi_api_key != VALID_ECOLOGI_KEY
    assert decrypt_key(merchant.ecologi_api_key) == VALID_ECOLOGI_KEY


def test_registrazione_chiave_ecologi_non_valida(client, mock_ecologi):
    payload = dict(REGISTER_PAYLOAD, ecologi_api_key="chiave-sbagliata")
    resp = client.post("/merchant/register", json=payload)
    assert resp.status_code == 400


def test_registrazione_telefono_duplicato(client, merchant, mock_ecologi):
    payload = dict(REGISTER_PAYLOAD, phone_number=merchant.phone_number)
    resp = client.post("/merchant/register", json=payload)
    assert resp.status_code == 409


def test_registrazione_password_troppo_corta(client, mock_ecologi):
    payload = dict(REGISTER_PAYLOAD, password="corta")
    resp = client.post("/merchant/register", json=payload)
    assert resp.status_code == 422


def test_pagina_registrazione(client):
    resp = client.get("/merchant/register")
    assert resp.status_code == 200
    assert "Ecologi" in resp.text


# ---------------------------------------------------------------------------
# Profilo e impostazioni del merchant autenticato
# ---------------------------------------------------------------------------

def test_me_richiede_login(client):
    assert client.get("/api/merchant/me").status_code == 401


def test_me_espone_configurazione_ma_non_segreti(tree_auth_client):
    resp = tree_auth_client.get("/api/merchant/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "trees_cashback"
    assert data["tree_threshold"] == 5
    assert data["monthly_tree_cap"] == 3
    assert "password" not in data
    assert "ecologi_api_key" not in data


def test_update_settings(tree_auth_client, session, tree_merchant, mock_ecologi):
    resp = tree_auth_client.put("/api/merchant/me/settings", json={
        "mode": "trees",
        "tree_threshold": 8,
        "monthly_tree_cap": 20,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "trees"
    assert data["tree_threshold"] == 8
    assert data["monthly_tree_cap"] == 20


def test_update_settings_chiave_non_valida(tree_auth_client, mock_ecologi):
    resp = tree_auth_client.put("/api/merchant/me/settings", json={
        "ecologi_api_key": "chiave-sbagliata",
    })
    assert resp.status_code == 400


def test_update_settings_soglia_non_valida(tree_auth_client, mock_ecologi):
    resp = tree_auth_client.put("/api/merchant/me/settings", json={"tree_threshold": 0})
    assert resp.status_code == 422
