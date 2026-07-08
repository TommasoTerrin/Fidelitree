"""
Test dei layer CRUD e service su database SQLite in-memory.
"""

import uuid

import pytest
from fastapi import HTTPException

from app.core.security import decrypt_key
from app.services.db_crud import merchant_crud, card_crud
from app.services import card_service
from tests.conftest import TEST_PASSWORD


# ---------------------------------------------------------------------------
# Merchant CRUD
# ---------------------------------------------------------------------------

def test_create_merchant_cifra_password(session, merchant):
    assert merchant.id is not None
    assert merchant.password != TEST_PASSWORD  # mai in chiaro nel DB
    assert decrypt_key(merchant.password) == TEST_PASSWORD


def test_get_e_update_merchant(session, merchant):
    found = merchant_crud.get_merchant_by_id(session, merchant.id)
    assert found.business_name == "Test Merchant"

    updated = merchant_crud.update_merchant(session, found, {"business_name": "Nuovo Nome"})
    assert updated.business_name == "Nuovo Nome"


def test_update_password_viene_ricifrata(session, merchant):
    updated = merchant_crud.update_merchant(session, merchant, {"password": "nuova-password"})
    assert updated.password != "nuova-password"
    assert decrypt_key(updated.password) == "nuova-password"


def test_delete_merchant_cascata_su_card(session, merchant, card):
    merchant_crud.delete_merchant(session, merchant.id)
    assert merchant_crud.get_merchant_by_id(session, merchant.id) is None
    assert card_crud.get_card_by_id(session, card.id) is None  # cascata


def test_delete_merchant_inesistente(session):
    with pytest.raises(HTTPException) as exc:
        merchant_crud.delete_merchant(session, 99999)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Card CRUD + service
# ---------------------------------------------------------------------------

def test_create_card(session, merchant):
    card = card_service.create_card(session, merchant.id)
    assert card.merchant_id == merchant.id
    assert card.cashback_point == 0.0


def test_create_card_merchant_inesistente(session):
    with pytest.raises(HTTPException) as exc:
        card_service.create_card(session, 99999)
    assert exc.value.status_code == 404


def test_update_cashback_aggiunta_e_rimozione(session, merchant, card):
    updated = card_service.update_cashback(session, merchant, card.id, 5.50)
    assert updated.cashback_point == pytest.approx(5.50)

    updated = card_service.update_cashback(session, merchant, card.id, -3.00)
    assert updated.cashback_point == pytest.approx(2.50)


def test_update_cashback_non_va_sotto_zero(session, merchant, card):
    card_service.update_cashback(session, merchant, card.id, 2.0)
    with pytest.raises(HTTPException) as exc:
        card_service.update_cashback(session, merchant, card.id, -5.0)
    assert exc.value.status_code == 400


def test_update_cashback_card_di_altro_merchant(session, merchant, card):
    other = merchant_crud.create_merchant(session, {
        "business_name": "Altro Merchant",
        "phone_number": "+393330000001",
        "password": TEST_PASSWORD,
    })
    with pytest.raises(HTTPException) as exc:
        card_service.update_cashback(session, other, card.id, 1.0)
    assert exc.value.status_code == 404


def test_delete_card(session, card):
    card_crud.delete_card(session, card.id)
    assert card_crud.get_card_by_id(session, card.id) is None


def test_delete_card_inesistente(session):
    with pytest.raises(HTTPException) as exc:
        card_crud.delete_card(session, uuid.uuid4())
    assert exc.value.status_code == 404
