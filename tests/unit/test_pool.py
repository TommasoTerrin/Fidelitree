"""
Test del core puro del pool (livelli, periodi, piano di chiusura).
Nessun DB, nessun mock: solo funzioni e modelli Pydantic.
"""

import ast
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.enums import Level
from app.core.errors import InvalidThresholdsError
from app.services import tree_service
from app.services.tree_service import (
    ClosurePlan, LevelThresholds, PoolInput, compute_level, compute_pool_progress,
    period_for, period_label, plan_period_closure, previous_period,
    resolve_thresholds, trees_for_level,
)

T = LevelThresholds(bronze=100, silver=300, gold=600)
UTC = timezone.utc


# ---------------------------------------------------------------------------
# Livelli
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("points,level", [
    (0, Level.NONE), (99, Level.NONE), (100, Level.BRONZE), (299, Level.BRONZE),
    (300, Level.SILVER), (599, Level.SILVER), (600, Level.GOLD),
    (10_000, Level.GOLD), (-5, Level.NONE),
])
def test_compute_level(points, level):
    assert compute_level(points, T) == level


@pytest.mark.parametrize("level,trees", [
    (Level.NONE, 0), (Level.BRONZE, 1), (Level.SILVER, 3), (Level.GOLD, 5),
])
def test_trees_for_level(level, trees):
    assert trees_for_level(level) == trees


def test_trees_per_level_non_cumulativi():
    assert tree_service.TREES_PER_LEVEL == {
        Level.NONE: 0, Level.BRONZE: 1, Level.SILVER: 3, Level.GOLD: 5,
    }


# ---------------------------------------------------------------------------
# Avanzamento
# ---------------------------------------------------------------------------

def test_progress_a_meta_strada():
    p = compute_pool_progress(150, T)
    assert p.points == 150
    assert p.level == Level.BRONZE
    assert p.trees_at_month_end == 1
    assert p.next_level == Level.SILVER
    assert p.points_to_next == 150
    assert p.percent_to_next == 25  # 50 su 200


def test_progress_da_zero():
    p = compute_pool_progress(0, T)
    assert p.level == Level.NONE
    assert p.trees_at_month_end == 0
    assert p.next_level == Level.BRONZE
    assert p.points_to_next == 100
    assert p.percent_to_next == 0


def test_progress_oro():
    p = compute_pool_progress(700, T)
    assert p.level == Level.GOLD
    assert p.trees_at_month_end == 5
    assert p.next_level is None
    assert p.points_to_next is None
    assert p.percent_to_next == 100


def test_progress_punti_negativi_come_zero():
    p = compute_pool_progress(-10, T)
    assert p.points == 0
    assert p.level == Level.NONE
    assert p.points_to_next == 100


# ---------------------------------------------------------------------------
# Soglie
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("b,s,g", [(100, 100, 600), (300, 100, 600), (0, 1, 2), (1, 5, 5)])
def test_soglie_incoerenti(b, s, g):
    with pytest.raises(InvalidThresholdsError):
        LevelThresholds(bronze=b, silver=s, gold=g)


def test_resolve_thresholds_override_singolo():
    r = resolve_thresholds(T, bronze=50)
    assert (r.bronze, r.silver, r.gold) == (50, 300, 600)


def test_resolve_thresholds_senza_override():
    assert resolve_thresholds(T) == T


def test_resolve_thresholds_override_incoerente():
    with pytest.raises(InvalidThresholdsError):
        resolve_thresholds(T, bronze=400)


# ---------------------------------------------------------------------------
# Periodi
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("moment,expected", [
    (datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC), "2026-09"),
    (datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC), "2026-10"),
    (datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC), "2026-12"),
    (datetime(2027, 1, 1, 0, 0, 0, tzinfo=UTC), "2027-01"),
    (datetime(2028, 2, 29, 12, 0, tzinfo=UTC), "2028-02"),
])
def test_period_for(moment, expected):
    assert period_for(moment) == expected


def test_period_for_converte_in_utc():
    # 01:30 del 1° ottobre a +02:00 = 23:30 UTC del 30 settembre
    moment = datetime(2026, 10, 1, 1, 30, tzinfo=timezone(timedelta(hours=2)))
    assert period_for(moment) == "2026-09"


def test_period_for_rifiuta_naive():
    with pytest.raises(ValueError):
        period_for(datetime(2026, 10, 1, 12, 0))


def test_previous_period():
    assert previous_period(date(2026, 1, 15)) == (2025, 12)
    assert previous_period(date(2026, 3, 1)) == (2026, 2)


def test_period_label():
    assert period_label(2026, 3) == "2026-03"
    assert period_label(2026, 12) == "2026-12"


# ---------------------------------------------------------------------------
# Piano di chiusura
# ---------------------------------------------------------------------------

def _pool(merchant_id, points):
    return PoolInput(merchant_id=merchant_id, business_name=f"Negozio {merchant_id}",
                     points=points, thresholds=T)


def test_piano_tre_pool():
    plan = plan_period_closure("2026-09", [_pool(3, 50), _pool(1, 700), _pool(2, 350)], set(), 20)
    assert isinstance(plan, ClosurePlan)
    assert plan.period == "2026-09"
    assert [l.merchant_id for l in plan.lines] == [1, 2, 3]  # ordinate per id
    assert [l.trees for l in plan.lines] == [5, 3, 0]
    assert [l.level for l in plan.lines] == [Level.GOLD, Level.SILVER, Level.NONE]
    assert plan.total_trees == 8
    assert plan.global_cap == 20
    assert plan.exceeds_cap is False
    assert plan.excess == 0


def test_piano_sfora_il_cap_senza_ripartire():
    pools = [_pool(i, 700) for i in range(1, 5)] + [_pool(5, 100), _pool(6, 350)]  # 20 + 1 + 3 = 24
    plan = plan_period_closure("2026-09", pools, set(), 20)
    assert plan.total_trees == 24
    assert plan.exceeds_cap is True
    assert plan.excess == 4
    assert [l.trees for l in plan.lines] == [5, 5, 5, 5, 1, 3]  # righe invariate


def test_piano_esclude_gia_chiusi():
    plan = plan_period_closure("2026-09", [_pool(1, 700), _pool(2, 350)], {1}, 20)
    assert [l.merchant_id for l in plan.lines] == [2]
    assert plan.total_trees == 3


def test_piano_vuoto():
    plan = plan_period_closure("2026-09", [], set(), 20)
    assert plan.lines == []
    assert plan.total_trees == 0
    assert plan.exceeds_cap is False
    assert plan.excess == 0


def test_piano_totale_uguale_al_cap():
    plan = plan_period_closure("2026-09", [_pool(i, 700) for i in range(1, 5)], set(), 20)
    assert plan.total_trees == 20
    assert plan.exceeds_cap is False


# ---------------------------------------------------------------------------
# Purezza del modulo
# ---------------------------------------------------------------------------

def test_level_viene_da_core_enums():
    assert tree_service.Level is Level


def test_modulo_senza_dipendenze_di_infrastruttura():
    """La parte del modulo prima di `# --- Shell ---` è il core: niente DB, HTTP o orologio."""
    source = Path(tree_service.__file__).read_text(encoding="utf-8").split("\n# --- Shell ---\n")[0]
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & {"sqlmodel", "httpx", "fastapi", "sqlalchemy", "zoneinfo"}
    assert "datetime.now" not in source and "utcnow" not in source
