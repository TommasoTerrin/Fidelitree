"""
Test del core puro di denaro, orologio, enum ed errori (nessun DB, nessun mock).
"""

import ast
import pathlib
from datetime import timedelta, timezone

import pytest

from app.core.clock import utc_now
from app.core.enums import Level, PointTransactionKind
from app.core.money import cents_to_euro, euro_to_cents

CORE_DIR = pathlib.Path(__file__).resolve().parents[2] / "app" / "core"


def test_euro_to_cents_valori_notevoli():
    assert euro_to_cents(2.0) == 200
    assert euro_to_cents(0.1 + 0.2) == 30  # 0.30000000000000004 in float
    assert euro_to_cents(19.99) == 1999
    assert euro_to_cents(0) == 0


def test_euro_to_cents_mezzo_centesimo_arrotonda_per_eccesso():
    assert euro_to_cents(0.005) == 1
    assert euro_to_cents(0.004) == 0


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_euro_to_cents_non_finito(bad):
    with pytest.raises(ValueError):
        euro_to_cents(bad)


def test_cents_to_euro():
    assert cents_to_euro(250) == 2.5
    assert cents_to_euro(0) == 0.0


def test_round_trip_su_10000_centesimi():
    for cents in range(0, 10_001):
        assert euro_to_cents(cents_to_euro(cents)) == cents


def test_utc_now_e_aware_utc():
    now = utc_now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)
    assert now.tzinfo == timezone.utc


def test_enum_valori():
    assert [p.value for p in PointTransactionKind] == ["scan", "conversion"]
    assert [lv.value for lv in Level] == ["none", "bronze", "silver", "gold"]
    assert Level("gold") is Level.GOLD  # str, Enum


@pytest.mark.parametrize("module", ["enums.py", "money.py", "errors.py"])
def test_core_non_importa_framework(module):
    tree = ast.parse((CORE_DIR / module).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"fastapi", "sqlmodel", "sqlalchemy", "httpx"}
