"""
Test di Ecologi di piattaforma (httpx mockato) e della chiusura del periodo
(SQLite in-memory, Ecologi mockato): piano, idempotenza, divergenze, cap e script.
"""

import asyncio
from datetime import datetime, timezone

import httpx
import pytest
from sqlmodel import select

from app.core.config import settings
from app.core.enums import Level
from app.models.models import MerchantPool, PointTransaction, TreePlanting
from app.services import card_service, ecologi_service, tree_service
from app.services.ecologi_service import EcologiError
from scripts import close_period as script

PERIOD = "2026-10"
NOW = datetime(2026, 11, 1, 0, 10, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _platform_key(monkeypatch):
    """Chiave di piattaforma presente e test mode spento (default dei test di chiusura)."""
    monkeypatch.setattr(settings, "ECOLOGI_API_KEY", "platform-key")
    monkeypatch.setattr(settings, "ECOLOGI_BASE_URL", "https://eco.real")
    monkeypatch.setattr(settings, "ECOLOGI_TEST_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ECOLOGI_TEST_MODE", False)


def _close(session, *, cap=20, confirm=lambda plan: False, period=PERIOD):
    return asyncio.run(tree_service.close_period(
        session, period, global_cap=cap, confirm=confirm, now=NOW,
    ))


def _plantings(session):
    return session.exec(select(TreePlanting).order_by(TreePlanting.merchant_id)).all()


# --- ecologi_service (httpx mockato) ---

def _patch_http(monkeypatch, handler):
    """Fa usare a ecologi_service un client httpx con transport finto; ritorna le richieste viste."""
    seen = []

    def wrapped(request):
        seen.append(request)
        return handler(request)

    real = httpx.AsyncClient
    monkeypatch.setattr(
        ecologi_service.httpx, "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(wrapped), **kw),
    )
    return seen


def test_purchase_trees_invia_chiave_payload_e_idempotency(monkeypatch):
    seen = _patch_http(monkeypatch, lambda r: httpx.Response(201, json={"treeUrl": "x1"}))
    result = asyncio.run(ecologi_service.purchase_trees(5, idempotency_key="chiave-1"))
    req = seen[0]
    assert result == {"treeUrl": "x1"}
    assert str(req.url) == "https://eco.real/impact/trees"
    assert req.headers["Authorization"] == "Bearer platform-key"
    assert req.headers["Idempotency-Key"] == "chiave-1"
    assert req.read() == b'{"number":5}'


def test_purchase_trees_test_mode_usa_chiave_di_test_e_stesso_url(monkeypatch):
    monkeypatch.setattr(settings, "ECOLOGI_TEST_MODE", True)
    seen = _patch_http(monkeypatch, lambda r: httpx.Response(200, json={}))
    asyncio.run(ecologi_service.purchase_trees(2))
    assert str(seen[0].url) == "https://eco.real/impact/trees"
    assert seen[0].headers["Authorization"] == "Bearer test-key"
    assert b'"test":true' in seen[0].read()
    assert len(seen[0].headers["Idempotency-Key"]) == 36  # uuid casuale


def test_purchase_trees_modalita_reale_senza_flag_test(monkeypatch):
    seen = _patch_http(monkeypatch, lambda r: httpx.Response(201, json={}))
    asyncio.run(ecologi_service.purchase_trees(2, name="Bar Demo · ottobre 2026"))
    assert seen[0].headers["Authorization"] == "Bearer platform-key"
    assert b"test" not in seen[0].read()


def test_purchase_trees_force_test_con_chiave_reale(monkeypatch):
    seen = _patch_http(monkeypatch, lambda r: httpx.Response(201, json={}))
    asyncio.run(ecologi_service.purchase_trees(1, force_test=True))
    assert seen[0].headers["Authorization"] == "Bearer platform-key"
    assert b'"test":true' in seen[0].read()


def test_purchase_trees_chiave_vuota(monkeypatch):
    monkeypatch.setattr(settings, "ECOLOGI_API_KEY", "")
    with pytest.raises(EcologiError, match="Chiave Ecologi di piattaforma non configurata"):
        asyncio.run(ecologi_service.purchase_trees(1))


def test_purchase_trees_test_mode_senza_chiave_di_test_nessun_fallback(monkeypatch):
    monkeypatch.setattr(settings, "ECOLOGI_TEST_MODE", True)
    monkeypatch.setattr(settings, "ECOLOGI_TEST_API_KEY", "")  # la chiave reale resta valorizzata
    with pytest.raises(EcologiError, match="Chiave Ecologi di test non configurata"):
        asyncio.run(ecologi_service.purchase_trees(1))


def test_purchase_trees_modalita_reale_senza_chiave_reale_nessun_fallback(monkeypatch):
    monkeypatch.setattr(settings, "ECOLOGI_API_KEY", "")  # la chiave di test resta valorizzata
    with pytest.raises(EcologiError, match="Chiave Ecologi di piattaforma non configurata"):
        asyncio.run(ecologi_service.purchase_trees(1))


def test_purchase_trees_http_500(monkeypatch):
    _patch_http(monkeypatch, lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(EcologiError):
        asyncio.run(ecologi_service.purchase_trees(1))


def test_purchase_trees_errore_di_rete(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("giù")

    _patch_http(monkeypatch, handler)
    with pytest.raises(EcologiError):
        asyncio.run(ecologi_service.purchase_trees(1))


def test_extract_ref():
    assert ecologi_service.extract_ref(
        {"treeUrl": "https://ecologi.com/x?tree=1", "amount": 1.8}
    ) == "https://ecologi.com/x?tree=1"
    assert ecologi_service.extract_ref({"id": 7}) is None  # l'id non è documentato
    assert ecologi_service.extract_ref({"number": 1}) is None


# --- close_period ---

def test_chiusura_pianta_per_livello(session, approved_merchants, mock_ecologi):
    ms = approved_merchants({"A": 700, "B": 350, "C": 40})
    report = _close(session)

    assert [c["number"] for c in mock_ecologi] == [5, 3]
    assert len(mock_ecologi) == 2  # C è sotto il bronzo: nessuna chiamata
    assert [c["name"] for c in mock_ecologi] == ["A · ottobre 2026", "B · ottobre 2026"]
    assert [c["idempotency_key"] for c in mock_ecologi] == [
        f"fidelitree-{ms[0].id}-{PERIOD}", f"fidelitree-{ms[1].id}-{PERIOD}",
    ]
    rows = _plantings(session)
    assert [(r.merchant_id, r.period, r.level, r.tree_count, r.pool_points, r.ecologi_ref, r.test)
            for r in rows] == [
        (ms[0].id, PERIOD, Level.GOLD, 5, 700, "https://ecologi.test/tree-1", False),
        (ms[1].id, PERIOD, Level.SILVER, 3, 350, "https://ecologi.test/tree-2", False),
    ]
    assert [e.status for e in report.entries] == ["planted", "planted", "skipped"]


def test_chiusura_bronzo_argento_oro(session, approved_merchants, mock_ecologi):
    ms = approved_merchants({"A": 700, "B": 350, "C": 150})
    _close(session)
    assert [c["number"] for c in mock_ecologi] == [5, 3, 1]
    assert len(_plantings(session)) == 3
    assert ms[2].id in {r.merchant_id for r in _plantings(session)}


def test_idempotency_key_in_test_mode(session, approved_merchants, mock_ecologi, monkeypatch):
    monkeypatch.setattr(settings, "ECOLOGI_TEST_MODE", True)
    ms = approved_merchants({"A": 150})
    _close(session)
    assert mock_ecologi[0]["idempotency_key"] == f"fidelitree-test-{ms[0].id}-{PERIOD}"
    assert _plantings(session)[0].test is True


def test_merchant_non_approvato_escluso(session, approved_merchants, mock_ecologi):
    ms = approved_merchants({"A": 900})
    ms[0].is_approved = False
    session.add(ms[0])
    session.commit()
    _close(session)
    assert mock_ecologi == []
    assert _plantings(session) == []


def test_sotto_il_bronzo_nessuna_chiamata(session, approved_merchants, mock_ecologi):
    approved_merchants({"A": 40})
    _close(session)
    assert mock_ecologi == []
    assert _plantings(session) == []


def test_idempotenza_seconda_esecuzione(session, approved_merchants, mock_ecologi):
    approved_merchants({"A": 700, "B": 350})
    _close(session)
    report = _close(session)
    assert len(mock_ecologi) == 2
    assert len(_plantings(session)) == 2
    assert [e.status for e in report.entries] == ["skipped", "skipped"]


def test_prova_non_blocca_la_chiusura_vera(session, approved_merchants, mock_ecologi, monkeypatch):
    approved_merchants({"A": 700})
    monkeypatch.setattr(settings, "ECOLOGI_TEST_MODE", True)
    _close(session)
    monkeypatch.setattr(settings, "ECOLOGI_TEST_MODE", False)
    _close(session)
    assert sorted(r.test for r in _plantings(session)) == [False, True]
    assert len(mock_ecologi) == 2
    _close(session)  # seconda chiusura vera: skipped
    assert len(mock_ecologi) == 2


def test_divergenza_contatore_registro_blocca_tutto(session, approved_merchants, mock_ecologi):
    ms = approved_merchants({"A": 700, "B": 350})
    assert tree_service.pool_mismatches(session, PERIOD) == []
    pool = session.get(MerchantPool, (ms[0].id, PERIOD))
    pool.points = 900
    session.add(pool)
    session.commit()

    report = _close(session)
    assert mock_ecologi == []
    assert _plantings(session) == []
    assert report.blocked_by == "mismatch"
    assert [(m.merchant_id, m.counter, m.ledger) for m in report.mismatches] == [(ms[0].id, 900, 700)]


def test_snapshot_pool_points(session, approved_merchants, mock_ecologi):
    ms = approved_merchants({"A": 700})
    _close(session)
    pool = session.get(MerchantPool, (ms[0].id, PERIOD))
    pool.points = 5  # correzione tardiva
    session.add(pool)
    session.commit()
    assert _plantings(session)[0].pool_points == 700


def test_errore_ecologi_su_un_negozio_non_blocca_gli_altri(session, approved_merchants, monkeypatch):
    ms = approved_merchants({"A": 700, "B": 350, "C": 150})
    calls = []
    fail = {"on": True}

    async def fake(number, name=None, idempotency_key=None, *, force_test=False):
        calls.append(idempotency_key)
        if fail["on"] and idempotency_key.startswith(f"fidelitree-{ms[1].id}-"):
            raise EcologiError("rifiutato")
        return {"treeUrl": "https://ecologi.test/ok"}

    monkeypatch.setattr(ecologi_service, "purchase_trees", fake)
    report = _close(session)
    assert [e.status for e in report.entries] == ["planted", "failed", "planted"]
    assert {r.merchant_id for r in _plantings(session)} == {ms[0].id, ms[2].id}

    fail["on"] = False
    calls.clear()
    _close(session)
    assert calls == [f"fidelitree-{ms[1].id}-{PERIOD}"]
    assert len(_plantings(session)) == 3


def test_override_soglie_del_merchant(session, approved_merchants, mock_ecologi):
    ms = approved_merchants({"A": 60})
    ms[0].bronze_threshold = 50
    session.add(ms[0])
    session.commit()
    _close(session)
    assert [c["number"] for c in mock_ecologi] == [1]


def test_pool_solo_del_mese_richiesto(session, approved_merchants, mock_ecologi, merchant):
    ms = approved_merchants({"A": 700})
    # scan del 1° del mese dopo + riga di un altro periodo: non entrano nel mese chiuso
    from app.models.models import Card
    card = session.exec(select(Card).where(Card.merchant_id == ms[0].id)).first()
    card_service.add_tree_points(session, ms[0], card.id, 100, now=datetime(2026, 11, 1, 0, 5, tzinfo=timezone.utc))
    assert tree_service.pool_points(session, ms[0].id, PERIOD) == 700
    assert tree_service.pool_points(session, ms[0].id, "2026-11") == 100
    _close(session)
    assert _plantings(session)[0].pool_points == 700


def test_conversione_non_riduce_il_pool(session, approved_merchants, mock_ecologi):
    approved_merchants({"A": 700}, conversion_enabled=True)  # 700 punti → conversioni, pool intatto
    _close(session)
    assert [c["number"] for c in mock_ecologi] == [5]


def test_cap_sforato_senza_conferma_non_pianta(session, approved_merchants, mock_ecologi):
    approved_merchants({f"N{i}": 700 for i in range(4)} | {"X": 350})  # 5*4 + 3 = 23 → con cap 20 sfora
    report = _close(session, cap=20)
    assert mock_ecologi == []
    assert report.blocked_by == "cap"
    assert report.plan.exceeds_cap and report.plan.excess == 3


def test_cap_alzato_pianta_tutto(session, approved_merchants, mock_ecologi):
    approved_merchants({f"N{i}": 700 for i in range(4)} | {"X": 350, "Y": 150})  # 24
    report = _close(session, cap=24)
    assert report.blocked_by is None
    assert sum(c["number"] for c in mock_ecologi) == 24


def test_cap_sforato_con_conferma_pianta(session, approved_merchants, mock_ecologi):
    approved_merchants({"A": 700, "B": 700})
    _close(session, cap=5, confirm=lambda plan: True)
    assert len(mock_ecologi) == 2


# --- script ---

def test_script_yes_con_cap_sforato_senza_cap_esce_con_errore(session, approved_merchants, mock_ecologi):
    approved_merchants({"A": 700, "B": 700, "C": 700, "D": 700, "E": 350})  # 23 > 20
    code = script.main(["--month", PERIOD, "--yes"], session=session, now=NOW)
    assert code != 0
    assert mock_ecologi == []


def test_script_con_cap_pianta(session, approved_merchants, mock_ecologi):
    approved_merchants({"A": 700, "B": 700, "C": 700, "D": 700, "E": 350})
    code = script.main(["--month", PERIOD, "--cap", "23", "--yes"], session=session, now=NOW)
    assert code == 0
    assert sum(c["number"] for c in mock_ecologi) == 23


def test_script_divergenza_esce_con_errore_anche_con_yes(session, approved_merchants, mock_ecologi):
    ms = approved_merchants({"A": 700})
    pool = session.get(MerchantPool, (ms[0].id, PERIOD))
    pool.points = 1
    session.add(pool)
    session.commit()
    assert script.main(["--month", PERIOD, "--yes"], session=session, now=NOW) == 1
    assert mock_ecologi == []


def test_script_mese_di_default_e_il_precedente(session, approved_merchants, mock_ecologi):
    approved_merchants({"A": 700})
    assert script.main(["--yes"], session=session, now=NOW) == 0  # 2026-11-01 00:10 UTC → 2026-10
    assert _plantings(session)[0].period == "2026-10"


def test_script_conferma_interattiva_negata(session, approved_merchants, mock_ecologi):
    approved_merchants({"A": 700})
    code = script.main(["--month", PERIOD], session=session, now=NOW, input_fn=lambda _: "n")
    assert code == 2
    assert mock_ecologi == []


def test_script_help_funziona():
    with pytest.raises(SystemExit) as exc:
        script.main(["--help"])
    assert exc.value.code == 0
