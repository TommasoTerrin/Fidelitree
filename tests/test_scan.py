"""
Test di integrazione dello scan (SQLite in-memory): saldo, registro movimenti,
contatore del pool, conversione automatica in cashback e cashback manuale.
"""

from datetime import datetime, timezone

import pytest
from sqlmodel import select

from app.core.enums import Level, PointTransactionKind
from app.core.errors import InsufficientBalanceError, NotFoundError
from app.models.models import Card, MerchantPool, PointTransaction
from app.services import card_service, tree_service
from app.services.db_crud import customer_crud, merchant_crud

NOW = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)


def _scan(session, merchant, card, points, now=NOW):
    return card_service.add_tree_points(session, merchant, card.id, points, now=now)


def _movements(session, kind=None):
    rows = session.exec(select(PointTransaction).order_by(PointTransaction.id)).all()
    return [r for r in rows if kind is None or r.kind == kind]


def _pool_rows(session):
    return session.exec(select(MerchantPool)).all()


def _new_card(session, merchant, email):
    customer = customer_crud.create_customer(session, email)
    card = Card(merchant_id=merchant.id, customer_id=customer.id)
    session.add(card)
    session.commit()
    session.refresh(card)
    return card


def _other_merchant(session):
    return merchant_crud.create_merchant(session, {
        "business_name": "Altro", "email": "altro@test.it", "is_approved": True,
    })


# --- scan: saldo, registro, pool ---

def test_scan_senza_conversione(session, merchant, card):
    result = _scan(session, merchant, card, 20)
    assert result.card.tree_points == 20
    assert result.card.cashback_cents == 0
    assert result.conversions == 0
    movs = _movements(session)
    assert [(m.kind, m.delta) for m in movs] == [(PointTransactionKind.SCAN, 20)]
    assert tree_service.pool_points(session, merchant.id, "2026-10") == 20
    assert [(p.period, p.points) for p in _pool_rows(session)] == [("2026-10", 20)]


def test_scan_con_conversione_non_riduce_il_pool(session, merchant, card):
    result = _scan(session, merchant, card, 60)
    assert result.card.tree_points == 10
    assert result.card.cashback_cents == 200
    assert result.conversions == 1
    assert result.cashback_added_cents == 200
    movs = _movements(session)
    assert [(m.kind, m.delta) for m in movs] == [
        (PointTransactionKind.SCAN, 60),
        (PointTransactionKind.CONVERSION, -50),
    ]
    assert tree_service.pool_points(session, merchant.id, "2026-10") == 60


def test_conversione_disattivata(session, merchant, card):
    merchant.conversion_enabled = False
    session.add(merchant)
    session.commit()
    result = _scan(session, merchant, card, 120)
    assert result.card.tree_points == 120
    assert result.card.cashback_cents == 0
    assert _movements(session, PointTransactionKind.CONVERSION) == []


def test_scan_sotto_zero_rollback(session, merchant, card):
    _scan(session, merchant, card, 20)
    with pytest.raises(InsufficientBalanceError, match="Impossibile portare i tree points sotto 0"):
        _scan(session, merchant, card, -30)
    session.expire_all()
    assert session.get(Card, card.id).tree_points == 20
    assert len(_movements(session)) == 1
    assert tree_service.pool_points(session, merchant.id, "2026-10") == 20


def test_scan_negativo_riduce_il_pool(session, merchant, card):
    _scan(session, merchant, card, 20)
    result = _scan(session, merchant, card, -10)
    assert result.card.tree_points == 10
    assert _movements(session)[-1].delta == -10
    assert tree_service.pool_points(session, merchant.id, "2026-10") == 10


def test_periodo_fissato_in_scrittura(session, merchant, card):
    _scan(session, merchant, card, 5, now=datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc))
    _scan(session, merchant, card, 7, now=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc))
    assert [m.period for m in _movements(session)] == ["2026-09", "2026-10"]
    pools = {p.period: p.points for p in _pool_rows(session)}
    assert pools == {"2026-09": 5, "2026-10": 7}


def test_pool_points_isolamento(session, merchant, card):
    assert tree_service.pool_points(session, merchant.id, "2026-10") == 0
    other = _other_merchant(session)
    other_card = _new_card(session, other, "x@test.it")
    _scan(session, merchant, card, 11)
    _scan(session, other, other_card, 4)
    _scan(session, merchant, card, 2, now=datetime(2026, 11, 2, tzinfo=timezone.utc))
    assert tree_service.pool_points(session, merchant.id, "2026-10") == 11
    assert tree_service.pool_points(session, other.id, "2026-10") == 4
    assert tree_service.pool_points(session, merchant.id, "2026-11") == 2


def test_coerenza_contatore_registro(session, merchant, card):
    other = _other_merchant(session)
    other_card = _new_card(session, other, "y@test.it")
    sep = datetime(2026, 9, 15, tzinfo=timezone.utc)
    _scan(session, merchant, card, 30)
    _scan(session, merchant, card, 40)     # converte
    _scan(session, merchant, card, -5)
    _scan(session, merchant, card, 8, now=sep)
    _scan(session, other, other_card, 55)  # converte
    _scan(session, other, other_card, 3, now=sep)
    for pool in _pool_rows(session):
        total = sum(
            m.delta for m in _movements(session, PointTransactionKind.SCAN)
            if m.merchant_id == pool.merchant_id and m.period == pool.period
        )
        assert pool.points == total


def test_scan_ripetuti_nessun_aggiornamento_perso(session, merchant, card):
    merchant.conversion_enabled = False
    session.add(merchant)
    session.commit()
    for _ in range(20):
        _scan(session, merchant, card, 3)
    assert tree_service.pool_points(session, merchant.id, "2026-10") == 60
    assert len(_pool_rows(session)) == 1


def test_carta_di_altro_merchant(session, merchant, card):
    other = _other_merchant(session)
    with pytest.raises(NotFoundError, match="Card non valida per questo merchant"):
        card_service.add_tree_points(session, other, card.id, 1, now=NOW)


def test_current_pool_progress_con_override(session, merchant, card):
    merchant.bronze_threshold, merchant.silver_threshold, merchant.gold_threshold = 10, 20, 30
    session.add(merchant)
    session.commit()
    _scan(session, merchant, card, 15)
    progress = tree_service.current_pool_progress(session, merchant, NOW)
    assert progress.points == 15
    assert progress.level == Level.BRONZE
    assert progress.points_to_next == 5


# --- cashback manuale ---

def test_cashback_manuale_con_conversione_disattivata(session, merchant, card):
    merchant.conversion_enabled = False
    session.add(merchant)
    session.commit()
    updated = card_service.update_cashback(session, merchant, card.id, 19.99)
    assert updated.cashback_cents == 1999
    with pytest.raises(InsufficientBalanceError):
        card_service.update_cashback(session, merchant, card.id, -50.0)


# --- route ---

def test_route_richiede_login(client, card):
    resp = client.post(f"/api/merchant/add-tree-points/{card.id}", json={"tree_points": 1})
    assert resp.status_code == 401


def test_route_scan_senza_conversione(auth_client, card, mock_ecologi):
    resp = auth_client.post(f"/api/merchant/add-tree-points/{card.id}", json={"tree_points": 20})
    assert resp.status_code == 200
    body = resp.json()
    assert body["card"]["tree_points"] == 20
    assert body["converted"] is None
    assert body["pool"]["points"] == 20
    assert "planted_now" not in body and "warning" not in body
    assert mock_ecologi == []


def test_route_scan_con_conversione(auth_client, card):
    resp = auth_client.post(f"/api/merchant/add-tree-points/{card.id}", json={"tree_points": 60})
    body = resp.json()
    assert body["converted"] == {"conversions": 1, "cashback_added": 2.0}
    assert body["card"]["cashback_point"] == 2.0
    assert body["pool"]["points"] == 60
    assert body["pool"]["level"] == "none"  # 60 < soglia bronzo di default (100)


def test_route_sotto_zero_400(auth_client, card):
    resp = auth_client.post(f"/api/merchant/add-tree-points/{card.id}", json={"tree_points": -1})
    assert resp.status_code == 400


def test_route_carta_altrui_404(client, card, session):
    from app.core.dependencies import get_current_merchant
    from app.main import app
    other = _other_merchant(session)
    app.dependency_overrides[get_current_merchant] = lambda: other
    try:
        resp = client.post(f"/api/merchant/add-tree-points/{card.id}", json={"tree_points": 1})
    finally:
        app.dependency_overrides.pop(get_current_merchant, None)
    assert resp.status_code == 404
