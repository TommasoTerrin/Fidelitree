"""
Test dei layer CRUD e service su database SQLite in-memory.
"""

import uuid

import pytest
from fastapi import HTTPException

from app.core.errors import DomainError, InsufficientBalanceError, NotFoundError
from sqlmodel import select

from app.services.db_crud import merchant_crud, card_crud, customer_crud
from app.services import card_service


# ---------------------------------------------------------------------------
# Merchant CRUD
# ---------------------------------------------------------------------------

def test_create_merchant_normalizza_email_e_applica_default(session):
    m = merchant_crud.create_merchant(session, {
        "business_name": "Bar Nuovo", "email": "  Bar@Nuovo.IT ",
    })
    assert m.id is not None
    assert m.email == "bar@nuovo.it"
    assert m.is_approved is False
    assert m.conversion_threshold == 50
    assert m.conversion_value_cents == 200


def test_create_merchant_dati_non_validi(session):
    with pytest.raises(HTTPException) as exc:
        merchant_crud.create_merchant(session, {
            "business_name": "Bar", "email": "a@b.it", "contact_phone": "123",
        })
    assert exc.value.status_code == 400


def test_get_by_email_ignora_maiuscole(session, merchant):
    assert merchant_crud.get_merchant_by_email(session, " MERCHANT@test.IT ").id == merchant.id
    assert merchant_crud.get_merchant_by_email(session, "boh@test.it") is None


def test_get_e_update_merchant(session, merchant):
    found = merchant_crud.get_merchant_by_id(session, merchant.id)
    assert found.business_name == "Test Merchant"

    updated = merchant_crud.update_merchant(session, found, {"business_name": "Nuovo Nome"})
    assert updated.business_name == "Nuovo Nome"


def test_update_merchant_valore_non_valido_non_sporca_la_sessione(session, merchant):
    with pytest.raises(HTTPException) as exc:
        merchant_crud.update_merchant(session, merchant, {"conversion_threshold": 0})
    assert exc.value.status_code == 400
    assert merchant.conversion_threshold == 50


def test_delete_merchant_cascata_su_card(session, merchant, card):
    merchant_crud.delete_merchant(session, merchant.id)
    assert merchant_crud.get_merchant_by_id(session, merchant.id) is None
    assert card_crud.get_card_by_id(session, card.id) is None  # cascata


def test_delete_merchant_inesistente(session):
    with pytest.raises(HTTPException) as exc:
        merchant_crud.delete_merchant(session, 99999)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Customer CRUD
# ---------------------------------------------------------------------------

def test_create_e_get_customer(session):
    c = customer_crud.create_customer(session, "  Mario@Rossi.IT ")
    assert c.email == "mario@rossi.it"
    assert customer_crud.get_customer_by_email(session, "MARIO@rossi.it").id == c.id
    assert customer_crud.get_customer_by_email(session, "altro@rossi.it") is None


# ---------------------------------------------------------------------------
# Card CRUD + service
# ---------------------------------------------------------------------------

def test_update_cashback_aggiunta_e_rimozione(session, merchant, card):
    updated = card_service.update_cashback(session, merchant, card.id, 5.50)
    assert updated.cashback_cents == 550

    updated = card_service.update_cashback(session, merchant, card.id, -3.00)
    assert updated.cashback_cents == 250


def test_update_cashback_centesimi_esatti(session, merchant, card):
    updated = card_service.update_cashback(session, merchant, card.id, 19.99)
    assert updated.cashback_cents == 1999
    assert isinstance(updated.cashback_cents, int)


def test_update_cashback_non_va_sotto_zero(session, merchant, card):
    card_service.update_cashback(session, merchant, card.id, 2.0)
    with pytest.raises(InsufficientBalanceError):
        card_service.update_cashback(session, merchant, card.id, -5.0)


def test_update_cashback_importo_non_finito(session, merchant, card):
    with pytest.raises(DomainError):
        card_service.update_cashback(session, merchant, card.id, float("nan"))


def test_update_cashback_card_di_altro_merchant(session, merchant, card):
    other = merchant_crud.create_merchant(session, {
        "business_name": "Altro Merchant",
        "email": "altro@test.it",
    })
    with pytest.raises(NotFoundError):
        card_service.update_cashback(session, other, card.id, 1.0)


def test_update_cashback_funziona_con_conversione_disattivata(session, merchant, card):
    merchant_crud.update_merchant(session, merchant, {"conversion_enabled": False})
    assert card_service.update_cashback(session, merchant, card.id, 1.0).cashback_cents == 100


def test_delete_card(session, card):
    card_crud.delete_card(session, card.id)
    assert card_crud.get_card_by_id(session, card.id) is None


def test_delete_card_inesistente(session):
    with pytest.raises(HTTPException) as exc:
        card_crud.delete_card(session, uuid.uuid4())
    assert exc.value.status_code == 404
