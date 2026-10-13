"""
Test unitari del core puro di `card_service`: saldi e conversione tree points → cashback.
Nessun DB, nessun mock: solo funzioni pure su interi.
"""

import ast
from pathlib import Path

import pytest

from app.core.errors import InsufficientBalanceError
from app.services import card_service
from app.services.card_service import (
    apply_cashback_delta,
    apply_tree_points_delta,
    compute_conversion,
)


@pytest.mark.parametrize("points, threshold, value, left, conversions, cents", [
    (49, 50, 200, 49, 0, 0),
    (50, 50, 200, 0, 1, 200),
    (130, 50, 200, 30, 2, 400),
    (120, 40, 75, 0, 3, 225),
])
def test_compute_conversion(points, threshold, value, left, conversions, cents):
    result = compute_conversion(points, threshold, value)
    assert result.tree_points_left == left
    assert result.conversions == conversions
    assert result.cashback_added_cents == cents


def test_apply_tree_points_delta():
    assert apply_tree_points_delta(10, -10) == 0
    assert apply_tree_points_delta(0, 5) == 5


def test_apply_tree_points_delta_sotto_zero():
    with pytest.raises(InsufficientBalanceError):
        apply_tree_points_delta(10, -11)


def test_apply_cashback_delta():
    assert apply_cashback_delta(500, -500) == 0
    assert apply_cashback_delta(0, 30) == 30
    assert isinstance(apply_cashback_delta(0, 30), int)


def test_apply_cashback_delta_sotto_zero():
    with pytest.raises(InsufficientBalanceError):
        apply_cashback_delta(500, -501)


def test_core_di_card_service_senza_dipendenze_di_infrastruttura():
    """La parte del modulo prima di `# --- Shell ---` non importa DB, HTTP o framework."""
    source = Path(card_service.__file__).read_text(encoding="utf-8")
    core = source.split("\n# --- Shell ---\n")[0]
    imported = set()
    for node in ast.walk(ast.parse(core)):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"sqlmodel", "httpx", "fastapi", "sqlalchemy"}
    assert "datetime.now" not in core and "utcnow" not in core


@pytest.mark.parametrize("points, threshold, to_next, percent", [
    (0, 50, 50, 0),
    (20, 50, 30, 40),
    (49, 50, 1, 98),
    (50, 50, 0, 100),   # già a soglia: non dovrebbe capitare, ma non esplode
    (-5, 50, 50, 0),    # negativi valgono zero
])
def test_conversion_progress(points, threshold, to_next, percent):
    result = card_service.conversion_progress(points, threshold)
    assert (result.points_to_next, result.percent) == (to_next, percent)
