"""
Test dei modelli: validazione pura (senza DB) e vincoli di schema
(SQLite in-memory, fixture `session`).
"""

from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.core.enums import Level, PointTransactionKind
from app.models.models import (
    Card, Customer, Merchant, MerchantPool, PointTransaction, TreePlanting,
)

VALID = {"business_name": "Bar Prova", "email": "bar@prova.it"}


def make_merchant(session, email="bar@prova.it", **extra) -> Merchant:
    """Crea e salva un merchant valido (via model_validate: i validatori girano)."""
    m = Merchant.model_validate({**VALID, "email": email, **extra})
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


def make_customer(session, email="cliente@prova.it") -> Customer:
    c = Customer.model_validate({"email": email})
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


# ---------------------------------------------------------------------------
# Merchant: validazione pura
# ---------------------------------------------------------------------------

def test_merchant_valido_con_default():
    m = Merchant.model_validate(VALID)
    assert m.type == "test"
    assert m.is_approved is False
    assert m.conversion_enabled is True
    assert m.conversion_threshold == 50
    assert m.conversion_value_cents == 200
    assert m.contact_phone is None
    assert m.auth_user_id is None
    assert m.bronze_threshold is None


def test_merchant_type_non_ammesso():
    with pytest.raises(ValidationError):
        Merchant.model_validate({**VALID, "type": "platinum"})


def test_merchant_non_ha_piu_i_campi_rimossi():
    for field in ("password", "phone_number", "mode", "ecologi_api_key",
                  "tree_threshold", "monthly_tree_cap"):
        assert field not in Merchant.model_fields


@pytest.mark.parametrize("field,value", [
    ("conversion_threshold", 0),
    ("conversion_value_cents", 0),
    ("conversion_value_cents", -5),
    ("bronze_threshold", 0),
    ("silver_threshold", 0),
    ("gold_threshold", -1),
])
def test_merchant_valori_numerici_non_validi(field, value):
    with pytest.raises(ValidationError):
        Merchant.model_validate({**VALID, field: value})


@pytest.mark.parametrize("phone", [
    "3331234567",        # manca +39
    "+39abc1234567",     # non numerico
    "+3933312",          # troppo corto
    "+39333123456789",   # troppo lungo
    "123",
])
def test_merchant_contact_phone_non_valido(phone):
    with pytest.raises(ValidationError):
        Merchant.model_validate({**VALID, "contact_phone": phone})


def test_merchant_contact_phone_opzionale():
    assert Merchant.model_validate({**VALID, "contact_phone": None}).contact_phone is None
    assert Merchant.model_validate({**VALID, "contact_phone": "+393331234567"}).contact_phone == "+393331234567"


def test_email_normalizzata_in_minuscolo_merchant_e_customer():
    assert Merchant.model_validate({**VALID, "email": "  Mario@Bar.IT "}).email == "mario@bar.it"
    assert Customer.model_validate({"email": "  Mario@Bar.IT "}).email == "mario@bar.it"


def test_email_duplicata_dopo_normalizzazione(session):
    make_merchant(session, email="mario@bar.it")
    with pytest.raises(IntegrityError):
        make_merchant(session, email=" MARIO@bar.it ")
    session.rollback()


# ---------------------------------------------------------------------------
# Timestamp
# ---------------------------------------------------------------------------

def test_created_at_aware_utc():
    for obj in (
        Customer(email="a@b.it"),
        PointTransaction(merchant_id=1, card_id=Card(merchant_id=1, customer_id=1).id,
                         kind=PointTransactionKind.SCAN, delta=1, period="2026-10"),
        TreePlanting(merchant_id=1, period="2026-10", level=Level.BRONZE,
                     tree_count=1, pool_points=100),
    ):
        assert obj.created_at.tzinfo is not None
        assert obj.created_at.utcoffset() == timedelta(0)


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------

def test_card_default():
    card = Card(merchant_id=1, customer_id=1)
    assert card.cashback_cents == 0
    assert isinstance(card.cashback_cents, int)
    assert card.tree_points == 0
    assert card.id is not None  # UUID generato automaticamente
    assert "trees_planted" not in Card.model_fields
    assert "cashback_point" not in Card.model_fields


def test_card_duplicata_stesso_merchant_e_customer(session):
    m, c = make_merchant(session), make_customer(session)
    session.add(Card(merchant_id=m.id, customer_id=c.id))
    session.commit()
    session.add(Card(merchant_id=m.id, customer_id=c.id))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_stesso_customer_su_due_merchant_ok(session):
    m1, m2 = make_merchant(session), make_merchant(session, email="altro@prova.it")
    c = make_customer(session)
    session.add(Card(merchant_id=m1.id, customer_id=c.id))
    session.add(Card(merchant_id=m2.id, customer_id=c.id))
    session.commit()
    assert len(session.exec(select(Card)).all()) == 2


# ---------------------------------------------------------------------------
# TreePlanting
# ---------------------------------------------------------------------------

def _planting(merchant_id, test=False, period="2026-10", **extra):
    return TreePlanting.model_validate({
        "merchant_id": merchant_id, "period": period, "level": Level.SILVER,
        "tree_count": 3, "pool_points": 350, "test": test, **extra,
    })


def test_tree_planting_duplicata_stesso_merchant_period_test(session):
    m = make_merchant(session)
    session.add(_planting(m.id))
    session.commit()
    session.add(_planting(m.id))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_tree_planting_prova_e_vera_coesistono(session):
    m = make_merchant(session)
    session.add(_planting(m.id, test=True))
    session.add(_planting(m.id, test=False))
    session.commit()
    assert len(session.exec(select(TreePlanting)).all()) == 2


def test_tree_planting_level_solo_valori_enum():
    with pytest.raises(ValidationError):
        _planting(1, level="platinum")


def test_tree_planting_snapshot_ed_ecologi_ref(session):
    m = make_merchant(session)
    session.add(_planting(m.id, ecologi_ref="eco-123"))
    session.commit()
    row = session.exec(select(TreePlanting)).one()
    assert row.level == Level.SILVER
    assert row.pool_points == 350
    assert row.ecologi_ref == "eco-123"


# ---------------------------------------------------------------------------
# MerchantPool
# ---------------------------------------------------------------------------

def test_merchant_pool_default_e_unicita(session):
    merchant_id = make_merchant(session).id
    session.add(MerchantPool(merchant_id=merchant_id, period="2026-10"))
    session.commit()
    assert session.exec(select(MerchantPool)).one().points == 0

    session.expunge_all()  # evita il conflitto di identità nella sessione: voglio l'errore del DB
    session.add(MerchantPool(merchant_id=merchant_id, period="2026-10"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.add(MerchantPool(merchant_id=merchant_id, period="2026-11"))  # altro mese: ok
    session.commit()


# ---------------------------------------------------------------------------
# Cascade
# ---------------------------------------------------------------------------

def test_cancellare_merchant_elimina_tutto_il_collegato(session):
    m, c = make_merchant(session), make_customer(session)
    card = Card(merchant_id=m.id, customer_id=c.id)
    session.add(card)
    session.add(PointTransaction(merchant_id=m.id, card_id=card.id,
                                 kind=PointTransactionKind.SCAN, delta=10, period="2026-10"))
    session.add(MerchantPool(merchant_id=m.id, period="2026-10", points=10))
    session.add(_planting(m.id))
    session.commit()

    session.delete(m)
    session.commit()

    for table in (Card, PointTransaction, MerchantPool, TreePlanting):
        assert session.exec(select(table)).all() == []
    assert session.exec(select(Customer)).one()  # il cliente resta


def test_cancellare_customer_elimina_le_sue_carte(session):
    m, c = make_merchant(session), make_customer(session)
    session.add(Card(merchant_id=m.id, customer_id=c.id))
    session.commit()

    session.delete(c)
    session.commit()

    assert session.exec(select(Card)).all() == []
    assert session.exec(select(Merchant)).one()
