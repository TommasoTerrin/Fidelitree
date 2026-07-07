"""
Test di validazione pura dei modelli (nessun database).
"""

import pytest
from pydantic import ValidationError

from app.models.models import Merchant, Card


def test_merchant_valido():
    m = Merchant.model_validate({
        "business_name": "Bar Prova",
        "phone_number": "+393331234567",
        "password": "segreta",
    })
    assert m.type == "test"  # default


def test_merchant_type_non_ammesso():
    with pytest.raises(ValidationError):
        Merchant.model_validate({
            "business_name": "Bar Prova",
            "phone_number": "+393331234567",
            "password": "segreta",
            "type": "platinum",
        })


@pytest.mark.parametrize("phone", [
    "3331234567",        # manca +39
    "+39abc1234567",     # non numerico
    "+3933312",          # troppo corto
    "+39333123456789",   # troppo lungo
])
def test_merchant_telefono_non_valido(phone):
    with pytest.raises(ValidationError):
        Merchant.model_validate({
            "business_name": "Bar Prova",
            "phone_number": phone,
            "password": "segreta",
        })


def test_card_default():
    card = Card(merchant_id=1)
    assert card.cashback_point == 0.0
    assert card.id is not None  # UUID generato automaticamente
