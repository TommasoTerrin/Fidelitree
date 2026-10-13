"""
Test del core puro di `merchant_service`: validazione dei dati di registrazione (nessun DB).
"""

import pytest

from app.core.errors import InvalidInputError
from app.services.merchant_service import validate_registration


def _valid(**overrides):
    data = {"business_name": "Bar Sole", "email": "bar@sole.it", "password": "password123"}
    data.update(overrides)
    return validate_registration(**data)


def test_registrazione_valida():
    data = _valid()
    assert (data.business_name, data.email, data.contact_phone) == ("Bar Sole", "bar@sole.it", None)


@pytest.mark.parametrize("email", ["barsole.it", "", "bar@", "@sole.it", "bar@sole", "ba r@sole.it"])
def test_email_non_valida(email):
    with pytest.raises(InvalidInputError, match="Email"):
        _valid(email=email)


def test_email_normalizzata():
    assert _valid(email="  Bar@Sole.IT ").email == "bar@sole.it"


def test_password_troppo_corta():
    with pytest.raises(InvalidInputError, match="password"):
        _valid(password="1234567")
    assert _valid(password="12345678").password == "12345678"


@pytest.mark.parametrize("name", ["", "   "])
def test_nome_vuoto(name):
    with pytest.raises(InvalidInputError, match="nome"):
        _valid(business_name=name)


def test_nome_ripulito_dagli_spazi():
    assert _valid(business_name="  Bar Sole  ").business_name == "Bar Sole"


def test_telefono_facoltativo_e_con_prefisso():
    assert _valid(contact_phone=None).contact_phone is None
    assert _valid(contact_phone="").contact_phone is None
    assert _valid(contact_phone="+393331234567").contact_phone == "+393331234567"
    with pytest.raises(InvalidInputError, match="telefono"):
        _valid(contact_phone="3331234567")
    with pytest.raises(InvalidInputError, match="telefono"):
        _valid(contact_phone="+39123")
