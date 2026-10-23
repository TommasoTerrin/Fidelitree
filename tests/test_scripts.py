"""
Test degli script di supporto: seed del DB, smoke test, reset del DB.
Tutto su SQLite in-memory (fixture `session`/`client`), senza rete e senza Ecologi.
"""

import json
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.config import settings
from app.core.enums import Level
from app.models.models import Card, Customer, Merchant, MerchantPool, PointTransaction
from app.services import ecologi_service, instagram_service, tree_service, zernio_service
from app.services.db_crud import customer_crud
from scripts import ecologi_check, reset_db, seed_db, zernio_check
from scripts.smoke_test_prod import run_smoke_test

NOW = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
PERIOD = "2026-10"


def _count(session, model) -> int:
    return len(session.exec(select(model)).all())


# --- seed ---

def test_seed_crea_merchant_clienti_carte_e_movimenti(session):
    entries = seed_db.seed(session, now=NOW)

    assert len(entries) == 2
    merchants = session.exec(select(Merchant)).all()
    assert len(merchants) == 2
    assert all(m.is_approved and m.auth_user_id for m in merchants)
    assert _count(session, Customer) == 2
    assert _count(session, Card) == 4  # ogni cliente ha una carta presso ciascun negozio
    assert _count(session, PointTransaction) > 0
    # un merchant con conversione e uno "solo alberi", con soglie diverse
    assert {m.conversion_enabled for m in merchants} == {True, False}
    assert len({(m.bronze_threshold, m.gold_threshold) for m in merchants}) == 2


def test_seed_converte_in_cashback_nel_negozio_con_conversione(session):
    entries = seed_db.seed(session, now=NOW)
    bar = next(e for e in entries if e.merchant.conversion_enabled)
    anna = session.get(Card, bar.cards["anna@fidelitree.it"].id)
    assert anna.cashback_cents == 200 and anna.tree_points == 10  # 60 punti: 50 → 2 €, restano 10


def test_seed_e_idempotente(session):
    seed_db.seed(session, now=NOW)
    snapshot = (
        _count(session, Merchant), _count(session, Customer), _count(session, Card),
        _count(session, PointTransaction), [p.points for p in session.exec(select(MerchantPool)).all()],
    )

    seed_db.seed(session, now=NOW)

    assert snapshot == (
        _count(session, Merchant), _count(session, Customer), _count(session, Card),
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


def test_main_del_seed_stampa_link_e_credenziali(monkeypatch, capsys):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(seed_db, "engine", engine)

    seed_db.main()  # stampa a sessione aperta: fuori da essa i modelli sarebbero scollegati

    out = capsys.readouterr().out
    assert "/join/1" in out and "/join/2" in out
    assert "/wallet" in out and settings.DEV_AUTH_PASSWORD in out
    assert "demo@fidelitree.it" in out and "anna@fidelitree.it" in out
    engine.dispose()


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


# --- reset_db ---

def test_reset_db_ricrea_lo_schema_vuoto(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        customer_crud.create_customer(s, "x@y.it")
    monkeypatch.setattr(reset_db, "engine", engine)

    reset_db.reset_db()

    tables = set(inspect(engine).get_table_names())
    assert {"merchant", "customer", "card", "pointtransaction", "merchantpool", "treeplanting"} <= tables
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM customer").scalar() == 0
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
