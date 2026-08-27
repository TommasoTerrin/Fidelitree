"""
Fixture condivise per la test suite.

I test girano su un database SQLite in-memory: nessun test tocca Neon
né fa chiamate di rete. La sessione di test viene iniettata nell'app
tramite dependency_overrides.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.main import app
from app.core.dependencies import get_session, get_current_merchant
from app.models.models import Merchant, Card
from app.services import ecologi_service
from app.services.db_crud import merchant_crud

TEST_PASSWORD = "password-di-test"
VALID_ECOLOGI_KEY = "ecologi-valid-key"


@pytest.fixture()
def session():
    """Sessione su un DB SQLite in-memory nuovo per ogni test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture()
def client(session):
    """TestClient con la sessione di test iniettata al posto di quella reale."""

    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def merchant(session) -> Merchant:
    """Merchant di test con password cifrata (come in produzione)."""
    return merchant_crud.create_merchant(session, {
        "business_name": "Test Merchant",
        "phone_number": "+393331234567",
        "password": TEST_PASSWORD,
    })


@pytest.fixture()
def card(session, merchant) -> Card:
    """Card di test associata al merchant di test."""
    new_card = Card(merchant_id=merchant.id)
    session.add(new_card)
    session.commit()
    session.refresh(new_card)
    return new_card


@pytest.fixture()
def auth_client(client, merchant):
    """TestClient con il merchant di test già autenticato."""
    app.dependency_overrides[get_current_merchant] = lambda: merchant
    yield client
    app.dependency_overrides.pop(get_current_merchant, None)


@pytest.fixture()
def admin_headers():
    """Header con la chiave admin corretta (letta dalle settings)."""
    from app.core.config import settings
    return {"X-Admin-Key": settings.ADMIN_SECRET_KEY}


# ---------------------------------------------------------------------------
# Tree points: merchant con chiave Ecologi + mock del servizio (niente rete)
# ---------------------------------------------------------------------------

@pytest.fixture()
def tree_merchant(session) -> Merchant:
    """Merchant con chiave Ecologi configurata, soglia 5 e cap mensile 3."""
    return merchant_crud.create_merchant(session, {
        "business_name": "Green Merchant",
        "phone_number": "+393339876543",
        "password": TEST_PASSWORD,
        "ecologi_api_key": VALID_ECOLOGI_KEY,
        "tree_threshold": 5,
        "monthly_tree_cap": 3,
        "mode": "trees_cashback",
    })


@pytest.fixture()
def tree_card(session, tree_merchant) -> Card:
    """Card di test associata al merchant con chiave Ecologi."""
    new_card = Card(merchant_id=tree_merchant.id)
    session.add(new_card)
    session.commit()
    session.refresh(new_card)
    return new_card


@pytest.fixture()
def tree_auth_client(client, tree_merchant):
    """TestClient autenticato come tree_merchant."""
    app.dependency_overrides[get_current_merchant] = lambda: tree_merchant
    yield client
    app.dependency_overrides.pop(get_current_merchant, None)


@pytest.fixture()
def mock_ecologi(monkeypatch):
    """
    Sostituisce le chiamate a Ecologi: nessuna rete nei test.
    Ritorna la lista delle piantumazioni simulate (per le assertion).
    """
    calls = []

    async def fake_purchase(api_key, number=1, name=None):
        calls.append({"api_key": api_key, "number": number, "name": name})
        return {"number": number, "test": True}

    async def fake_validate(api_key):
        return api_key == VALID_ECOLOGI_KEY

    monkeypatch.setattr(ecologi_service, "purchase_trees", fake_purchase)
    monkeypatch.setattr(ecologi_service, "validate_api_key", fake_validate)
    return calls
