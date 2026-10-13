"""
Test del core puro di `customer_service`: email, redirect sicuro e costruzione del wallet (nessun DB).
"""

import uuid

import pytest

from app.core.enums import Level
from app.core.errors import InvalidInputError
from app.services.customer_service import (
    DEFAULT_NEXT_PATH, WalletCardInput, build_wallet, normalize_email, safe_next_path,
)
from app.services.tree_service import LevelThresholds, compute_pool_progress

THRESHOLDS = LevelThresholds(bronze=100, silver=300, gold=600)


def _card(name: str, merchant_id: int, cashback_cents: int = 0, tree_points: int = 0):
    return WalletCardInput(
        card_id=uuid.uuid4(), merchant_id=merchant_id, business_name=name,
        cashback_cents=cashback_cents, tree_points=tree_points,
    )


# --- normalize_email ---

def test_email_normalizzata():
    assert normalize_email("  Mario@Mail.IT ") == "mario@mail.it"


@pytest.mark.parametrize("email", ["mario", "", "   ", "mario@", "@mail.it", "mario@mail", "ma rio@mail.it"])
def test_email_non_valida(email):
    with pytest.raises(InvalidInputError, match="Email non valida"):
        normalize_email(email)


# --- safe_next_path ---

@pytest.mark.parametrize("path", ["/card/abc", "/wallet", "/join/3?x=1"])
def test_next_interno_accettato(path):
    assert safe_next_path(path) == path


@pytest.mark.parametrize("path", [
    None, "", "card/abc", "//evil.com", "https://evil.com", "javascript:alert(1)", "/\\evil.com",
])
def test_next_esterno_o_malformato_scartato(path):
    assert safe_next_path(path) == DEFAULT_NEXT_PATH


# --- build_wallet ---

def test_wallet_vuoto():
    assert build_wallet([], {}) == []


def test_wallet_ordinato_per_nome_con_livello_del_proprio_pool():
    pools = {
        1: compute_pool_progress(350, THRESHOLDS),  # argento
        2: compute_pool_progress(120, THRESHOLDS),  # bronzo
    }
    cards = [_card("Pizzeria Zeta", 1, cashback_cents=250, tree_points=12), _card("bar alfa", 2)]

    wallet = build_wallet(cards, pools)

    assert [e.business_name for e in wallet] == ["bar alfa", "Pizzeria Zeta"]  # senza badare alle maiuscole
    alfa, zeta = wallet
    assert (alfa.level, alfa.pool_points, alfa.points_to_next) == (Level.BRONZE, 120, 180)
    assert (zeta.level, zeta.pool_points, zeta.next_level) == (Level.SILVER, 350, Level.GOLD)
    assert (zeta.cashback_cents, zeta.tree_points) == (250, 12)
    assert zeta.trees_at_month_end == 3


def test_wallet_negozio_senza_pool_livello_none():
    [entry] = build_wallet([_card("Bar", 7)], {})
    assert entry.level == Level.NONE
    assert (entry.pool_points, entry.points_to_next, entry.percent_to_next) == (0, None, 0)
    assert entry.trees_at_month_end == 0


def test_wallet_stesso_nome_ordinato_per_negozio():
    wallet = build_wallet([_card("Bar", 9), _card("Bar", 4)], {})
    assert [e.merchant_id for e in wallet] == [4, 9]
