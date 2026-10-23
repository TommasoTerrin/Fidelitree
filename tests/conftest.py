"""
Fixture condivise per la test suite.

I test girano su un database SQLite in-memory: nessun test tocca Neon
né fa chiamate di rete. La sessione di test viene iniettata nell'app
tramite dependency_overrides.
"""

import os

# Chiavi obbligatorie senza default: i valori di test vanno impostati PRIMA di importare l'app.
os.environ.setdefault("ENCRYPTION_KEY", "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcy0hISE=")  # 32 byte base64 urlsafe
os.environ.setdefault("IGSID_HMAC_KEY", "test-igsid-hmac-key-0123456789-abcdef")
os.environ.setdefault("CARD_LINK_KEY", "test-card-link-key-0123456789-abcdefg")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.main import app
from app.core.dependencies import get_session, get_current_merchant
from app.models.models import Merchant, Customer, Card
from app.services import ecologi_service
from app.services.db_crud import merchant_crud, customer_crud


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
    """Merchant di test (email, approvato)."""
    return merchant_crud.create_merchant(session, {
        "business_name": "Test Merchant",
        "email": "merchant@test.it",
        "contact_phone": "+393331234567",
        "is_approved": True,
    })


@pytest.fixture()
def customer(session) -> Customer:
    """Cliente di test."""
    return customer_crud.create_customer(session, "cliente@test.it")


@pytest.fixture()
def card(session, merchant, customer) -> Card:
    """Card di test del cliente di test presso il merchant di test."""
    new_card = Card(merchant_id=merchant.id, customer_id=customer.id)
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
def auth_provider():
    """Provider `dev` con lo stato in memoria azzerato prima e dopo ogni test."""
    from app.core.auth import get_auth_provider
    provider = get_auth_provider()
    provider.reset()
    yield provider
    provider.reset()


def login_as(client, identity, provider=None) -> str:
    """Autentica il client come `identity` (cookie `access_token`); ritorna il token."""
    from app.core.auth import get_auth_provider
    token = (provider or get_auth_provider()).issue_token(identity)
    client.cookies.set("access_token", token)
    return token


def identity_for(email: str):
    """Identità del provider dev per `email` (stesso `user_id` che darebbe il login vero)."""
    from app.core.auth import AuthIdentity, dev_user_id
    return AuthIdentity(user_id=dev_user_id(email), email=email)


@pytest.fixture()
def admin_headers():
    """Header con la chiave admin corretta (letta dalle settings)."""
    from app.core.config import settings
    return {"X-Admin-Key": settings.ADMIN_SECRET_KEY}


# ---------------------------------------------------------------------------
# Ecologi: mock del servizio (niente rete), chiave di piattaforma
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_ecologi(monkeypatch):
    """
    Sostituisce le chiamate a Ecologi: nessuna rete nei test.
    Ritorna la lista delle piantumazioni simulate (per le assertion); ogni acquisto
    restituisce un `treeUrl` progressivo ("https://ecologi.test/tree-N") usato come `ecologi_ref`.
    """
    calls = []

    async def fake_purchase(number, name=None, idempotency_key=None, *, force_test=False):
        calls.append({"number": number, "name": name, "idempotency_key": idempotency_key})
        return {"treeUrl": f"https://ecologi.test/tree-{len(calls)}", "number": number}

    monkeypatch.setattr(ecologi_service, "purchase_trees", fake_purchase)
    return calls


@pytest.fixture()
def approved_merchants(session):
    """
    Crea merchant approvati con pool reali prodotti da scan veri (contatore e registro
    coincidono). Uso: `approved_merchants({"A": 700, "B": 350})` → lista di Merchant.
    Il pool è del mese di `POOL_NOW` (2026-10).
    """
    from datetime import datetime, timezone
    from app.services import card_service

    def _make(points_by_name: dict, conversion_enabled: bool = False):
        merchants = []
        for i, (name, points) in enumerate(points_by_name.items(), start=1):
            m = merchant_crud.create_merchant(session, {
                "business_name": name, "email": f"m{i}-{name.lower()}@test.it",
                "is_approved": True, "conversion_enabled": conversion_enabled,
            })
            if points:
                c = customer_crud.create_customer(session, f"c{i}-{name.lower()}@test.it")
                cd = Card(merchant_id=m.id, customer_id=c.id)
                session.add(cd)
                session.commit()
                session.refresh(cd)
                card_service.add_tree_points(
                    session, m, cd.id, points,
                    now=datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc),
                )
            merchants.append(m)
        return merchants

    return _make
