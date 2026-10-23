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
                errors.ConflictError, errors.InvalidInputError,
                errors.MessageTooLongError, errors.InvalidSignatureError):
        assert issubclass(cls, errors.DomainError)
    assert issubclass(errors.DomainError, Exception)
    assert issubclass(errors.MessageTooLongError, errors.InvalidInputError)
    assert issubclass(errors.InvalidSignatureError, errors.AuthError)


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
    app.add_api_route("/_test/too-long", make(errors.MessageTooLongError))
    app.add_api_route("/_test/bad-signature", make(errors.InvalidSignatureError))
    yield TestClient(app)
    del app.router.routes[before:]


@pytest.mark.parametrize("path,status", [
    ("/_test/not-found", 404),
    ("/_test/insufficient", 400),
    ("/_test/forbidden", 403),
    ("/_test/closed", 400),
    ("/_test/conflict", 409),
    ("/_test/invalid-input", 400),
    ("/_test/too-long", 400),
    ("/_test/bad-signature", 401),
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


def _env_minimo(monkeypatch):
    """Variabili obbligatorie per costruire `Settings` senza leggere il .env locale."""
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JWT_SECRET_KEY", "x")
    monkeypatch.setenv("ADMIN_SECRET_KEY", "y")


@pytest.mark.parametrize("var", ["ENCRYPTION_KEY", "IGSID_HMAC_KEY", "CARD_LINK_KEY"])
def test_settings_chiavi_instagram_obbligatorie(monkeypatch, var):
    _env_minimo(monkeypatch)
    Settings(_env_file=None)  # con le chiavi di test del conftest è valida
    monkeypatch.delenv(var)
    with pytest.raises(Exception):
        Settings(_env_file=None)


@pytest.mark.parametrize("var", ["ENCRYPTION_KEY", "IGSID_HMAC_KEY", "CARD_LINK_KEY"])
def test_settings_chiavi_instagram_vuote_rifiutate(monkeypatch, var):
    _env_minimo(monkeypatch)
    monkeypatch.setenv(var, "")
    with pytest.raises(Exception):
        Settings(_env_file=None)


@pytest.mark.parametrize("bad", ["non-base64!!", "dGVzdA=="])  # malformata / solo 4 byte
def test_settings_encryption_key_deve_essere_32_byte_base64(monkeypatch, bad):
    _env_minimo(monkeypatch)
    monkeypatch.setenv("ENCRYPTION_KEY", bad)
    with pytest.raises(Exception):
        Settings(_env_file=None)


def test_settings_default_instagram_zernio(monkeypatch):
    _env_minimo(monkeypatch)
    for var in ("ENCRYPTION_KEY_ID", "PUBLIC_BASE_URL", "ZERNIO_BASE_URL", "INSTAGRAM_CARD_KEYWORD",
                "ZERNIO_MONTHLY_SEND_LIMIT", "ZERNIO_SEND_WARN_PERCENT"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.ENCRYPTION_KEY_ID == "1"
    assert s.PUBLIC_BASE_URL == "http://127.0.0.1:8001"
    assert s.ZERNIO_BASE_URL == "https://zernio.com/api"
    assert s.INSTAGRAM_CARD_KEYWORD == "CARTA"
    assert s.ZERNIO_MONTHLY_SEND_LIMIT == 10000
    assert s.ZERNIO_SEND_WARN_PERCENT == 75


def test_settings_auth_provider_solo_valori_ammessi(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JWT_SECRET_KEY", "x")
    monkeypatch.setenv("ADMIN_SECRET_KEY", "y")
    monkeypatch.setenv("AUTH_PROVIDER", "boh")
    with pytest.raises(Exception):
        Settings(_env_file=None)
