"""
Test di errori di dominio, handler HTTP e configurazione (nessun DB).
"""

import pytest
from fastapi.testclient import TestClient

from app.core import errors
from app.core.config import Settings
from app.main import app


def test_gerarchia_errori():
    for cls in (errors.NotFoundError, errors.ForbiddenError, errors.InsufficientBalanceError,
                errors.InvalidThresholdsError, errors.PeriodAlreadyClosedError,
                errors.ConflictError, errors.InvalidInputError):
        assert issubclass(cls, errors.DomainError)
    assert issubclass(errors.DomainError, Exception)


def test_errors_non_importa_fastapi():
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(errors))
    names = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    names |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(n.split(".")[0] == "fastapi" for n in names)


@pytest.fixture()
def error_routes():
    """Aggiunge all'app route che sollevano errori di dominio; le toglie a fine test."""
    def make(exc):
        async def _raise():
            raise exc("messaggio di prova")
        return _raise

    before = len(app.router.routes)
    app.add_api_route("/_test/not-found", make(errors.NotFoundError))
    app.add_api_route("/_test/insufficient", make(errors.InsufficientBalanceError))
    app.add_api_route("/_test/forbidden", make(errors.ForbiddenError))
    app.add_api_route("/_test/closed", make(errors.PeriodAlreadyClosedError))
    app.add_api_route("/_test/conflict", make(errors.ConflictError))
    app.add_api_route("/_test/invalid-input", make(errors.InvalidInputError))
    yield TestClient(app)
    del app.router.routes[before:]


@pytest.mark.parametrize("path,status", [
    ("/_test/not-found", 404),
    ("/_test/insufficient", 400),
    ("/_test/forbidden", 403),
    ("/_test/closed", 400),
    ("/_test/conflict", 409),
    ("/_test/invalid-input", 400),
])
def test_handler_errori_di_dominio(error_routes, path, status):
    resp = error_routes.get(path)
    assert resp.status_code == status
    assert resp.json() == {"detail": "messaggio di prova"}


def test_settings_default_nuovi(monkeypatch):
    for var in ("ECOLOGI_API_KEY", "ECOLOGI_TEST_API_KEY",
                "ECOLOGI_GLOBAL_MONTHLY_CAP", "TIER_BRONZE_POINTS",
                "TIER_SILVER_POINTS", "TIER_GOLD_POINTS", "AUTH_PROVIDER", "ENVIRONMENT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JWT_SECRET_KEY", "x")
    monkeypatch.setenv("ADMIN_SECRET_KEY", "y")

    s = Settings(_env_file=None)
    assert s.ECOLOGI_API_KEY == ""
    assert s.ECOLOGI_TEST_API_KEY == ""
    assert not hasattr(s, "ECOLOGI_TEST_BASE_URL")  # il test è il flag "test", stesso URL
    assert s.ECOLOGI_GLOBAL_MONTHLY_CAP == 20
    assert (s.TIER_BRONZE_POINTS, s.TIER_SILVER_POINTS, s.TIER_GOLD_POINTS) == (100, 300, 600)
    assert s.AUTH_PROVIDER == "dev"
    assert s.ENVIRONMENT == "development"


def test_settings_auth_provider_solo_valori_ammessi(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JWT_SECRET_KEY", "x")
    monkeypatch.setenv("ADMIN_SECRET_KEY", "y")
    monkeypatch.setenv("AUTH_PROVIDER", "boh")
    with pytest.raises(Exception):
        Settings(_env_file=None)
