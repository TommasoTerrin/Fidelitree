"""
Test di accesso OTP, iscrizione a un negozio, wallet e proprietà della carta
(provider di autenticazione `dev`, SQLite in-memory).
"""

import uuid

import pytest
from sqlmodel import select

from app.core.auth import DEV_OTP_CODE
from app.main import app
from app.core.dependencies import get_current_merchant
from app.models.models import Card, Customer
from app.services.db_crud import customer_crud, merchant_crud
from tests.conftest import identity_for, login_as


@pytest.fixture()
def altro_merchant(session):
    """Secondo negozio, per i test su più carte."""
    return merchant_crud.create_merchant(session, {
        "business_name": "Altro Negozio", "email": "altro@test.it", "is_approved": True,
    })


def _login(client, email="cliente@test.it"):
    """Autentica il client come cliente `email` (il Customer nasce al primo accesso)."""
    login_as(client, identity_for(email))


def _customers(session):
    return session.exec(select(Customer)).all()


# --- Accesso con OTP ---

def test_otp_request_e_verify_impostano_il_cookie(client, session, auth_provider):
    resp = client.post("/api/customer/otp/request", json={"email": "Cliente@Test.it"})
    assert resp.status_code == 200

    resp = client.post("/api/customer/otp/verify", json={"email": "Cliente@Test.it", "code": DEV_OTP_CODE})
    assert resp.status_code == 200
    assert "access_token" in resp.cookies
    [customer] = _customers(session)
    assert customer.email == "cliente@test.it"
    assert resp.json()["customer_id"] == customer.id

    assert client.get("/api/customer/wallet").status_code == 200  # il cookie vale come sessione


def test_otp_codice_errato(client, session, auth_provider):
    resp = client.post("/api/customer/otp/verify", json={"email": "cliente@test.it", "code": "123456"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Codice non valido"
    assert "access_token" not in resp.cookies
    assert _customers(session) == []


def test_otp_email_non_valida(client, auth_provider):
    assert client.post("/api/customer/otp/request", json={"email": "mario"}).status_code == 400
    resp = client.post("/api/customer/otp/verify", json={"email": "mario", "code": DEV_OTP_CODE})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Email non valida"


def test_secondo_accesso_non_duplica_il_cliente(client, session, auth_provider):
    for _ in range(2):
        client.cookies.clear()
        resp = client.post("/api/customer/otp/verify", json={"email": "cliente@test.it", "code": DEV_OTP_CODE})
        assert resp.status_code == 200
    assert len(_customers(session)) == 1


def test_accesso_collega_un_cliente_gia_presente_senza_identita(client, session, customer, auth_provider):
    assert customer.auth_user_id is None
    client.post("/api/customer/otp/verify", json={"email": customer.email, "code": DEV_OTP_CODE})
    session.refresh(customer)
    assert customer.auth_user_id == identity_for(customer.email).user_id
    assert len(_customers(session)) == 1


def test_logout_cancella_il_cookie(client, auth_provider):
    _login(client)
    resp = client.get("/customer/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/customer/login"
    client.cookies.clear()
    assert client.get("/api/customer/wallet").status_code == 401


# --- Join ---

def test_join_crea_la_carta(client, session, merchant, auth_provider):
    _login(client)
    resp = client.post(f"/api/customer/join/{merchant.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True
    card = session.get(Card, uuid.UUID(body["card_id"]))
    assert card.merchant_id == merchant.id
    assert card.customer_id == customer_crud.get_customer_by_email(session, "cliente@test.it").id


def test_secondo_join_riapre_la_stessa_carta(client, session, merchant, auth_provider):
    _login(client)
    first = client.post(f"/api/customer/join/{merchant.id}").json()
    second = client.post(f"/api/customer/join/{merchant.id}").json()
    assert second == {"card_id": first["card_id"], "created": False}
    assert len(session.exec(select(Card)).all()) == 1


def test_join_su_due_negozi_due_carte_stesso_cliente(client, session, merchant, altro_merchant, auth_provider):
    _login(client)
    a = client.post(f"/api/customer/join/{merchant.id}").json()
    b = client.post(f"/api/customer/join/{altro_merchant.id}").json()
    assert a["card_id"] != b["card_id"]
    cards = session.exec(select(Card)).all()
    assert len(cards) == 2 and len({c.customer_id for c in cards}) == 1


def test_join_merchant_inesistente(client, auth_provider):
    _login(client)
    resp = client.post("/api/customer/join/99999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Merchant non trovato"


def test_join_senza_login(client, merchant, auth_provider):
    assert client.post(f"/api/customer/join/{merchant.id}").status_code == 401


# --- Wallet ---

def test_wallet_senza_login(client, auth_provider):
    assert client.get("/api/customer/wallet").status_code == 401


def test_wallet_vuoto(client, auth_provider):
    _login(client)
    assert client.get("/api/customer/wallet").json() == []


def test_wallet_solo_le_carte_del_cliente_loggato(client, session, merchant, altro_merchant, auth_provider):
    _login(client, "mario@test.it")
    client.post(f"/api/customer/join/{merchant.id}")
    client.post(f"/api/customer/join/{altro_merchant.id}")
    client.cookies.clear()
    _login(client, "luigi@test.it")
    luigi = client.post(f"/api/customer/join/{merchant.id}").json()["card_id"]

    wallet = client.get("/api/customer/wallet").json()
    assert [e["card_id"] for e in wallet] == [luigi]

    client.cookies.clear()
    _login(client, "mario@test.it")
    wallet = client.get("/api/customer/wallet").json()
    assert [e["business_name"] for e in wallet] == ["Altro Negozio", "Test Merchant"]  # ordine per nome


def test_wallet_livello_del_negozio_coerente_col_pool(client, session, merchant, auth_provider):
    """Il pool del negozio è preparato con scan reali; il wallet ne riporta livello e punti mancanti."""
    from app.core.enums import Level
    from app.services import card_service

    _login(client)
    card_id = uuid.UUID(client.post(f"/api/customer/join/{merchant.id}").json()["card_id"])
    merchant.conversion_enabled = False
    session.add(merchant)
    session.commit()
    card_service.add_tree_points(session, merchant, card_id, 120)  # soglie default 100/300/600

    [entry] = client.get("/api/customer/wallet").json()
    assert entry["level"] == Level.BRONZE.value
    assert entry["pool_points"] == 120
    assert entry["points_to_next"] == 180
    assert entry["tree_points"] == 120
    assert entry["cashback_point"] == 0.0


# --- Proprietà della carta ---

def test_api_card_solo_per_il_proprietario(client, card, customer, auth_provider):
    assert client.get(f"/api/card/{card.id}").status_code == 401  # anonimo

    _login(client, customer.email)
    resp = client.get(f"/api/card/{card.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(card.id)

    client.cookies.clear()
    _login(client, "intruso@test.it")
    altrui = client.get(f"/api/card/{card.id}")
    assert altrui.status_code == 404
    inesistente = client.get(f"/api/card/{uuid.uuid4()}")
    assert inesistente.status_code == 404
    assert altrui.json() == inesistente.json()  # non si rivela l'esistenza


def test_pagina_card_anonima_va_al_login(client, card, auth_provider):
    resp = client.get(f"/card/{card.id}", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/customer/login?next=/card/{card.id}"


def test_pagina_card_di_un_altro_cliente_404(client, card, auth_provider):
    _login(client, "intruso@test.it")
    assert client.get(f"/card/{card.id}").status_code == 404


def test_sessione_non_valida_trattata_da_anonimo(client, card, auth_provider):
    client.cookies.set("access_token", "spazzatura")
    assert client.get(f"/card/{card.id}", follow_redirects=False).status_code == 303
    assert client.get(f"/api/card/{card.id}").status_code == 401


# --- Pagine ---

def test_pagina_login_cliente_e_next_sicuro(client, auth_provider):
    resp = client.get("/customer/login?next=/card/abc")
    assert resp.status_code == 200
    assert 'data-next="/card/abc"' in resp.text

    resp = client.get("/customer/login?next=//evil.com")
    assert 'data-next="/wallet"' in resp.text


def test_pagina_join_pubblica(client, merchant, auth_provider):
    resp = client.get(f"/join/{merchant.id}")
    assert resp.status_code == 200
    assert merchant.business_name in resp.text
    assert client.get("/join/99999").status_code == 404


def test_pagina_wallet(client, merchant, auth_provider):
    resp = client.get("/wallet", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/customer/login?next=/wallet"

    _login(client)
    client.post(f"/api/customer/join/{merchant.id}")
    resp = client.get("/wallet")
    assert resp.status_code == 200
    assert merchant.business_name in resp.text


# --- Cosa non esiste più ---

def test_get_card_e_download_card_rimossi(client, merchant, auth_provider):
    assert client.post("/api/get-card", json={"merchant_id": merchant.id}).status_code == 404
    assert client.get("/download_card").status_code == 404


def test_nessun_riferimento_a_whatsapp_nel_codice():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "app"
    for path in root.rglob("*"):
        if path.suffix in {".py", ".html", ".js"}:
            assert "whatsapp" not in path.read_text(encoding="utf-8").lower(), path


# --- Merchant e carte altrui ---

def test_merchant_gestisce_solo_carte_del_proprio_negozio(auth_client, session, card, altro_merchant):
    assert auth_client.get(f"/merchant/card/{card.id}/manage").status_code == 200

    altro_cliente = customer_crud.create_customer(session, "altro-cliente@test.it")
    altra_carta = Card(merchant_id=altro_merchant.id, customer_id=altro_cliente.id)
    session.add(altra_carta)
    session.commit()
    assert auth_client.get(f"/merchant/card/{altra_carta.id}/manage").status_code == 404


# --- End-to-end ---

def test_cliente_entra_il_merchant_assegna_punti_il_wallet_si_aggiorna(
    client, session, merchant, auth_provider,
):
    _login(client)
    card_id = client.post(f"/api/customer/join/{merchant.id}").json()["card_id"]

    # il merchant (stesso DB) assegna 60 tree points: soglia 50 → 1 conversione da € 2,00
    app.dependency_overrides[get_current_merchant] = lambda: merchant
    try:
        resp = client.post(f"/api/merchant/add-tree-points/{card_id}", json={"tree_points": 60})
    finally:
        app.dependency_overrides.pop(get_current_merchant, None)
    assert resp.status_code == 200

    [entry] = client.get("/api/customer/wallet").json()
    assert entry["card_id"] == card_id
    assert entry["pool_points"] == 60       # la conversione non riduce il pool
    assert entry["tree_points"] == 10       # 60 - 50 convertiti
    assert entry["cashback_point"] == 2.0
