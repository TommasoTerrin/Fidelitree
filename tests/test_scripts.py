"""
Test degli script di supporto: seed del DB, smoke test, reset del DB.
Tutto su SQLite in-memory (fixture `session`/`client`), senza rete e senza Ecologi.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.config import settings
from app.core.enums import Level
from app.models.models import Card, Customer, Merchant, MerchantPool, PointTransaction
from app.services import tree_service
from app.services.db_crud import customer_crud
from scripts import reset_db, seed_db
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
