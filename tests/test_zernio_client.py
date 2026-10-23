"""
Test della shell di `zernio_service`: client httpx con `MockTransport` (nessuna rete), errori, nessun nuovo
tentativo sugli invii, `zernio_credentials_for`.
"""

import asyncio
import json
import logging

import httpx
import pytest

from app.core.config import settings
from app.core.crypto import encrypt_secret
from app.models.models import Merchant
from app.services import zernio_service as zs
from app.services.instagram_service import build_card_message
from app.services.zernio_service import ZernioError, ZernioErrorKind

KEY = "sk_" + "ab12" * 16
WEBHOOK_SECRET = "whsec-supersegreto-123"
CARD_URL = "https://fidelitree.example/c/tokensegreto"
BASE = settings.ZERNIO_BASE_URL.rstrip("/")


def _run(coro):
    return asyncio.run(coro)


def _creds(account_id="acc_1", webhook_secret=None):
    return zs.credentials_from_key(KEY, account_id) if webhook_secret is None else zs.ZernioCredentials(
        api_key=KEY, account_id=account_id, profile_id="p1", webhook_secret=webhook_secret,
        quota_scope="account:acc_1",
    )


def _mock(handler):
    """(client, richieste viste): `handler(request)` decide la risposta."""
    seen: list[httpx.Request] = []

    def wrapped(request):
        seen.append(request)
        return handler(request)

    return httpx.AsyncClient(transport=httpx.MockTransport(wrapped)), seen


def _ok(payload):
    return lambda request: httpx.Response(200, json=payload)


def _call(client, coro_fn):
    """Esegue `coro_fn(http)` con `client` e lo chiude."""
    async def go():
        async with client as http:
            return await coro_fn(http)
    return _run(go())


# --- invio della card ---

def test_send_card_metodo_path_header_e_corpo():
    client, seen = _mock(_ok({"success": True, "data": {"messageId": "m_1", "conversationId": "conv/1"}}))
    card = build_card_message("Bar Demo", CARD_URL)

    mid = _call(client, lambda http: zs.send_card(http, _creds(), "conv/1", card, "idem-123"))

    assert mid == "m_1"
    assert len(seen) == 1
    req = seen[0]
    assert req.method == "POST"
    assert str(req.url) == f"{BASE}/v1/inbox/conversations/conv%2F1/messages"
    assert req.headers["Authorization"] == f"Bearer {KEY}"
    assert req.headers["Idempotency-Key"] == "idem-123"
    assert json.loads(req.read()) == zs.build_card_body("acc_1", card)


def test_send_text_corpo_e_message_id():
    client, seen = _mock(_ok({"success": True, "data": {"messageId": "m_2"}}))

    mid = _call(client, lambda http: zs.send_text(http, _creds(), "conv1", "ciao", "idem-9"))

    assert mid == "m_2"
    assert json.loads(seen[0].read()) == {"accountId": "acc_1", "message": "ciao"}
    assert seen[0].headers["Idempotency-Key"] == "idem-9"


def test_send_senza_message_id_nella_risposta_non_solleva():
    # 200 = consegnato: sollevare farebbe partire il ripiego e il cliente riceverebbe due messaggi
    client, _ = _mock(_ok({"success": True}))
    assert _call(client, lambda http: zs.send_text(http, _creds(), "c", "x", "i")) == ""


def test_i_timeout_di_invio_e_configurazione():
    assert zs.SEND_TIMEOUT == 3.0
    assert zs.CONFIG_TIMEOUT == 10.0


def test_invii_e_configurazione_usano_ciascuno_il_proprio_timeout(monkeypatch):
    timeouts = []
    client, _ = _mock(_ok({"data": {"messageId": "m"}, "accounts": []}))
    real = client.request

    async def spy(*a, **kw):
        timeouts.append(kw.get("timeout"))
        return await real(*a, **kw)

    monkeypatch.setattr(client, "request", spy)

    async def both(http):
        await zs.send_text(http, _creds(), "c", "x", "i")
        await zs.list_instagram_accounts(http, _creds())

    _call(client, both)
    assert timeouts == [3.0, 10.0]


# --- errori ---

def _error_case(status, body, kind):
    client, seen = _mock(lambda r: httpx.Response(status, json=body) if body is not None else httpx.Response(status))
    card = build_card_message("Bar Demo", CARD_URL)
    with pytest.raises(ZernioError) as exc:
        _call(client, lambda http: zs.send_card(http, _creds(), "conv1", card, "idem"))
    assert exc.value.kind == kind
    assert exc.value.status == status
    assert KEY not in str(exc.value) and CARD_URL not in str(exc.value) and "tokensegreto" not in str(exc.value)
    assert len(seen) == 1  # nessun nuovo tentativo
    return exc.value


def test_401_e_auth():
    _error_case(401, {"error": "Invalid API key", "code": "invalid_credentials"}, ZernioErrorKind.AUTH)


def test_409_not_thread_owner():
    _error_case(409, {"error": "x", "code": "not_thread_owner"}, ZernioErrorKind.NOT_THREAD_OWNER)


def test_500_e_server_e_non_si_ritenta():
    _error_case(500, {"error": "boom"}, ZernioErrorKind.SERVER)


def test_500_con_corpo_non_json():
    _error_case(500, None, ZernioErrorKind.SERVER)


def test_403_quota():
    _error_case(403, {"code": "message_allowance_exceeded"}, ZernioErrorKind.QUOTA)


def test_403_generico_e_bad_request_non_auth():
    _error_case(403, {"error": "Inbox addon required"}, ZernioErrorKind.BAD_REQUEST)


def test_400_non_follower():
    _error_case(
        400, {"code": "platform_api_error", "platformError": {"code": 2, "subcode": 1545133}},
        ZernioErrorKind.NOT_FOLLOWER,
    )


def test_429_rate_limited():
    _error_case(429, {"error": "slow down"}, ZernioErrorKind.RATE_LIMITED)


@pytest.mark.parametrize("exc", [
    httpx.ReadTimeout("timeout"),
    httpx.ConnectTimeout("timeout"),
    httpx.ConnectError("rete assente"),
])
def test_eccezione_di_rete_o_timeout_e_server_senza_nuovo_tentativo(exc):
    seen = []

    def handler(request):
        seen.append(request)
        raise exc

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    card = build_card_message("Bar Demo", CARD_URL)
    with pytest.raises(ZernioError) as e:
        _call(client, lambda http: zs.send_card(http, _creds(), "c", card, "i"))
    assert e.value.kind == ZernioErrorKind.SERVER
    assert e.value.status is None
    assert KEY not in str(e.value)
    assert len(seen) == 1


def test_il_testo_dell_errore_zernio_non_arriva_nel_messaggio():
    err = _error_case(400, {"error": f"chiave {KEY} non valida", "code": "validation_error"}, ZernioErrorKind.BAD_REQUEST)
    assert KEY not in str(err)


def test_log_degli_errori_senza_segreti(caplog):
    client, _ = _mock(lambda r: httpx.Response(401, json={"error": f"bad {KEY}", "code": "invalid_credentials"}))
    card = build_card_message("Bar Demo", CARD_URL)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ZernioError):
            _call(client, lambda http: zs.send_card(http, _creds(), "conv1", card, "idem"))
    assert KEY not in caplog.text and "tokensegreto" not in caplog.text


def test_senza_account_le_chiamate_che_lo_richiedono_sono_not_configured():
    client, seen = _mock(_ok({}))
    with pytest.raises(ZernioError) as e:
        _call(client, lambda http: zs.send_text(http, zs.credentials_from_key(KEY), "c", "x", "i"))
    assert e.value.kind == ZernioErrorKind.NOT_CONFIGURED
    assert seen == []


# --- account ---

def test_list_instagram_accounts_query_string_e_parsing():
    client, seen = _mock(_ok({"accounts": [
        {"_id": "a1", "platform": "instagram", "username": "bar_demo", "profileId": "p1"},
        {"_id": "a2", "platform": "facebook", "username": "pagina"},
    ]}))

    accounts = _call(client, lambda http: zs.list_instagram_accounts(http, zs.credentials_from_key(KEY)))

    assert [a.id for a in accounts] == ["a1"]
    req = seen[0]
    assert req.method == "GET"
    assert req.url.path == "/api/v1/accounts"
    assert dict(req.url.params) == {"platform": "instagram", "status": "connected"}
    assert req.url.query.decode() == "platform=instagram&status=connected"
    assert req.headers["Authorization"] == f"Bearer {KEY}"


def test_list_instagram_accounts_401():
    client, _ = _mock(lambda r: httpx.Response(401, json={"code": "invalid_credentials"}))
    with pytest.raises(ZernioError) as e:
        _call(client, lambda http: zs.list_instagram_accounts(http, zs.credentials_from_key(KEY)))
    assert e.value.kind == ZernioErrorKind.AUTH


# --- webhook ---

def test_register_webhook_corpo_e_id():
    client, seen = _mock(_ok({"success": True, "webhook": {"_id": "wh_123", "name": "Fidelitree"}}))

    wid = _call(client, lambda http: zs.register_webhook(
        http, _creds(), "https://app.example/webhooks/zernio/hook", WEBHOOK_SECRET))

    assert wid == "wh_123"
    req = seen[0]
    assert req.method == "POST" and req.url.path == "/api/v1/webhooks/settings"
    body = json.loads(req.read())
    assert body["events"] == ["message.received"]
    assert body["secret"] == WEBHOOK_SECRET
    assert body["accountIds"] == ["acc_1"]
    assert body["isActive"] is True and body["name"] == "Fidelitree"
    assert body["url"] == "https://app.example/webhooks/zernio/hook"


def test_register_webhook_senza_id_nella_risposta_e_un_errore_senza_segreti():
    client, _ = _mock(_ok({"success": True}))
    with pytest.raises(ZernioError) as e:
        _call(client, lambda http: zs.register_webhook(http, _creds(), "https://x.example/h", WEBHOOK_SECRET))
    assert e.value.kind == ZernioErrorKind.SERVER
    assert WEBHOOK_SECRET not in str(e.value)


def test_delete_webhook_usa_webhook_id_in_query():
    client, seen = _mock(_ok({"success": True}))

    result = _call(client, lambda http: zs.delete_webhook(http, _creds(), "507f1f77bcf86cd799439011"))

    assert result is None
    req = seen[0]
    assert req.method == "DELETE" and req.url.path == "/api/v1/webhooks/settings"
    assert dict(req.url.params) == {"webhookId": "507f1f77bcf86cd799439011"}
    assert req.content == b""


# --- menu persistente ---

def test_get_persistent_menu():
    menu = [{"persistent_menu": [{"locale": "default", "call_to_actions": []}]}]
    client, seen = _mock(_ok({"data": menu}))

    assert _call(client, lambda http: zs.get_persistent_menu(http, _creds())) == menu
    assert seen[0].method == "GET" and seen[0].url.path == "/api/v1/accounts/acc_1/messenger-menu"


def test_get_persistent_menu_senza_data_e_vuoto():
    client, _ = _mock(_ok({}))
    assert _call(client, lambda http: zs.get_persistent_menu(http, _creds())) == []


def test_set_persistent_menu():
    client, seen = _mock(_ok({"success": True}))

    result = _call(client, lambda http: zs.set_persistent_menu(http, _creds(), "🌳 La mia carta", "FIDELITREE_CARD"))

    assert result is None
    req = seen[0]
    assert req.method == "PUT" and req.url.path == "/api/v1/accounts/acc_1/messenger-menu"
    assert json.loads(req.read()) == zs.build_menu_body("🌳 La mia carta", "FIDELITREE_CARD")


# --- conversazioni ---

def test_list_conversations_default_e_folder():
    client, seen = _mock(_ok({"data": [{"id": "c1", "updatedTime": "2026-10-22T10:00:00Z"}]}))

    convs = _call(client, lambda http: zs.list_conversations(http, _creds()))
    assert convs == [{"id": "c1", "updatedTime": "2026-10-22T10:00:00Z"}]
    assert dict(seen[0].url.params) == {"accountId": "acc_1", "platform": "instagram"}

    client, seen = _mock(_ok({"data": []}))
    _call(client, lambda http: zs.list_conversations(http, _creds(), folder="requests"))
    assert dict(seen[0].url.params) == {"accountId": "acc_1", "platform": "instagram", "folder": "requests"}


# --- identità del team ---

def test_get_team_identity_senza_campo_affidabile_e_none():
    client, seen = _mock(_ok({"currentUserId": "u1", "users": [{"_id": "u1", "isRoot": True}]}))
    assert _call(client, lambda http: zs.get_team_identity(http, _creds())) is None
    assert seen == []  # nessun campo identifica il team: nessuna chiamata inutile


# --- http client e dependency ---

def test_make_http_client_usa_il_timeout_dato():
    async def go():
        async with zs.make_http_client(10.0) as client:
            return client.timeout
    assert _run(go()).read == 10.0


def test_get_zernio_http_e_una_dependency_sovrascrivibile():
    from app.main import app

    async def fake():
        yield "client-finto"

    app.dependency_overrides[zs.get_zernio_http] = fake
    try:
        assert app.dependency_overrides[zs.get_zernio_http] is fake
    finally:
        app.dependency_overrides.pop(zs.get_zernio_http, None)


def test_get_zernio_http_apre_e_chiude_il_client():
    async def go():
        gen = zs.get_zernio_http()
        client = await gen.__anext__()
        assert isinstance(client, httpx.AsyncClient) and not client.is_closed
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
        return client.is_closed
    assert _run(go()) is True


# --- zernio_credentials_for ---

def _merchant(**fields):
    return Merchant(business_name="Bar Demo", email="m@test.it", **fields)


def test_credenziali_dal_merchant_con_team():
    m = _merchant(
        zernio_api_key_enc=encrypt_secret(KEY), zernio_account_id="acc_9", zernio_profile_id="p9",
        zernio_team_id="team_7", webhook_secret_enc=encrypt_secret(WEBHOOK_SECRET),
    )

    creds = zs.zernio_credentials_for(m)

    assert creds.api_key.get_secret_value() == KEY
    assert creds.webhook_secret.get_secret_value() == WEBHOOK_SECRET
    assert creds.account_id == "acc_9" and creds.profile_id == "p9"
    assert creds.quota_scope == "zernio:team_7"
    assert KEY not in repr(creds) and WEBHOOK_SECRET not in repr(creds)


def test_credenziali_senza_team_ripiegano_sull_account():
    m = _merchant(zernio_api_key_enc=encrypt_secret(KEY), zernio_account_id="acc_9")

    creds = zs.zernio_credentials_for(m)

    assert creds.quota_scope == "account:acc_9"
    assert creds.webhook_secret is None and creds.profile_id is None


def test_credenziali_merchant_senza_chiave():
    with pytest.raises(ZernioError) as e:
        zs.zernio_credentials_for(_merchant(zernio_account_id="acc_9"))
    assert e.value.kind == ZernioErrorKind.NOT_CONFIGURED


def test_credenziali_merchant_senza_account():
    with pytest.raises(ZernioError) as e:
        zs.zernio_credentials_for(_merchant(zernio_api_key_enc=encrypt_secret(KEY)))
    assert e.value.kind == ZernioErrorKind.NOT_CONFIGURED


def test_credenziali_con_chiave_illeggibile_sono_not_configured_senza_dettagli():
    m = _merchant(zernio_api_key_enc="1:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", zernio_account_id="acc_9")
    with pytest.raises(ZernioError) as e:
        zs.zernio_credentials_for(m)
    assert e.value.kind == ZernioErrorKind.NOT_CONFIGURED


def test_credentials_from_key():
    creds = zs.credentials_from_key(KEY)
    assert creds.account_id is None and creds.quota_scope == ""
    assert KEY not in repr(creds)
    assert zs.credentials_from_key(KEY, "acc_3").quota_scope == "account:acc_3"
