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
from app.core.dependencies import get_session, get_current_merchant, get_optional_merchant
from app.models.models import Merchant, Card
from app.services import ecologi_service, instagram_service
from app.services.db_crud import merchant_crud


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


def make_card(session, merchant, igsid="igsid-test-1") -> Card:
    """
    Carta di un cliente Instagram (identificato da `igsid`) presso `merchant`, creata come fa il webhook:
    indice cieco dell'IGSID e hash del token del link veri, quindi `/c/<token>` funziona. Idempotente per
    la stessa coppia (negozio, IGSID); per più carte nello stesso negozio serve un `igsid` diverso.
    """
    new_card, _ = instagram_service.get_or_create_card(session, merchant, igsid)
    return new_card


@pytest.fixture()
def card(session, merchant) -> Card:
    """Card di test del cliente `igsid-test-1` presso il merchant di test."""
    return make_card(session, merchant)


@pytest.fixture()
def auth_client(client, merchant):
    """TestClient con il merchant di test già autenticato."""
    app.dependency_overrides[get_current_merchant] = lambda: merchant      # API /api/merchant/*
    app.dependency_overrides[get_optional_merchant] = lambda: merchant     # pagine HTML /merchant/*
    yield client
    app.dependency_overrides.pop(get_current_merchant, None)
    app.dependency_overrides.pop(get_optional_merchant, None)


@pytest.fixture()
def auth_provider():
    """Provider `dev` con lo stato in memoria azzerato prima e dopo ogni test."""
    from app.core.auth import get_auth_provider
    provider = get_auth_provider()
    provider.reset()
    yield provider
    provider.reset()


@pytest.fixture(autouse=True)
def reset_login_throttle():
    """Il freno ai tentativi di login è in memoria del processo: lo si azzera prima e dopo ogni test."""
    from app.core.auth import login_throttle
    login_throttle.reset()
    yield
    login_throttle.reset()


@pytest.fixture()
def local_auth(session, monkeypatch):
    """
    Provider `local` su SQLite in-memory, installato al posto del provider scelto da `settings`
    (`AUTH_PROVIDER=local`). Usa la `session` di test: il provider NON apre mai l'engine dell'app (che punta
    al `DATABASE_URL` del .env). L'istanza si toglie da `auth._instances` a fine test.
    """
    from contextlib import nullcontext
    from app.core import auth
    from app.core.config import settings

    provider = auth.LocalAuthProvider(session_factory=lambda: nullcontext(session))
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "local")
    monkeypatch.setitem(auth._instances, "local", provider)
    return provider


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
                cd = make_card(session, m, igsid=f"igsid-pool-{i}")
                card_service.add_tree_points(
                    session, m, cd.id, points,
                    now=datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc),
                )
            merchants.append(m)
        return merchants

    return _make


# ---------------------------------------------------------------------------
# Instagram / Zernio (v0.3.0): negozio collegato, Zernio finto, webhook firmato
# ---------------------------------------------------------------------------

ZERNIO_TEST_KEY = "sk_" + "ef56" * 16
WEBHOOK_TEST_SECRET = "whsec-di-prova-0123456789"
TEST_PUBLIC_BASE_URL = "https://fidelitree.example"
INSTAGRAM_ACCOUNT_ID = "acc-1"
INSTAGRAM_HOOK_ID = "hook-opaco-123"


@pytest.fixture()
def instagram_merchant(session, monkeypatch) -> Merchant:
    """
    Merchant con Instagram collegato (stato `ACTIVE`): chiave Zernio e secret del webhook cifrati,
    `zernio_account_id` e `webhook_hook_id` valorizzati. Imposta anche un `PUBLIC_BASE_URL` https
    (la card accetta solo link https).
    """
    from app.core.config import settings
    from app.core.crypto import encrypt_secret
    from app.core.enums import InstagramStatus

    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", TEST_PUBLIC_BASE_URL)
    created = merchant_crud.create_merchant(session, {
        "business_name": "Bar Demo", "email": "bar@test.it", "is_approved": True,
    })
    created.zernio_api_key_enc = encrypt_secret(ZERNIO_TEST_KEY)
    created.zernio_account_id = INSTAGRAM_ACCOUNT_ID
    created.zernio_profile_id = "prof-1"
    created.instagram_username = "bar_demo"
    created.webhook_hook_id = INSTAGRAM_HOOK_ID
    created.webhook_secret_enc = encrypt_secret(WEBHOOK_TEST_SECRET)
    created.instagram_status = InstagramStatus.ACTIVE
    session.add(created)
    session.commit()
    session.refresh(created)
    return created


class ZernioMock:
    """
    Zernio finto: registra le richieste e risponde con 200 (`messageId` progressivo) salvo diversa
    indicazione. `queue(...)` accoda risposte (`httpx.Response`) o eccezioni httpx da sollevare,
    consumate una per richiesta nell'ordine.
    """

    def __init__(self):
        import httpx
        self._httpx = httpx
        self.requests: list = []
        self._queue: list = []

    def queue(self, *items) -> "ZernioMock":
        """Accoda risposte o eccezioni per le prossime richieste."""
        self._queue.extend(items)
        return self

    def handler(self, request):
        """Handler del `MockTransport`."""
        self.requests.append(request)
        if self._queue:
            item = self._queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return self._httpx.Response(200, json={"success": True, "data": {"messageId": f"m_{len(self.requests)}"}})

    def bodies(self) -> list:
        """Corpi JSON delle richieste viste, nell'ordine."""
        import json
        return [json.loads(r.read()) for r in self.requests]


@pytest.fixture()
def zernio_mock(client):
    """
    `ZernioMock` installato con `dependency_overrides[get_zernio_http]`: il webhook parla con questo
    e non con la rete. Dipende da `client`, che azzera gli override a fine test.
    """
    import httpx
    from app.services.zernio_service import get_zernio_http

    mock = ZernioMock()

    async def override():
        async with httpx.AsyncClient(transport=httpx.MockTransport(mock.handler)) as http:
            yield http

    app.dependency_overrides[get_zernio_http] = override
    return mock


def sign_body(raw: bytes, secret: str = WEBHOOK_TEST_SECRET) -> str:
    """Firma `X-Zernio-Signature`: HMAC-SHA256 esadecimale del corpo grezzo."""
    import hashlib
    import hmac
    return hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def signed_webhook(client, merchant, payload, event_id=None, *, signature=None, secret=WEBHOOK_TEST_SECRET,
                   hook_id=None, raw: bytes = None):
    """
    Invia un webhook Zernio al negozio: serializza `payload` (o usa `raw`), lo firma con `secret` (o con
    `signature`, `""` = header assente) e lo manda con `X-Zernio-Event-Id` = `event_id` (default:
    `payload["id"]`; `""` = header assente). Ritorna la risposta.
    """
    import json
    body = raw if raw is not None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    event_id = payload.get("id") if event_id is None and isinstance(payload, dict) else event_id
    if event_id:
        headers["X-Zernio-Event-Id"] = event_id
    sig = sign_body(body, secret) if signature is None else signature
    if sig:
        headers["X-Zernio-Signature"] = sig
    return client.post(f"/webhooks/zernio/{hook_id or merchant.webhook_hook_id}", content=body, headers=headers)
