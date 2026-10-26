"""
Test degli script di supporto: seed del DB, smoke test, reset del DB.
Tutto su SQLite in-memory (fixture `session`/`client`), senza rete e senza Ecologi.
"""

import json
import re
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.config import settings
from app.core.clock import utc_now
from app.core.crypto import encrypt_secret
from app.core.dependencies import get_session
from app.core.enums import InstagramStatus, Level, WebhookOutcome
from app.main import app
from app.models.models import (
    Card, Merchant, MerchantPool, PointTransaction, ProcessedWebhookEvent, ZernioSendCounter,
)
from app.services import ecologi_service, instagram_service, tree_service, zernio_service
from app.version import get_version
from scripts import ecologi_check, replay_webhook, reset_db, seed_db, smoke_test_prod, zernio_check
from scripts.smoke_test_prod import run_smoke_test
from tests.conftest import WEBHOOK_TEST_SECRET, ZERNIO_TEST_KEY

NOW = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
PERIOD = "2026-10"


def _count(session, model) -> int:
    return len(session.exec(select(model)).all())


# --- seed ---

def test_seed_crea_merchant_carte_e_movimenti(session):
    entries = seed_db.seed(session, now=NOW)

    assert len(entries) == 2
    merchants = session.exec(select(Merchant)).all()
    assert len(merchants) == 2
    assert all(m.is_approved and m.auth_user_id for m in merchants)
    assert _count(session, Card) == 4  # ogni cliente finto ha una carta presso ciascun negozio
    assert all(c.igsid_hash and c.link_token_hash for c in session.exec(select(Card)).all())
    assert _count(session, PointTransaction) > 0
    # un merchant con conversione e uno "solo alberi", con soglie diverse
    assert {m.conversion_enabled for m in merchants} == {True, False}
    assert len({(m.bronze_threshold, m.gold_threshold) for m in merchants}) == 2


def test_seed_converte_in_cashback_nel_negozio_con_conversione(session):
    entries = seed_db.seed(session, now=NOW)
    bar = next(e for e in entries if e.merchant.conversion_enabled)
    anna = session.get(Card, bar.cards["anna"].id)
    assert anna.cashback_cents == 200 and anna.tree_points == 10  # 60 punti: 50 → 2 €, restano 10


def test_seed_e_idempotente(session):
    seed_db.seed(session, now=NOW)
    snapshot = (
        _count(session, Merchant), _count(session, Card),
        _count(session, PointTransaction), [p.points for p in session.exec(select(MerchantPool)).all()],
    )

    seed_db.seed(session, now=NOW)

    assert snapshot == (
        _count(session, Merchant), _count(session, Card),
        _count(session, PointTransaction), [p.points for p in session.exec(select(MerchantPool)).all()],
    )


def test_seed_produce_pool_coerenti_e_un_piano_utile_al_collaudo(session):
    seed_db.seed(session, now=NOW)

    assert tree_service.pool_mismatches(session, PERIOD) == []
    plan = tree_service.build_closure_plan(session, PERIOD, global_cap=settings.ECOLOGI_GLOBAL_MONTHLY_CAP)
    levels = {line.business_name: line.level for line in plan.lines}
    assert levels["Bar Demo"] == Level.GOLD
    assert levels["Forno Solo Alberi"] == Level.NONE
    assert not plan.exceeds_cap


@pytest.fixture()
def seed_engine(monkeypatch):
    """Engine SQLite in-memory con lo schema, installato come `seed_db.engine` (il DB vero non si tocca)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(seed_db, "engine", engine)
    yield engine
    engine.dispose()


def test_main_del_seed_stampa_credenziali_e_id_delle_carte_senza_link(seed_engine, capsys, caplog):
    seed_db.main([])  # stampa a sessione aperta: fuori da essa i modelli sarebbero scollegati

    out = capsys.readouterr().out
    assert settings.DEV_AUTH_PASSWORD in out and "demo@fidelitree.it" in out
    assert "Carta di anna: id " in out
    assert "/join" not in out and "/wallet" not in out and "/c/" not in out  # il token del link è un segreto
    with Session(seed_engine) as s:
        for card in s.exec(select(Card)).all():
            assert instagram_service.card_link_url(card).rsplit("/", 1)[1] not in out + caplog.text


def test_la_stampa_del_seed_si_codifica_nella_console_windows(seed_engine, capsys):
    """Su una console cp1252 un carattere come la freccia darebbe `UnicodeEncodeError`."""
    seed_db.main(["--links"])

    out = capsys.readouterr().out
    out.encode("cp1252")


def test_main_del_seed_con_links_stampa_i_link_che_aprono_la_pagina_carta(seed_engine, client, capsys, caplog):
    def override_get_session():
        with Session(seed_engine) as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session

    seed_db.main(["--links"])

    out = capsys.readouterr().out
    links = re.findall(r"(?<=Link: )\S+/c/\S+", out)
    assert len(links) == 4  # due carte per ciascuno dei due negozi
    for link in links:
        assert client.get(link[link.index("/c/"):]).status_code == 200
    with Session(seed_engine) as s:
        assert set(links) == {instagram_service.card_link_url(c) for c in s.exec(select(Card)).all()}
        # il token non passa dal logger, solo da stdout
        assert all(link.rsplit("/", 1)[1] not in caplog.text for link in links)


def test_seed_rifiuta_provider_diversi_da_dev(session, monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "supabase")
    with pytest.raises(RuntimeError, match="AUTH_PROVIDER=dev"):
        seed_db.seed(session, now=NOW)
    assert _count(session, Merchant) == 0


def test_i_merchant_del_seed_possono_accedere(client, session, auth_provider):
    seed_db.seed(session, now=NOW)

    ok = client.post(
        "/merchant/login",
        data={"email": "demo@fidelitree.it", "password": settings.DEV_AUTH_PASSWORD},
        follow_redirects=False,
    )
    assert ok.status_code == 303 and ok.headers["location"] == "/merchant/scanner"
    assert "access_token" in ok.cookies

    wrong = client.post(
        "/merchant/login",
        data={"email": "demo@fidelitree.it", "password": "sbagliata"},
        follow_redirects=False,
    )
    assert wrong.status_code == 401


# --- smoke test ---

def test_smoke_test_su_app_locale_passa_e_non_pianta_alberi(client, mock_ecologi, session):
    assert run_smoke_test("", settings.ADMIN_SECRET_KEY, http=client) is True

    assert mock_ecologi == []  # nessuna chiamata a Ecologi
    assert _count(session, Merchant) == 0  # il merchant di prova è stato cancellato
    assert _count(session, PointTransaction) == 0


def test_smoke_test_con_chiave_admin_sbagliata_fallisce(client, mock_ecologi):
    assert run_smoke_test("", "chiave-sbagliata", http=client) is False


def test_smoke_test_non_invia_nulla_a_zernio_e_non_crea_carte(client, zernio_mock, mock_ecologi, session):
    assert run_smoke_test("", settings.ADMIN_SECRET_KEY, http=client) is True

    assert zernio_mock.requests == []
    assert mock_ecologi == []
    assert _count(session, Card) == 0
    assert _count(session, ProcessedWebhookEvent) == 0  # il webhook di prova si ferma prima di ogni scrittura


def test_la_versione_attesa_dallo_smoke_test_e_quella_di_pyproject():
    """Al prossimo bump questo test ricorda di aggiornare `EXPECTED_VERSION`."""
    assert smoke_test_prod.EXPECTED_VERSION == get_version()


class _SmokeHttp:
    """Client che inoltra al `TestClient` ma risponde con `fake` per i percorsi indicati (metodo, percorso)."""

    def __init__(self, client, fake: dict):
        self.client, self.fake = client, fake

    def _call(self, method: str, url: str, **kwargs):
        if (method, url) in self.fake:
            return self.fake[(method, url)]
        return getattr(self.client, method.lower())(url, **kwargs)

    def get(self, url, **kwargs):
        return self._call("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._call("POST", url, **kwargs)

    def delete(self, url, **kwargs):
        return self._call("DELETE", url, **kwargs)


@pytest.mark.parametrize("method, path, response", [
    ("GET", "/wallet", httpx.Response(200, text="<html></html>", headers={"Content-Type": "text/html"})),
    ("GET", "/join/1", httpx.Response(200, text="<html></html>", headers={"Content-Type": "text/html"})),
    ("GET", "/static/manifest.webmanifest", httpx.Response(200, json={"start_url": "/wallet"})),
    ("GET", "/c/token-inesistente", httpx.Response(200, text="<html></html>", headers={"Content-Type": "text/html"})),
    ("POST", "/webhooks/zernio/hook-inesistente", httpx.Response(200, json={"status": "ok"})),
    ("GET", "/privacy", httpx.Response(404)),
    ("GET", "/sw.js", httpx.Response(404)),
    ("GET", "/health", httpx.Response(200, json={"status": "ok", "version": "0.2.1"})),
])
def test_smoke_test_fallisce_se_una_risposta_non_e_quella_attesa(client, method, path, response):
    http = _SmokeHttp(client, {(method, path): response})

    assert run_smoke_test("", settings.ADMIN_SECRET_KEY, http=http) is False


def test_smoke_test_stampa_quale_controllo_e_fallito(client, capsys):
    wallet = httpx.Response(200, text="<html></html>", headers={"Content-Type": "text/html"})

    run_smoke_test("", settings.ADMIN_SECRET_KEY, http=_SmokeHttp(client, {("GET", "/wallet"): wallet}))

    assert "[FAIL] Pagina vecchia /wallet rimossa" in capsys.readouterr().out


# --- reset_db ---

def test_reset_db_ricrea_lo_schema_vuoto(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Merchant.model_validate({"business_name": "Bar Prova", "email": "x@y.it"}))
        s.commit()
    monkeypatch.setattr(reset_db, "engine", engine)

    reset_db.reset_db()

    tables = set(inspect(engine).get_table_names())
    assert {"merchant", "card", "pointtransaction", "merchantpool", "treeplanting"} <= tables
    assert "customer" not in tables
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM merchant").scalar() == 0
    engine.dispose()


# --- ecologi_check ---

@pytest.fixture()
def eco_http(monkeypatch):
    """Chiavi finte e httpx mockato: ritorna la lista delle richieste viste da Ecologi."""
    monkeypatch.setattr(settings, "ECOLOGI_BASE_URL", "https://eco.real")
    monkeypatch.setattr(settings, "ECOLOGI_API_KEY", "real-key-9999")
    monkeypatch.setattr(settings, "ECOLOGI_TEST_API_KEY", "test-key-1234")
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(201, json={
            "amount": 0.8, "currency": "EUR", "treeUrl": "https://ecologi.com/x?tree=1",
            "projectDetails": [{"name": "Progetto Uno"}],
        })

    real = httpx.AsyncClient
    monkeypatch.setattr(
        ecologi_service.httpx, "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    return seen


def test_ecologi_check_in_test_mode(eco_http, monkeypatch, capsys):
    monkeypatch.setattr(settings, "ECOLOGI_TEST_MODE", True)
    month = tree_service.period_for(datetime.now(timezone.utc))
    assert ecologi_check.main([]) == 0
    assert len(eco_http) == 1
    req = eco_http[0]
    assert req.headers["Authorization"] == "Bearer test-key-1234"
    body = json.loads(req.read())
    assert body == {"number": 1, "name": tree_service.planting_name("Negozio di prova", month), "test": True}
    out = capsys.readouterr().out
    assert "https://ecologi.com/x?tree=1" in out and "Progetto Uno" in out
    assert "di test" in out and "test-key-1234" not in out


def test_ecologi_check_con_chiave_reale_manda_comunque_test(eco_http, monkeypatch, capsys):
    monkeypatch.setattr(settings, "ECOLOGI_TEST_MODE", False)
    assert ecologi_check.main([]) == 0
    assert eco_http[0].headers["Authorization"] == "Bearer real-key-9999"
    assert json.loads(eco_http[0].read())["test"] is True
    out = capsys.readouterr().out
    assert "REALE" in out and "real-key-9999" not in out and "…9999" in out


def test_ecologi_check_argomenti(eco_http, monkeypatch):
    monkeypatch.setattr(settings, "ECOLOGI_TEST_MODE", True)
    assert ecologi_check.main(["--trees", "3", "--merchant-name", "Bar Demo", "--month", "2026-10"]) == 0
    assert json.loads(eco_http[0].read()) == {"number": 3, "name": "Bar Demo · ottobre 2026", "test": True}


def test_ecologi_check_chiave_mancante(eco_http, monkeypatch, capsys):
    monkeypatch.setattr(settings, "ECOLOGI_TEST_MODE", True)
    monkeypatch.setattr(settings, "ECOLOGI_TEST_API_KEY", "")
    assert ecologi_check.main([]) == 1
    assert eco_http == []
    assert "Chiave Ecologi di test non configurata" in capsys.readouterr().err


def test_ecologi_check_http_401(monkeypatch, capsys):
    monkeypatch.setattr(settings, "ECOLOGI_TEST_MODE", True)
    monkeypatch.setattr(settings, "ECOLOGI_TEST_API_KEY", "test-key-1234")
    real = httpx.AsyncClient
    monkeypatch.setattr(
        ecologi_service.httpx, "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(401, text="no")), **kw),
    )
    assert ecologi_check.main([]) == 1
    assert "HTTP 401" in capsys.readouterr().err


def test_ecologi_check_non_apre_sessioni_db(eco_http, monkeypatch, session):
    monkeypatch.setattr(settings, "ECOLOGI_TEST_MODE", True)
    assert ecologi_check.main([]) == 0
    assert _count(session, tree_service.TreePlanting) == 0


# --- zernio_check ---

ZERNIO_KEY = "sk_" + "cd34" * 16


@pytest.fixture()
def zernio_http(monkeypatch):
    """Chiave da env e httpx mockato: ritorna la lista delle richieste viste da Zernio."""
    monkeypatch.setenv("ZERNIO_CHECK_API_KEY", ZERNIO_KEY)
    monkeypatch.setattr(zernio_check.getpass, "getpass", lambda prompt="": "")
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/api/v1/accounts":
            return httpx.Response(200, json={"accounts": [
                {"_id": "acc_1", "platform": "instagram", "username": "bar_demo"},
                {"_id": "acc_2", "platform": "facebook", "username": "pagina"},
            ]})
        if request.url.path == "/api/v1/inbox/conversations":
            return httpx.Response(200, json={"data": [{
                "id": "conv_1", "updatedTime": "2026-10-22T10:00:00Z",
                "participantId": "IGSID-9999", "participantName": "Mario Rossi",
                "instagramProfile": {"isFollower": True},
            }]})
        return httpx.Response(200, json={"success": True, "data": {"messageId": "m_1"}})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        zernio_service.httpx, "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    return seen


def test_zernio_check_accounts_con_chiave_da_env(zernio_http, capsys):
    assert zernio_check.main(["accounts"]) == 0

    out = capsys.readouterr().out
    assert "…cd34" in out and ZERNIO_KEY not in out
    assert "acc_1" in out and "@bar_demo" in out and "acc_2" not in out
    assert len(zernio_http) == 1
    assert zernio_http[0].headers["Authorization"] == f"Bearer {ZERNIO_KEY}"


def test_zernio_check_accounts_401(monkeypatch, capsys):
    monkeypatch.setenv("ZERNIO_CHECK_API_KEY", ZERNIO_KEY)
    real = httpx.AsyncClient
    monkeypatch.setattr(
        zernio_service.httpx, "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(
            lambda r: httpx.Response(401, json={"error": "no", "code": "invalid_credentials"})), **kw),
    )

    assert zernio_check.main(["accounts"]) == 1

    captured = capsys.readouterr()
    assert "auth" in captured.err and "401" in captured.err
    assert ZERNIO_KEY not in captured.out + captured.err


def test_zernio_check_chiave_mancante(zernio_http, monkeypatch, capsys):
    monkeypatch.delenv("ZERNIO_CHECK_API_KEY")

    assert zernio_check.main(["accounts"]) == 1

    assert zernio_http == []
    assert "ZERNIO_CHECK_API_KEY" in capsys.readouterr().err


def test_zernio_check_chiede_la_chiave_a_video_se_manca_l_env(zernio_http, monkeypatch, capsys):
    monkeypatch.delenv("ZERNIO_CHECK_API_KEY")
    monkeypatch.setattr(zernio_check.getpass, "getpass", lambda prompt="": ZERNIO_KEY)

    assert zernio_check.main(["accounts"]) == 0

    assert zernio_http[0].headers["Authorization"] == f"Bearer {ZERNIO_KEY}"
    assert ZERNIO_KEY not in capsys.readouterr().out


def test_zernio_check_non_accetta_la_chiave_da_riga_di_comando(zernio_http, capsys):
    with pytest.raises(SystemExit):
        zernio_check.main(["accounts", "--api-key", ZERNIO_KEY])
    assert zernio_http == []


def test_zernio_check_conversations_non_stampa_dati_dei_clienti(zernio_http, capsys):
    assert zernio_check.main(["conversations", "--account-id", "acc_1", "--folder", "requests"]) == 0

    out = capsys.readouterr().out
    assert "conv_1" in out and "2026-10-22T10:00:00Z" in out
    assert "IGSID-9999" not in out and "Mario" not in out
    assert dict(zernio_http[0].url.params) == {"accountId": "acc_1", "platform": "instagram", "folder": "requests"}


def test_zernio_check_send_card_invia_un_solo_post_con_il_corpo_del_core(zernio_http, capsys):
    argv = ["send-card", "--account-id", "acc_1", "--conversation-id", "conv_1",
            "--name", "Bar Demo", "--url", "https://fidelitree.example/c/x"]

    assert zernio_check.main(argv) == 0

    assert len(zernio_http) == 1
    req = zernio_http[0]
    assert req.method == "POST" and req.url.path == "/api/v1/inbox/conversations/conv_1/messages"
    assert req.headers["Idempotency-Key"]
    card = instagram_service.build_card_message("Bar Demo", "https://fidelitree.example/c/x")
    assert json.loads(req.read()) == zernio_service.build_card_body("acc_1", card)
    out = capsys.readouterr().out
    assert "m_1" in out and ZERNIO_KEY not in out


def test_zernio_check_send_text(zernio_http):
    argv = ["send-text", "--account-id", "acc_1", "--conversation-id", "conv_1", "--name", "Bar Demo"]

    assert zernio_check.main(argv) == 0

    assert len(zernio_http) == 1
    text = instagram_service.build_fallback_text("Bar Demo", zernio_check.DEFAULT_URL)
    assert json.loads(zernio_http[0].read()) == {"accountId": "acc_1", "message": text}


def test_zernio_check_url_non_https_non_chiama_zernio(zernio_http, capsys):
    argv = ["send-card", "--account-id", "acc_1", "--conversation-id", "conv_1", "--url", "http://x.example/c/t"]

    assert zernio_check.main(argv) == 1

    assert zernio_http == []
    assert "https://" in capsys.readouterr().err


def test_zernio_check_non_apre_sessioni_db(zernio_http, session):
    assert zernio_check.main(["accounts"]) == 0
    assert _count(session, Merchant) == 0


def test_zernio_check_senza_merchant_l_account_id_e_obbligatorio_per_conversazioni_e_invii(zernio_http, capsys):
    assert zernio_check.main(["send-card", "--conversation-id", "conv_1"]) == 1

    assert zernio_http == []
    assert "--account-id" in capsys.readouterr().err


# --- zernio_check --merchant-id ---

def _check_merchant(session, merchant_id, *argv):
    return zernio_check.main([*argv, "--merchant-id", str(merchant_id)], session=session)


def test_zernio_check_merchant_mostra_stato_e_chiave_mascherata(zernio_http, instagram_merchant, session, capsys):
    session.add(ZernioSendCounter(quota_scope="account:acc-1", period=utc_now().strftime("%Y-%m"), sent=7))
    session.commit()

    assert _check_merchant(session, instagram_merchant.id, "accounts") == 0

    captured = capsys.readouterr()
    shown = captured.out + captured.err
    assert "active" in captured.out and "@bar_demo" in captured.out
    assert "…ef56" in captured.out and "Invii del mese: 7" in captured.out
    assert ZERNIO_TEST_KEY not in shown and ZERNIO_KEY not in shown
    assert "Bar Demo" not in shown  # il nome può contenere emoji: la console Windows non le stampa
    # la chiamata usa la chiave salvata del negozio, non quella dell'ambiente
    assert zernio_http[0].headers["Authorization"] == f"Bearer {ZERNIO_TEST_KEY}"


def test_zernio_check_merchant_non_chiede_la_chiave_a_video(zernio_http, instagram_merchant, session, monkeypatch):
    monkeypatch.delenv("ZERNIO_CHECK_API_KEY")

    def no_prompt(prompt=""):
        raise AssertionError("la chiave del negozio non si chiede a video")

    monkeypatch.setattr(zernio_check.getpass, "getpass", no_prompt)

    assert _check_merchant(session, instagram_merchant.id, "accounts") == 0


def test_zernio_check_merchant_invia_sull_account_del_negozio(zernio_http, instagram_merchant, session):
    argv = ["--conversation-id", "conv_1", "--name", "Bar Demo", "--url", "https://fidelitree.example/c/x"]

    assert _check_merchant(session, instagram_merchant.id, "send-card", *argv) == 0

    request = zernio_http[0]
    assert request.url.path == "/api/v1/inbox/conversations/conv_1/messages"
    assert json.loads(request.read())["accountId"] == "acc-1"
    assert request.headers["Authorization"] == f"Bearer {ZERNIO_TEST_KEY}"


def test_zernio_check_merchant_con_account_id_esplicito_lo_preferisce(zernio_http, instagram_merchant, session):
    assert _check_merchant(session, instagram_merchant.id, "conversations", "--account-id", "altro") == 0

    assert dict(zernio_http[0].url.params)["accountId"] == "altro"


def test_zernio_check_merchant_con_chiave_ma_senza_account_puo_elencare_gli_account(zernio_http, merchant, session, capsys):
    merchant.zernio_api_key_enc = encrypt_secret(ZERNIO_TEST_KEY)
    merchant.instagram_status = InstagramStatus.NOT_CONNECTED
    session.add(merchant)
    session.commit()

    assert _check_merchant(session, merchant.id, "accounts") == 0

    assert "not_connected" in capsys.readouterr().out
    assert zernio_http[0].headers["Authorization"] == f"Bearer {ZERNIO_TEST_KEY}"


def test_zernio_check_merchant_senza_chiave_esce_con_errore_chiaro(zernio_http, merchant, session, capsys):
    assert _check_merchant(session, merchant.id, "accounts") == 1

    captured = capsys.readouterr()
    assert zernio_http == []
    assert "not_connected" in captured.out  # lo stato si mostra comunque
    assert "chiave Zernio" in captured.err and "non" in captured.err


def test_zernio_check_merchant_inesistente(zernio_http, session, capsys):
    assert _check_merchant(session, 999, "accounts") == 1

    assert zernio_http == []
    assert "999" in capsys.readouterr().err


def test_zernio_check_merchant_non_modifica_il_db(zernio_http, instagram_merchant, session):
    before = (instagram_merchant.instagram_status, _count(session, ZernioSendCounter), _count(session, Card))

    _check_merchant(session, instagram_merchant.id, "accounts")

    session.refresh(instagram_merchant)
    assert before == (instagram_merchant.instagram_status, _count(session, ZernioSendCounter), _count(session, Card))


# --- replay_webhook ---

class _FakeServer:
    """Server finto per `replay_webhook`: registra le richieste; `outcome` (se dato) scrive la riga dell'evento."""

    def __init__(self, session=None, merchant_id=None, outcome=None, status=200):
        self.requests = []
        self.session, self.merchant_id, self.outcome, self.status = session, merchant_id, outcome, status
        self.client = httpx.Client(transport=httpx.MockTransport(self._handle))

    def _handle(self, request):
        self.requests.append(request)
        if self.outcome:
            self.session.add(ProcessedWebhookEvent(
                event_id=request.headers["X-Zernio-Event-Id"], merchant_id=self.merchant_id,
                received_at=utc_now(), outcome=self.outcome,
            ))
            self.session.commit()
        return httpx.Response(self.status, json={"status": "ok"})

    def event_message(self):
        """Evento `message.received` ricevuto, riletto con il core dopo aver verificato la firma."""
        request = self.requests[0]
        raw = request.read()
        assert instagram_service.verify_signature(WEBHOOK_TEST_SECRET, raw, request.headers["X-Zernio-Signature"])
        return instagram_service.parse_message_received(json.loads(raw), request.headers["X-Zernio-Event-Id"])


def _replay(session, merchant, server, *extra):
    argv = ["--merchant-id", str(merchant.id), "--conversation-id", "conv-9", *extra]
    return replay_webhook.main(argv, session=session, http=server.client)


def test_replay_webhook_invia_un_corpo_firmato_che_il_core_verifica(session, instagram_merchant):
    server = _FakeServer()

    assert _replay(session, instagram_merchant, server, "--text", "CARTA") == 0

    assert len(server.requests) == 1
    request = server.requests[0]
    assert request.method == "POST"
    assert request.url.path == f"/webhooks/zernio/{instagram_merchant.webhook_hook_id}"
    assert request.headers["X-Zernio-Event-Id"]
    msg = server.event_message()
    assert (msg.source, msg.text, msg.conversation_id) == ("dm_text", "CARTA", "conv-9")
    assert msg.account_id == instagram_merchant.zernio_account_id
    assert msg.direction == "incoming"
    assert msg.standby is False and msg.is_follower is None
    assert abs(msg.sent_at - utc_now()) < timedelta(minutes=1)
    assert instagram_service.detect_trigger(msg, settings.INSTAGRAM_CARD_KEYWORD) is not None


def test_replay_webhook_ogni_esecuzione_ha_un_event_id_nuovo(session, instagram_merchant):
    first, second = _FakeServer(), _FakeServer()
    _replay(session, instagram_merchant, first)
    _replay(session, instagram_merchant, second)
    assert first.requests[0].headers["X-Zernio-Event-Id"] != second.requests[0].headers["X-Zernio-Event-Id"]


def test_replay_webhook_testo_di_default_e_la_parola_chiave(session, instagram_merchant):
    server = _FakeServer()
    _replay(session, instagram_merchant, server)
    assert server.event_message().text == settings.INSTAGRAM_CARD_KEYWORD


def test_replay_webhook_postback(session, instagram_merchant):
    server = _FakeServer()
    _replay(session, instagram_merchant, server, "--postback")
    msg = server.event_message()
    assert msg.source == "dm_postback"
    assert msg.postback_payload == instagram_service.CARD_POSTBACK_PAYLOAD


def test_replay_webhook_standby_sender_ore_e_follower(session, instagram_merchant):
    server = _FakeServer()
    _replay(session, instagram_merchant, server, "--standby", "--sender-id", "igsid-finto-5", "--hours-ago", "5",
            "--follower", "no")
    msg = server.event_message()
    assert msg.standby is True
    assert msg.sender_id == "igsid-finto-5"
    assert msg.is_follower is False
    assert abs((utc_now() - msg.sent_at) - timedelta(hours=5)) < timedelta(minutes=1)


def test_replay_webhook_follower_si(session, instagram_merchant):
    server = _FakeServer()
    _replay(session, instagram_merchant, server, "--follower", "si")
    assert server.event_message().is_follower is True


def test_replay_webhook_stampa_status_ed_esito_e_avvisa_dell_invio_vero(session, instagram_merchant, capsys):
    server = _FakeServer(session, instagram_merchant.id, outcome=WebhookOutcome.SENT)

    assert _replay(session, instagram_merchant, server) == 0

    out = capsys.readouterr().out
    assert "VERO" in out
    assert "200" in out
    assert "sent" in out


def test_replay_webhook_non_stampa_ne_segreti_ne_conversazione(session, instagram_merchant, capsys):
    server = _FakeServer(session, instagram_merchant.id, outcome=WebhookOutcome.SENT)
    _replay(session, instagram_merchant, server)

    captured = capsys.readouterr()
    shown = captured.out + captured.err
    for secret in (WEBHOOK_TEST_SECRET, ZERNIO_TEST_KEY, "conv-9", "igsid-finto", instagram_merchant.webhook_hook_id):
        assert secret not in shown


def test_replay_webhook_senza_riga_dell_evento_lo_dice(session, instagram_merchant, capsys):
    server = _FakeServer()
    assert _replay(session, instagram_merchant, server) == 0
    assert "non trovato" in capsys.readouterr().out


def test_replay_webhook_risposta_non_2xx_esce_con_errore(session, instagram_merchant, capsys):
    server = _FakeServer(status=401)
    assert _replay(session, instagram_merchant, server) == 1
    assert "401" in capsys.readouterr().out


def test_replay_webhook_server_non_raggiungibile(session, instagram_merchant, capsys):
    def refuse(request):
        raise httpx.ConnectError("rifiutata")

    http = httpx.Client(transport=httpx.MockTransport(refuse))
    code = replay_webhook.main(
        ["--merchant-id", str(instagram_merchant.id), "--conversation-id", "c"], session=session, http=http,
    )
    assert code == 1
    assert "ERRORE" in capsys.readouterr().err


def test_replay_webhook_merchant_inesistente(session, capsys):
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    code = replay_webhook.main(["--merchant-id", "999", "--conversation-id", "c"], session=session, http=http)
    assert code == 1
    assert "ERRORE" in capsys.readouterr().err


def test_replay_webhook_merchant_senza_webhook(session, merchant, capsys):
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    code = replay_webhook.main(
        ["--merchant-id", str(merchant.id), "--conversation-id", "c"], session=session, http=http,
    )
    assert code == 1
    assert "ERRORE" in capsys.readouterr().err


def test_replay_webhook_text_e_postback_si_escludono(session):
    with pytest.raises(SystemExit):
        replay_webhook.main(
            ["--merchant-id", "1", "--conversation-id", "c", "--text", "x", "--postback"], session=session,
        )


def test_replay_webhook_help_non_richiede_il_db(capsys):
    with pytest.raises(SystemExit) as exit_info:
        replay_webhook.main(["--help"])
    assert exit_info.value.code == 0
    assert "--conversation-id" in capsys.readouterr().out


def test_replay_webhook_contro_l_app_vera_crea_la_carta(client, session, instagram_merchant, zernio_mock):
    """Giro completo: il corpo firmato dallo script è accettato dal vero webhook."""

    def forward(request):
        response = client.post(
            request.url.path, content=request.read(),
            headers={k: v for k, v in request.headers.items() if k.lower().startswith("x-zernio")},
        )
        return httpx.Response(response.status_code, json=response.json())

    http = httpx.Client(transport=httpx.MockTransport(forward))
    code = replay_webhook.main(
        ["--merchant-id", str(instagram_merchant.id), "--conversation-id", "conv-9"], session=session, http=http,
    )

    assert code == 0
    assert _count(session, Card) == 1
    assert len(zernio_mock.requests) == 1
