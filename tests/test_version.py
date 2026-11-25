"""
Test del versionamento: la versione dell'app ha come unica fonte
`[project] version` in pyproject.toml ed è esposta da `GET /health`.
"""

import tomllib
from pathlib import Path

from app import version
from scripts import smoke_test_prod

ROOT = Path(__file__).resolve().parent.parent


def _versione_da_pyproject() -> str:
    """Legge direttamente la versione da pyproject.toml (riferimento indipendente)."""
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def test_versione_0_4_1_in_pyproject_e_nello_smoke_test():
    """
    v0.4.1 AC-29: `pyproject.toml` ed `EXPECTED_VERSION` dello smoke test di
    produzione valgono entrambi "0.4.1"; il letterale viene dal contract (§1),
    non da `get_version()`, così un bump dimenticato in uno dei due punti fa
    fallire il test.
    """
    assert _versione_da_pyproject() == "0.4.1"
    assert smoke_test_prod.EXPECTED_VERSION == "0.4.1"


def test_get_version_coincide_con_pyproject():
    assert version.get_version() == "0.4.1"
    assert version.get_version() == _versione_da_pyproject()


def test_get_version_unknown_se_pyproject_non_raggiungibile(monkeypatch, tmp_path):
    # Punto di partenza della ricerca in una cartella senza pyproject.toml
    monkeypatch.setattr(version, "__file__", str(tmp_path / "version.py"))
    # Se esistesse un pyproject.toml sopra tmp_path il test non sarebbe valido
    assert not any((p / "pyproject.toml").exists() for p in tmp_path.parents)
    assert version.get_version() == "unknown"


def test_health_espone_versione(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app"] == "Fidelitree"
    assert body["version"] == "0.4.1"
