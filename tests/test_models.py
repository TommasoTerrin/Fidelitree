"""
Test dei modelli: validazione pura (senza DB) e vincoli di schema
(SQLite in-memory, fixture `session`).
"""

from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.core.clock import utc_now
from app.core.enums import InstagramStatus, Level, PointTransactionKind, WebhookOutcome
from app.models.models import (
    Card, Merchant, MerchantPool, PointTransaction, ProcessedWebhookEvent,
    TreePlanting, ZernioSendCounter,
)

VALID = {"business_name": "Bar Prova", "email": "bar@prova.it"}


def make_merchant(session, email="bar@prova.it", **extra) -> Merchant:
    """Crea e salva un merchant valido (via model_validate: i validatori girano)."""
    m = Merchant.model_validate({**VALID, "email": email, **extra})
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


def make_card(merchant_id, igsid_hash="h" * 64, **extra) -> Card:
    """Carta con i campi obbligatori; `link_token_hash` ricavato da `igsid_hash` (è unico)."""
    return Card(merchant_id=merchant_id, igsid_hash=igsid_hash, link_token_hash="tok-" + igsid_hash, **extra)


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


def test_email_normalizzata_in_minuscolo():
    assert Merchant.model_validate({**VALID, "email": "  Mario@Bar.IT "}).email == "mario@bar.it"


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
        make_card(1),
        PointTransaction(merchant_id=1, card_id=make_card(1).id,
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
    card = make_card(1)
    assert card.cashback_cents == 0
    assert isinstance(card.cashback_cents, int)
    assert card.tree_points == 0
    assert card.id is not None  # UUID generato automaticamente
    assert "trees_planted" not in Card.model_fields
    assert "cashback_point" not in Card.model_fields


# ---------------------------------------------------------------------------
# Carta via DM Instagram (v0.3.0): Merchant, Card, eventi webhook, contatore quota
# ---------------------------------------------------------------------------

def test_merchant_nuovo_non_ha_instagram_collegato():
    m = Merchant.model_validate(VALID)
    assert m.instagram_status == InstagramStatus.NOT_CONNECTED
    assert m.persistent_menu_set is False
    for field in ("zernio_api_key_enc", "zernio_account_id", "zernio_profile_id", "zernio_team_id",
                  "instagram_username", "webhook_hook_id", "webhook_secret_enc", "zernio_webhook_id",
                  "standby_detected_at", "standby_owner_app_id"):
        assert getattr(m, field) is None


def test_merchant_zernio_account_id_e_hook_id_unici(session):
    make_merchant(session, zernio_account_id="acc1", webhook_hook_id="h1")
    for extra in ({"zernio_account_id": "acc1"}, {"webhook_hook_id": "h1"}):
        with pytest.raises(IntegrityError):
            make_merchant(session, email="altro@prova.it", **extra)
        session.rollback()
    # i NULL non collidono
    make_merchant(session, email="due@prova.it")
    make_merchant(session, email="tre@prova.it")


def test_card_con_i_campi_obbligatori_ha_i_default_attesi(session):
    m = make_merchant(session)
    session.add(make_card(m.id))
    session.commit()
    card = session.exec(select(Card)).one()
    assert card.link_version == 1
    assert card.zernio_conversation_id is None and card.last_inbound_at is None
    assert card.created_at is not None


def test_card_igsid_duplicato_stesso_negozio(session):
    m = make_merchant(session)
    session.add(Card(merchant_id=m.id, igsid_hash="abc", link_token_hash="t1"))
    session.commit()
    session.add(Card(merchant_id=m.id, igsid_hash="abc", link_token_hash="t2"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_card_stesso_igsid_su_due_negozi_ok(session):
    m1, m2 = make_merchant(session), make_merchant(session, email="altro@prova.it")
    session.add(Card(merchant_id=m1.id, igsid_hash="abc", link_token_hash="t1"))
    session.add(Card(merchant_id=m2.id, igsid_hash="abc", link_token_hash="t2"))
    session.commit()
    assert len(session.exec(select(Card)).all()) == 2


def test_card_link_token_hash_unico(session):
    m = make_merchant(session)
    session.add(Card(merchant_id=m.id, igsid_hash="a", link_token_hash="tok"))
    session.commit()
    session.add(Card(merchant_id=m.id, igsid_hash="b", link_token_hash="tok"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_processed_webhook_event_default_e_unicita(session):
    merchant_id = make_merchant(session).id
    session.add(ProcessedWebhookEvent(event_id="evt-1", merchant_id=merchant_id))
    session.commit()
    event = session.exec(select(ProcessedWebhookEvent)).one()
    assert event.outcome == WebhookOutcome.RECEIVED
    assert event.received_at is not None

    session.expunge_all()
    session.add(ProcessedWebhookEvent(event_id="evt-1", merchant_id=merchant_id))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_zernio_send_counter_pk_composta(session):
    session.add(ZernioSendCounter(quota_scope="zernio:t1", period="2026-10"))
    session.commit()
    assert session.exec(select(ZernioSendCounter)).one().sent == 0

    session.expunge_all()
    session.add(ZernioSendCounter(quota_scope="zernio:t1", period="2026-10"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.add(ZernioSendCounter(quota_scope="zernio:t1", period="2026-11"))  # altro mese
    session.add(ZernioSendCounter(quota_scope="zernio:t2", period="2026-10"))  # altro team
    session.commit()


def test_created_at_e_received_at_aware_utc():
    for value in (Card(merchant_id=1).created_at, ProcessedWebhookEvent(event_id="e", merchant_id=1).received_at):
        assert value.tzinfo is not None
        assert value.utcoffset() == timedelta(0)


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
    m = make_merchant(session)
    card = make_card(m.id)
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


def test_cancellare_merchant_elimina_carte_instagram_ed_eventi(session):
    m = make_merchant(session)
    session.add(make_card(m.id, "abc", last_inbound_at=utc_now()))
    session.add(ProcessedWebhookEvent(event_id="evt-1", merchant_id=m.id))
    session.commit()

    session.delete(m)
    session.commit()

    assert session.exec(select(Card)).all() == []
    assert session.exec(select(ProcessedWebhookEvent)).all() == []
