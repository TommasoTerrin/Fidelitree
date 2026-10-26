"""
Test dell'onboarding Instagram del merchant: chiave Zernio, scelta dell'account, webhook e menu, scollegamento,
pannello. Zernio è finto (`FakeZernio`, un `MockTransport` che risponde in base a metodo e path): nessuna rete.
"""

import json
from datetime import timedelta
from urllib.parse import urlparse

import httpx
import pytest
from sqlmodel import select

from app.core.clock import utc_now
from app.core.config import settings
from app.core.crypto import decrypt_secret
from app.core.dependencies import get_current_merchant
from app.core.enums import InstagramStatus
from app.main import app
from app.models.models import Card, Merchant, ZernioSendCounter
from app.services.instagram_service import CARD_POSTBACK_PAYLOAD
from app.services.zernio_service import get_zernio_http
from tests.conftest import (
    INSTAGRAM_ACCOUNT_ID, TEST_PUBLIC_BASE_URL, WEBHOOK_TEST_SECRET, ZERNIO_TEST_KEY, ZernioMock, make_card,
)

NEW_KEY = "sk_" + "cd34" * 16
ACCOUNT = {"_id": INSTAGRAM_ACCOUNT_ID, "platform": "instagram", "username": "bar_demo", "profileId": "prof-1"}
ZERNIO_FIELDS = (
    "zernio_api_key_enc", "zernio_account_id", "zernio_profile_id", "zernio_team_id", "instagram_username",
    "webhook_hook_id", "webhook_secret_enc", "zernio_webhook_id", "standby_detected_at", "standby_owner_app_id",
)


class FakeZernio(ZernioMock):
    """
    Zernio finto per l'onboarding: risponde in base a metodo e path. `accounts` e `menu` sono i dati restituiti;
    `override[etichetta]` sostituisce la risposta (una `httpx.Response` o un'eccezione) in modo permanente.
    Etichette: accounts, webhook_create, webhook_delete, menu_get, menu_put.
    """

    def __init__(self):
        super().__init__()
        self.accounts = [dict(ACCOUNT)]
        self.menu: list = []
        self.override: dict = {}

    @staticmethod
    def label(request) -> str:
        """Nome della chiamata, dal metodo e dal path (senza il prefisso della base URL)."""
        prefix = urlparse(settings.ZERNIO_BASE_URL).path.rstrip("/")
        path = request.url.path[len(prefix):]
        if path == "/v1/accounts":
            return "accounts"
        if path == "/v1/webhooks/settings":
            return "webhook_create" if request.method == "POST" else "webhook_delete"
        if path.endswith("/messenger-menu"):
            return "menu_get" if request.method == "GET" else "menu_put"
        return f"altro:{request.method}:{path}"

    def handler(self, request):
        self.requests.append(request)
        label = self.label(request)
        item = self.override.get(label)
        if isinstance(item, Exception):
            raise item
        if item is not None:
            return item
        if label == "accounts":
            return httpx.Response(200, json={"accounts": self.accounts})
        if label == "webhook_create":
            return httpx.Response(200, json={"success": True, "webhook": {"_id": "wh-1", "isActive": True}})
        if label == "menu_get":
            return httpx.Response(200, json={"data": self.menu})
        return httpx.Response(200, json={"success": True})

    def calls(self, label: str) -> list:
        """Richieste viste per una chiamata."""
        return [r for r in self.requests if self.label(r) == label]


@pytest.fixture()
def zernio(client):
    """`FakeZernio` installato come `get_zernio_http`; `client` azzera gli override a fine test."""
    fake = FakeZernio()

    async def override():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)) as http:
            yield http

    app.dependency_overrides[get_zernio_http] = override
    return fake


@pytest.fixture()
def https_base(monkeypatch):
    """`PUBLIC_BASE_URL` https, come in produzione (il default locale è http)."""
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", TEST_PUBLIC_BASE_URL)


def _error(status, **body):
    return httpx.Response(status, json=body)


def _stored(session, merchant) -> dict:
    """Campi Zernio e stato del merchant riletti dal DB."""
    session.expire_all()
    fresh = session.get(Merchant, merchant.id)
    return {**{f: getattr(fresh, f) for f in ZERNIO_FIELDS}, "status": fresh.instagram_status,
            "menu": fresh.persistent_menu_set}


def _connect(auth_client, zernio_key=NEW_KEY):
    """Salva la chiave e sceglie l'account tramite l'API; ritorna la risposta della seconda chiamata."""
    assert auth_client.post("/api/merchant/instagram/key", json={"api_key": zernio_key}).status_code == 200
    return auth_client.post("/api/merchant/instagram/account", json={"account_id": INSTAGRAM_ACCOUNT_ID})


# --- chiave Zernio ---

def test_chiave_valida_restituisce_gli_account_e_si_salva_cifrata(auth_client, zernio, session, merchant):
    resp = auth_client.post("/api/merchant/instagram/key", json={"api_key": f"  {NEW_KEY} "})

    assert resp.status_code == 200
    assert resp.json() == {"accounts": [{"id": INSTAGRAM_ACCOUNT_ID, "username": "bar_demo"}]}
    assert NEW_KEY not in resp.text
    [request] = zernio.calls("accounts")
    assert request.headers["Authorization"] == f"Bearer {NEW_KEY}"
    assert request.url.params["platform"] == "instagram" and request.url.params["status"] == "connected"
    stored = _stored(session, merchant)
    assert stored["zernio_api_key_enc"] and NEW_KEY not in stored["zernio_api_key_enc"]
    assert decrypt_secret(stored["zernio_api_key_enc"]) == NEW_KEY
    assert stored["status"] == InstagramStatus.NOT_CONNECTED and stored["zernio_account_id"] is None


def test_chiave_zrk_con_gruppi_limitati_e_accettata(auth_client, zernio):
    assert auth_client.post("/api/merchant/instagram/key", json={"api_key": "zrk_" + "a" * 30}).status_code == 200


def test_chiave_errata_400_e_nulla_salvato(auth_client, zernio, session, merchant):
    zernio.override["accounts"] = _error(401, code="invalid_credentials", error="Invalid API key")

    resp = auth_client.post("/api/merchant/instagram/key", json={"api_key": NEW_KEY})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Chiave Zernio non valida"
    assert NEW_KEY not in resp.text
    assert _stored(session, merchant)["zernio_api_key_enc"] is None


@pytest.mark.parametrize("body", [
    {"api_key": ""}, {"api_key": "   "}, {"api_key": "abc123"}, {"api_key": "sk_"}, {"api_key": "pk_" + "a" * 30},
    {"api_key": "sk_con spazio dentro"}, {},
])
def test_chiave_vuota_o_malformata_400_senza_chiamare_zernio(auth_client, zernio, session, merchant, body):
    resp = auth_client.post("/api/merchant/instagram/key", json=body)

    assert resp.status_code == 400  # non 422: il corpo di un 422 rimanderebbe indietro il valore inviato
    for value in body.values():
        assert len(value.strip()) <= 4 or value not in resp.text  # i prefissi nudi sono nel messaggio fisso
    assert zernio.requests == []
    assert _stored(session, merchant)["zernio_api_key_enc"] is None


def test_chiave_di_tipo_sbagliato_non_e_riportata_nella_risposta(auth_client, zernio):
    resp = auth_client.post("/api/merchant/instagram/key", json={"api_key": ["sk_" + "z" * 40]})
    assert resp.status_code == 400  # niente 422: l'errore di validazione di FastAPI rimanda indietro `input`
    assert "z" * 40 not in resp.text
    assert zernio.requests == []


def test_nessun_account_instagram_400_con_istruzione(auth_client, zernio, session, merchant):
    zernio.accounts = []

    resp = auth_client.post("/api/merchant/instagram/key", json={"api_key": NEW_KEY})

    assert resp.status_code == 400
    assert "Zernio" in resp.json()["detail"] and "Instagram" in resp.json()["detail"]
    assert _stored(session, merchant)["zernio_api_key_enc"] is None


def test_zernio_in_errore_sulla_chiave_502_e_nulla_salvato(auth_client, zernio, session, merchant):
    zernio.override["accounts"] = _error(500, error="boom")
    assert auth_client.post("/api/merchant/instagram/key", json={"api_key": NEW_KEY}).status_code == 502
    zernio.override["accounts"] = httpx.ConnectError("irraggiungibile")
    assert auth_client.post("/api/merchant/instagram/key", json={"api_key": NEW_KEY}).status_code == 502
    assert _stored(session, merchant)["zernio_api_key_enc"] is None


def test_nuova_chiave_scollega_prima_la_vecchia_configurazione(zernio, client, session, instagram_merchant):
    instagram_merchant.zernio_webhook_id = "wh-vecchio"
    session.add(instagram_merchant)
    session.commit()
    app.dependency_overrides[get_current_merchant] = lambda: instagram_merchant

    resp = client.post("/api/merchant/instagram/key", json={"api_key": NEW_KEY})

    assert resp.status_code == 200
    [delete] = zernio.calls("webhook_delete")
    assert delete.url.params["webhookId"] == "wh-vecchio"
    assert delete.headers["Authorization"] == f"Bearer {ZERNIO_TEST_KEY}"  # con la chiave vecchia
    stored = _stored(session, instagram_merchant)
    assert decrypt_secret(stored["zernio_api_key_enc"]) == NEW_KEY
    assert stored["status"] == InstagramStatus.NOT_CONNECTED
    assert stored["zernio_account_id"] is None and stored["webhook_hook_id"] is None
    assert stored["webhook_secret_enc"] is None and stored["zernio_webhook_id"] is None


def test_nuova_chiave_sbagliata_non_tocca_la_configurazione_esistente(zernio, client, session, instagram_merchant):
    instagram_merchant.zernio_webhook_id = "wh-vecchio"
    session.add(instagram_merchant)
    session.commit()
    app.dependency_overrides[get_current_merchant] = lambda: instagram_merchant
    zernio.override["accounts"] = _error(401, code="invalid_credentials")

    resp = client.post("/api/merchant/instagram/key", json={"api_key": NEW_KEY})

    assert resp.status_code == 400
    assert zernio.calls("webhook_delete") == []
    stored = _stored(session, instagram_merchant)
    assert decrypt_secret(stored["zernio_api_key_enc"]) == ZERNIO_TEST_KEY
    assert stored["status"] == InstagramStatus.ACTIVE and stored["webhook_hook_id"] == "hook-opaco-123"


def test_nuova_chiave_con_vecchia_configurazione_illeggibile_o_webhook_gia_sparito(
    zernio, client, session, instagram_merchant,
):
    instagram_merchant.zernio_webhook_id = "wh-vecchio"
    session.add(instagram_merchant)
    session.commit()
    app.dependency_overrides[get_current_merchant] = lambda: instagram_merchant
    zernio.override["webhook_delete"] = _error(404, error="not found")

    resp = client.post("/api/merchant/instagram/key", json={"api_key": NEW_KEY})

    assert resp.status_code == 200
    assert decrypt_secret(_stored(session, instagram_merchant)["zernio_api_key_enc"]) == NEW_KEY


def test_elenco_account_riusa_la_chiave_salvata(auth_client, zernio):
    auth_client.post("/api/merchant/instagram/key", json={"api_key": NEW_KEY})
    zernio.requests.clear()

    resp = auth_client.get("/api/merchant/instagram/accounts")

    assert resp.status_code == 200
    assert resp.json() == {"accounts": [{"id": INSTAGRAM_ACCOUNT_ID, "username": "bar_demo"}]}
    assert zernio.requests[0].headers["Authorization"] == f"Bearer {NEW_KEY}"
    assert NEW_KEY not in resp.text


def test_elenco_account_senza_chiave_salvata_400(auth_client, zernio):
    resp = auth_client.get("/api/merchant/instagram/accounts")
    assert resp.status_code == 400
    assert zernio.requests == []


def test_elenco_account_con_chiave_ormai_rifiutata_400(auth_client, zernio):
    auth_client.post("/api/merchant/instagram/key", json={"api_key": NEW_KEY})
    zernio.override["accounts"] = _error(401, code="invalid_credentials")
    resp = auth_client.get("/api/merchant/instagram/accounts")
    assert resp.status_code == 400 and resp.json()["detail"] == "Chiave Zernio non valida"


# --- collegamento dell'account ---

def test_collegamento_registra_il_webhook_e_imposta_il_menu(auth_client, zernio, https_base, session, merchant):
    resp = _connect(auth_client)

    assert resp.status_code == 200
    [create] = zernio.calls("webhook_create")
    body = json.loads(create.read())
    stored = _stored(session, merchant)
    hook_id = stored["webhook_hook_id"]
    assert hook_id and body["url"] == f"{TEST_PUBLIC_BASE_URL}/webhooks/zernio/{hook_id}"
    assert body["events"] == ["message.received"] and body["accountIds"] == [INSTAGRAM_ACCOUNT_ID]
    assert body["secret"] and body["secret"] != hook_id
    assert decrypt_secret(stored["webhook_secret_enc"]) == body["secret"]
    assert body["secret"] not in stored["webhook_secret_enc"]
    assert create.headers["Authorization"] == f"Bearer {NEW_KEY}"
    # menu vuoto → PUT con la nostra voce
    [put] = zernio.calls("menu_put")
    actions = json.loads(put.read())["persistent_menu"][0]["call_to_actions"]
    assert actions == [{"type": "postback", "title": "🌳 La mia carta", "payload": CARD_POSTBACK_PAYLOAD}]
    assert stored["menu"] is True
    # stato e dati dell'account scelto
    assert stored["status"] == InstagramStatus.AWAITING_TEST_DM
    assert stored["zernio_account_id"] == INSTAGRAM_ACCOUNT_ID and stored["zernio_profile_id"] == "prof-1"
    assert stored["instagram_username"] == "bar_demo" and stored["zernio_webhook_id"] == "wh-1"
    assert decrypt_secret(stored["zernio_api_key_enc"]) == NEW_KEY
    # la risposta è il pannello, senza segreti
    panel = resp.json()
    assert panel["status"] == "awaiting_test_dm" and panel["username"] == "bar_demo"
    assert panel["keyword"] == settings.INSTAGRAM_CARD_KEYWORD
    for secret in (NEW_KEY, body["secret"], hook_id):
        assert secret not in resp.text


def test_collegamento_con_menu_di_altri_non_lo_tocca(auth_client, zernio, https_base, session, merchant):
    zernio.menu = [{"persistent_menu": [{"locale": "default", "call_to_actions": [
        {"type": "postback", "title": "Ordina", "payload": "ORDINA"},
    ]}]}]

    resp = _connect(auth_client)

    assert resp.status_code == 200
    assert zernio.calls("menu_put") == []
    assert _stored(session, merchant)["menu"] is False
    assert "menu" in [w["code"] for w in resp.json()["warnings"]]


def test_collegamento_con_gia_la_nostra_voce_non_la_riscrive(auth_client, zernio, https_base, session, merchant):
    zernio.menu = [{"persistent_menu": [{"locale": "default", "call_to_actions": [
        {"type": "postback", "title": "🌳 La mia carta", "payload": CARD_POSTBACK_PAYLOAD},
    ]}]}]

    resp = _connect(auth_client)

    assert resp.status_code == 200
    assert zernio.calls("menu_put") == []
    assert _stored(session, merchant)["menu"] is True
    assert "menu" not in [w["code"] for w in resp.json()["warnings"]]


def test_errore_sul_menu_non_blocca_il_collegamento(auth_client, zernio, https_base, session, merchant):
    zernio.override["menu_get"] = _error(500, error="boom")

    resp = _connect(auth_client)

    assert resp.status_code == 200
    stored = _stored(session, merchant)
    assert stored["status"] == InstagramStatus.AWAITING_TEST_DM and stored["webhook_hook_id"]
    assert stored["menu"] is False and zernio.calls("menu_put") == []


def test_collegamento_account_non_in_elenco_404(auth_client, zernio, https_base, session, merchant):
    auth_client.post("/api/merchant/instagram/key", json={"api_key": NEW_KEY})

    resp = auth_client.post("/api/merchant/instagram/account", json={"account_id": "acc-sconosciuto"})

    assert resp.status_code == 404
    assert zernio.calls("webhook_create") == []
    assert _stored(session, merchant)["zernio_account_id"] is None


def test_collegamento_account_di_un_altro_negozio_409(
    auth_client, zernio, https_base, session, merchant, instagram_merchant,
):
    auth_client.post("/api/merchant/instagram/key", json={"api_key": NEW_KEY})

    resp = auth_client.post("/api/merchant/instagram/account", json={"account_id": INSTAGRAM_ACCOUNT_ID})

    assert resp.status_code == 409
    assert zernio.calls("webhook_create") == []
    assert _stored(session, merchant)["zernio_account_id"] is None
    assert _stored(session, instagram_merchant)["zernio_account_id"] == INSTAGRAM_ACCOUNT_ID


def test_collegamento_con_public_base_url_http_400_senza_chiamate(auth_client, zernio, monkeypatch, session, merchant):
    auth_client.post("/api/merchant/instagram/key", json={"api_key": NEW_KEY})
    zernio.requests.clear()
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "http://127.0.0.1:8001")

    resp = auth_client.post("/api/merchant/instagram/account", json={"account_id": INSTAGRAM_ACCOUNT_ID})

    assert resp.status_code == 400 and "https" in resp.json()["detail"]
    assert zernio.requests == []
    assert _stored(session, merchant)["zernio_account_id"] is None


@pytest.mark.parametrize("failure", [
    _error(500, error="boom"),
    _error(403, code="insufficient_permissions", required_group="webhooks"),
    _error(429, error="slow down"),
    httpx.ReadTimeout("timeout"),
    httpx.Response(200, json={"success": True}),  # risposta senza l'id del webhook
])
def test_errore_sul_webhook_502_e_nessun_campo_salvato(auth_client, zernio, https_base, session, merchant, failure):
    auth_client.post("/api/merchant/instagram/key", json={"api_key": NEW_KEY})
    zernio.override["webhook_create"] = failure

    resp = auth_client.post("/api/merchant/instagram/account", json={"account_id": INSTAGRAM_ACCOUNT_ID})

    assert resp.status_code == 502
    stored = _stored(session, merchant)
    assert stored["zernio_account_id"] is None and stored["webhook_hook_id"] is None
    assert stored["webhook_secret_enc"] is None and stored["zernio_webhook_id"] is None
    assert stored["status"] == InstagramStatus.NOT_CONNECTED
    assert decrypt_secret(stored["zernio_api_key_enc"]) == NEW_KEY  # la chiave resta: basta riprovare
    assert zernio.calls("menu_put") == []


def test_collegamento_senza_chiave_salvata_400(auth_client, zernio, https_base):
    resp = auth_client.post("/api/merchant/instagram/account", json={"account_id": INSTAGRAM_ACCOUNT_ID})
    assert resp.status_code == 400
    assert zernio.requests == []


def test_collegamento_gia_attivo_409_e_non_registra_un_secondo_webhook(zernio, https_base, client, instagram_merchant):
    app.dependency_overrides[get_current_merchant] = lambda: instagram_merchant

    resp = client.post("/api/merchant/instagram/account", json={"account_id": INSTAGRAM_ACCOUNT_ID})

    assert resp.status_code == 409
    assert zernio.calls("webhook_create") == []


# --- scollegamento ---

def test_scollega_rimuove_il_webhook_e_cancella_i_campi(zernio, client, session, instagram_merchant):
    instagram_merchant.zernio_webhook_id = "wh-9"
    instagram_merchant.persistent_menu_set = True
    session.add(instagram_merchant)
    session.commit()
    make_card(session, instagram_merchant)
    app.dependency_overrides[get_current_merchant] = lambda: instagram_merchant

    resp = client.delete("/api/merchant/instagram")

    assert resp.status_code == 200
    assert resp.json()["status"] == "not_connected" and resp.json()["username"] is None
    [delete] = zernio.calls("webhook_delete")
    assert delete.url.params["webhookId"] == "wh-9"
    assert delete.headers["Authorization"] == f"Bearer {ZERNIO_TEST_KEY}"
    stored = _stored(session, instagram_merchant)
    assert all(stored[f] is None for f in ZERNIO_FIELDS)
    assert stored["status"] == InstagramStatus.NOT_CONNECTED and stored["menu"] is False
    assert len(session.exec(select(Card)).all()) == 1  # le carte restano


def test_scollega_con_zernio_in_errore_cancella_comunque_e_logga(zernio, client, session, instagram_merchant, caplog):
    instagram_merchant.zernio_webhook_id = "wh-9"
    session.add(instagram_merchant)
    session.commit()
    app.dependency_overrides[get_current_merchant] = lambda: instagram_merchant
    zernio.override["webhook_delete"] = _error(500, error="boom")

    with caplog.at_level("DEBUG"):
        resp = client.delete("/api/merchant/instagram")

    assert resp.status_code == 200
    assert all(_stored(session, instagram_merchant)[f] is None for f in ZERNIO_FIELDS)
    assert "webhook non rimosso" in caplog.text.lower()
    assert ZERNIO_TEST_KEY not in caplog.text and WEBHOOK_TEST_SECRET not in caplog.text


def test_scollega_con_chiave_illeggibile_cancella_comunque(zernio, client, session, instagram_merchant):
    instagram_merchant.zernio_webhook_id = "wh-9"
    instagram_merchant.zernio_api_key_enc = "1:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    session.add(instagram_merchant)
    session.commit()
    app.dependency_overrides[get_current_merchant] = lambda: instagram_merchant

    assert client.delete("/api/merchant/instagram").status_code == 200
    assert zernio.requests == []
    assert _stored(session, instagram_merchant)["zernio_api_key_enc"] is None


def test_scollega_senza_configurazione_non_chiama_zernio(auth_client, zernio):
    resp = auth_client.delete("/api/merchant/instagram")
    assert resp.status_code == 200 and resp.json()["status"] == "not_connected"
    assert zernio.requests == []


def test_si_puo_ricollegare_dopo_lo_scollegamento(auth_client, zernio, https_base, session, merchant):
    assert _connect(auth_client).status_code == 200
    first_hook = _stored(session, merchant)["webhook_hook_id"]
    assert auth_client.delete("/api/merchant/instagram").status_code == 200

    assert _connect(auth_client).status_code == 200

    stored = _stored(session, merchant)
    assert stored["status"] == InstagramStatus.AWAITING_TEST_DM and stored["webhook_hook_id"] != first_hook


# --- pannello ---

def test_pannello_attivo_con_chiave_mascherata_e_quota(client, zernio, session, instagram_merchant):
    session.add(ZernioSendCounter(
        quota_scope=f"account:{INSTAGRAM_ACCOUNT_ID}", period=utc_now().strftime("%Y-%m"), sent=7600,
    ))
    session.commit()
    app.dependency_overrides[get_current_merchant] = lambda: instagram_merchant

    resp = client.get("/api/merchant/instagram")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active" and data["username"] == "bar_demo"
    assert data["key_masked"] == "…" + ZERNIO_TEST_KEY[-4:]
    assert data["quota"]["sent"] == 7600 and data["quota"]["percent"] == 76
    assert "quota" in [w["code"] for w in data["warnings"]]
    assert ZERNIO_TEST_KEY not in resp.text
    assert zernio.requests == []  # il pannello non chiama Zernio


def test_pannello_standby_recente_con_datetime_senza_fuso_di_sqlite(client, session, instagram_merchant):
    instagram_merchant.standby_detected_at = utc_now() - timedelta(days=1)
    session.add(instagram_merchant)
    session.commit()
    app.dependency_overrides[get_current_merchant] = lambda: instagram_merchant

    data = client.get("/api/merchant/instagram").json()

    assert "standby" in [w["code"] for w in data["warnings"]]


def test_pannello_standby_vecchio_non_avvisa(client, session, instagram_merchant):
    instagram_merchant.standby_detected_at = utc_now() - timedelta(days=30)
    session.add(instagram_merchant)
    session.commit()
    app.dependency_overrides[get_current_merchant] = lambda: instagram_merchant

    assert "standby" not in [w["code"] for w in client.get("/api/merchant/instagram").json()["warnings"]]


def test_pannello_senza_collegamento(auth_client):
    data = auth_client.get("/api/merchant/instagram").json()
    assert data["status"] == "not_connected" and data["key_masked"] is None and data["key_saved"] is False
    assert data["quota"] is None and data["warnings"] == []


def test_pannello_con_chiave_salvata_e_account_da_scegliere(auth_client, zernio):
    auth_client.post("/api/merchant/instagram/key", json={"api_key": NEW_KEY})
    data = auth_client.get("/api/merchant/instagram").json()
    assert data["status"] == "not_connected" and data["key_saved"] is True
    assert data["key_masked"] == "…" + NEW_KEY[-4:]


def test_pannello_con_chiave_non_valida(client, session, instagram_merchant):
    instagram_merchant.instagram_status = InstagramStatus.KEY_INVALID
    session.add(instagram_merchant)
    session.commit()
    app.dependency_overrides[get_current_merchant] = lambda: instagram_merchant

    data = client.get("/api/merchant/instagram").json()

    assert data["status"] == "key_invalid" and "key_invalid" in [w["code"] for w in data["warnings"]]


# --- accesso ---

@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/merchant/instagram/key", {"api_key": NEW_KEY}),
    ("get", "/api/merchant/instagram/accounts", None),
    ("post", "/api/merchant/instagram/account", {"account_id": "x"}),
    ("get", "/api/merchant/instagram", None),
    ("delete", "/api/merchant/instagram", None),
])
def test_senza_login_401(client, zernio, method, path, body):
    resp = getattr(client, method)(path, **({"json": body} if body else {}))
    assert resp.status_code == 401
    assert zernio.requests == []


def test_un_merchant_non_vede_ne_modifica_la_configurazione_di_un_altro(
    auth_client, zernio, session, merchant, instagram_merchant,
):
    panel = auth_client.get("/api/merchant/instagram").json()
    assert panel["status"] == "not_connected" and panel["username"] is None and panel["key_masked"] is None

    assert auth_client.delete("/api/merchant/instagram").status_code == 200

    other = _stored(session, instagram_merchant)
    assert other["status"] == InstagramStatus.ACTIVE and other["webhook_hook_id"] == "hook-opaco-123"
    assert decrypt_secret(other["zernio_api_key_enc"]) == ZERNIO_TEST_KEY
    assert zernio.requests == []


# --- nessun segreto ---

def test_nessun_segreto_in_log_e_risposte_sull_intero_flusso(auth_client, zernio, https_base, session, merchant, caplog):
    texts = []
    with caplog.at_level("DEBUG"):
        texts.append(auth_client.post("/api/merchant/instagram/key", json={"api_key": NEW_KEY}).text)
        texts.append(auth_client.get("/api/merchant/instagram/accounts").text)
        texts.append(auth_client.post("/api/merchant/instagram/account", json={"account_id": INSTAGRAM_ACCOUNT_ID}).text)
        texts.append(auth_client.get("/api/merchant/instagram").text)
        stored = _stored(session, merchant)
        hook_id = stored["webhook_hook_id"]
        webhook_secret = decrypt_secret(stored["webhook_secret_enc"])
        texts.append(auth_client.delete("/api/merchant/instagram").text)
        zernio.override["accounts"] = _error(401, code="invalid_credentials", error=f"bad key {NEW_KEY}")
        texts.append(auth_client.post("/api/merchant/instagram/key", json={"api_key": NEW_KEY}).text)
        zernio.override["accounts"] = _error(500, error=f"boom {NEW_KEY}")
        texts.append(auth_client.post("/api/merchant/instagram/key", json={"api_key": NEW_KEY}).text)

    for secret in (NEW_KEY, webhook_secret, hook_id):
        assert secret not in caplog.text
        assert all(secret not in text for text in texts)
    assert caplog.text  # il flusso ha davvero scritto qualcosa
