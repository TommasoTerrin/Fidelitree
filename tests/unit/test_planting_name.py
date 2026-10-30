"""Test del core puro `planting_name`: etichetta della tessera sulla foresta Ecologi."""

import pytest

from app.core.errors import InvalidInputError
from app.services.tree_service import planting_name


def test_formato_base_e_mesi_estremi():
    assert planting_name("Bar Demo", "2026-10") == "Bar Demo · ottobre 2026"
    assert planting_name("Bar Demo", "2026-01") == "Bar Demo · gennaio 2026"
    assert planting_name("Bar Demo", "2026-12") == "Bar Demo · dicembre 2026"


def test_spazi_normalizzati():
    assert planting_name("  Forno   del Borgo ", "2026-10") == "Forno del Borgo · ottobre 2026"


@pytest.mark.parametrize("name", ["", "   "])
def test_nome_vuoto_usa_il_default(name):
    assert planting_name(name, "2026-10") == "Negozio Fidelitree · ottobre 2026"


def test_nome_lungo_troncato_a_60():
    result = planting_name("x" * 100, "2026-10")
    assert result == "x" * 60 + " · ottobre 2026"


@pytest.mark.parametrize("period", ["2026-13", "2026-00", "ottobre", "2026-1", "26-10", "2026-10-01", ""])
def test_periodo_non_valido(period):
    with pytest.raises(InvalidInputError):
        planting_name("Bar Demo", period)
