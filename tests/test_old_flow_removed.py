"""
Test del ticket 09: il vecchio flusso cliente (OTP, wallet, `/join`, `Customer`) non esiste più e l'unico
modo per avere una carta è il DM Instagram. Include il flusso completo e la cancellazione su richiesta.
"""

import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.core.dependencies import get_current_merchant
from app.main import app
from app.models.models import Card
from app.services.db_crud import merchant_crud
from tests.test_card_page import _request_card

APP_ROOT = Path(__file__).resolve().parent.parent / "app"


# --- Route rimosse ---

@pytest.mark.parametrize("method,path", [
    ("get", "/customer/login"),
    ("get", "/customer/logout"),
    ("get", "/join/1"),
    ("get", "/wallet"),
    ("get", f"/card/{uuid.uuid4()}"),
    ("post", "/api/customer/otp/request"),
    ("post", "/api/customer/otp/verify"),
    ("post", "/api/customer/join/1"),
    ("get", "/api/customer/wallet"),
    ("get", f"/api/card/{uuid.uuid4()}"),
])
def test_route_del_vecchio_flusso_rimosse(client, method, path):
    assert getattr(client, method)(path).status_code == 404


def test_get_card_e_download_card_restano_rimossi(client, merchant):
    assert client.post("/api/get-card", json={"merchant_id": merchant.id}).status_code == 404
    assert client.get("/download_card").status_code == 404


# --- Codice ripulito ---

_OLD_FLOW = re.compile(r"customer|wallet|\botp\b|/join\b", re.IGNORECASE)


def test_il_codice_di_app_non_ha_residui_del_vecchio_flusso():
    for path in APP_ROOT.rglob("*"):
        if path.suffix in {".py", ".html", ".js", ".webmanifest"}:
            match = _OLD_FLOW.search(path.read_text(encoding="utf-8"))
            assert match is None, (path.relative_to(APP_ROOT), match and match.group())


def test_nessun_riferimento_a_whatsapp_nel_codice():
    for path in APP_ROOT.rglob("*"):
        if path.suffix in {".py", ".html", ".js"}:
            assert "whatsapp" not in path.read_text(encoding="utf-8").lower(), path


def test_moduli_e_template_del_vecchio_flusso_cancellati():
    for relative in (
        "services/customer_service.py", "services/db_crud/customer_crud.py", "schemas/customer.py",
        "routes/consumer/auth.py", "routes/consumer/api.py",
        "templates/consumer/login.html", "templates/consumer/join.html", "templates/consumer/wallet.html",
    ):
        assert not (APP_ROOT / relative).exists(), relative


# --- Modello ---

def test_card_senza_igsid_hash_non_si_salva(session, merchant):
    session.add(Card(merchant_id=merchant.id, link_token_hash="tok"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_card_senza_link_token_hash_non_si_salva(session, merchant):
    session.add(Card(merchant_id=merchant.id, igsid_hash="abc"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_card_ha_le_colonne_obbligatorie_e_non_ha_customer():
    columns = Card.__table__.c
    assert columns.igsid_hash.nullable is False
    assert columns.link_token_hash.nullable is False
    assert "customer_id" not in columns
    assert "customer" not in Card.__table__.metadata.tables


# --- Flusso completo ---

def test_flusso_completo_carta_pagina_scan_pagina(client, session, instagram_merchant, zernio_mock):
    """Webhook CARTA → `/c/<token>` → scan +60 tree points del merchant → la pagina mostra conversione e pool."""
    card, token = _request_card(client, session, instagram_merchant, zernio_mock)
    assert "Nessun livello" in client.get(f"/c/{token}").text

    app.dependency_overrides[get_current_merchant] = lambda: instagram_merchant
    resp = client.post(f"/api/merchant/add-tree-points/{card.id}", json={"tree_points": 60})
    assert resp.status_code == 200

    text = client.get(f"/c/{token}").text
    assert "€ 2.00" in text                      # 50 punti → 2 € (soglia e valore di default)
    assert "🌳 10" in text                       # restano 10 tree points
    assert "60 punti questo mese" in text        # la conversione non riduce il pool


# --- Cancellazione su richiesta del cliente ---

def test_eliminata_la_carta_un_nuovo_carta_la_ricrea_a_zero(client, session, instagram_merchant, zernio_mock):
    card, token = _request_card(client, session, instagram_merchant, zernio_mock)
    app.dependency_overrides[get_current_merchant] = lambda: instagram_merchant
    assert client.post(f"/api/merchant/add-tree-points/{card.id}", json={"tree_points": 60}).status_code == 200

    assert client.delete(f"/api/merchant/card/{card.id}").status_code == 200
    session.expire_all()
    assert session.get(Card, card.id) is None
    assert client.get(f"/c/{token}").status_code == 404  # il vecchio link non apre più nulla

    # stesso IGSID, evento diverso (altrimenti la dedup lo scarta): carta nuova, a zero
    new_card, new_token = _request_card(
        client, session, instagram_merchant, zernio_mock, event_id="evt-card-2",
    )
    assert new_card.id != card.id and new_token != token
    assert new_card.tree_points == 0 and new_card.cashback_cents == 0
    assert len(session.exec(select(Card).where(Card.merchant_id == instagram_merchant.id)).all()) == 1


def test_il_merchant_non_elimina_le_carte_di_un_altro_negozio(client, session, instagram_merchant, zernio_mock):
    card, _ = _request_card(client, session, instagram_merchant, zernio_mock)
    altro = merchant_crud.create_merchant(session, {
        "business_name": "Altro", "email": "altro@test.it", "is_approved": True,
    })
    app.dependency_overrides[get_current_merchant] = lambda: altro
    assert client.delete(f"/api/merchant/card/{card.id}").status_code == 404
    session.expire_all()
    assert session.get(Card, card.id) is not None
