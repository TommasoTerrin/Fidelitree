"""
Test del core puro dell'onboarding Instagram (`merchant_service`): chiave Zernio, URL del webhook, menu
persistente e pannello. Nessun DB, nessuna rete, nessun orologio: il tempo arriva come argomento.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.enums import InstagramStatus
from app.core.errors import InvalidInputError
from app.services.instagram_service import CARD_POSTBACK_PAYLOAD
from app.services.merchant_service import (
    InstagramPanelInput, MenuState, classify_persistent_menu, instagram_panel, validate_zernio_key,
    webhook_url_for,
)

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
KEY = "sk_" + "ab12" * 16


def _panel(counter_sent=0, now=NOW, **fields):
    """Pannello con i limiti di piattaforma di default (10.000 invii, avviso al 75%)."""
    data = {"status": InstagramStatus.ACTIVE, "account_connected": True, "persistent_menu_set": True}
    data.update(fields)
    return instagram_panel(
        InstagramPanelInput(**data), counter_sent, now, keyword="CARTA", send_limit=10000, warn_percent=75,
    )


def _codes(panel):
    return [w.code for w in panel.warnings]


# --- chiave Zernio ---

@pytest.mark.parametrize("raw,expected", [
    (KEY, KEY),
    (f"  {KEY}\n", KEY),
    ("zrk_abc123", "zrk_abc123"),
])
def test_chiave_valida(raw, expected):
    assert validate_zernio_key(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "abc123", "sk_", "zrk_", "pk_" + "a" * 20, "sk_ab cd", "SK_abcd"])
def test_chiave_non_valida_e_mai_riportata_nel_messaggio(raw):
    with pytest.raises(InvalidInputError) as e:
        validate_zernio_key(raw)
    # il messaggio nomina i prefissi accettati: i valori di soli 4 caratteri o meno (i prefissi nudi) non contano
    assert len((raw or "").strip()) <= 4 or raw.strip() not in str(e.value)


# --- URL del webhook ---

def test_webhook_url_con_https():
    assert webhook_url_for("https://fidelitree.example", "hook1") == "https://fidelitree.example/webhooks/zernio/hook1"
    assert webhook_url_for("https://fidelitree.example/", "h") == "https://fidelitree.example/webhooks/zernio/h"


@pytest.mark.parametrize("base", ["http://127.0.0.1:8001", "", "fidelitree.example"])
def test_webhook_url_richiede_https(base):
    with pytest.raises(InvalidInputError, match="https"):
        webhook_url_for(base, "hook1")


# --- menu persistente ---

def _menu(*actions):
    return [{"persistent_menu": [{"locale": "default", "call_to_actions": list(actions)}]}]


@pytest.mark.parametrize("data", [[], None, [{}], _menu(), [{"persistent_menu": []}]])
def test_menu_vuoto(data):
    assert classify_persistent_menu(data) == MenuState.EMPTY


def test_menu_con_la_nostra_voce():
    ours = {"type": "postback", "title": "🌳 La mia carta", "payload": CARD_POSTBACK_PAYLOAD}
    other = {"type": "postback", "title": "Ordina", "payload": "ORDINA"}
    assert classify_persistent_menu(_menu(ours)) == MenuState.OURS
    assert classify_persistent_menu(_menu(other, ours)) == MenuState.OURS


def test_menu_di_altri():
    other = {"type": "web_url", "title": "Sito", "url": "https://bar.example"}
    assert classify_persistent_menu(_menu(other)) == MenuState.OTHER
    # voce annidata: conta lo stesso
    nested = {"type": "nested", "title": "Altro", "call_to_actions": [{"type": "postback", "payload": "X"}]}
    assert classify_persistent_menu(_menu(nested)) == MenuState.OTHER


# --- pannello ---

def test_pannello_attivo_senza_avvisi():
    panel = _panel(username="bar_demo", key_masked="…ef56", key_saved=True)
    assert panel.status == InstagramStatus.ACTIVE
    assert panel.username == "bar_demo"
    assert panel.key_masked == "…ef56"
    assert panel.keyword == "CARTA"
    assert panel.warnings == []


def test_pannello_senza_collegamento():
    panel = _panel(status=InstagramStatus.NOT_CONNECTED, account_connected=False, persistent_menu_set=False)
    assert panel.status == InstagramStatus.NOT_CONNECTED
    assert panel.quota is None and panel.warnings == [] and panel.key_saved is False


def test_pannello_chiave_salvata_e_account_da_scegliere():
    panel = _panel(
        status=InstagramStatus.NOT_CONNECTED, account_connected=False, persistent_menu_set=False,
        key_saved=True, key_masked="…ef56",
    )
    assert panel.key_saved is True and panel.key_masked == "…ef56"


def test_avviso_standby_entro_7_giorni_e_non_oltre():
    assert "standby" in _codes(_panel(standby_detected_at=NOW - timedelta(days=6, hours=23)))
    assert "standby" in _codes(_panel(standby_detected_at=NOW - timedelta(days=7)))
    assert "standby" not in _codes(_panel(standby_detected_at=NOW - timedelta(days=7, seconds=1)))
    assert "standby" not in _codes(_panel(standby_detected_at=None))


def test_standby_letto_da_sqlite_senza_fuso_vale_utc():
    naive = (NOW - timedelta(days=1)).replace(tzinfo=None)  # SQLite restituisce i datetime senza fuso
    assert "standby" in _codes(_panel(standby_detected_at=naive))
    too_old = (NOW - timedelta(days=30)).replace(tzinfo=None)
    assert "standby" not in _codes(_panel(standby_detected_at=too_old))


def test_avviso_quota_dal_75_per_cento():
    assert "quota" not in _codes(_panel(counter_sent=7499))
    panel = _panel(counter_sent=7500)
    assert "quota" in _codes(panel)
    assert panel.quota.sent == 7500 and panel.quota.limit == 10000 and panel.quota.percent == 75


def test_quota_esaurita_ha_un_messaggio_distinto():
    warned = next(w for w in _panel(counter_sent=8000).warnings if w.code == "quota")
    exhausted = next(w for w in _panel(counter_sent=10000).warnings if w.code == "quota")
    assert warned.message != exhausted.message
    assert _panel(counter_sent=10000).quota.exhausted is True


def test_avviso_menu_solo_con_account_collegato():
    assert "menu" in _codes(_panel(account_connected=True, persistent_menu_set=False))
    assert "menu" not in _codes(_panel(account_connected=True, persistent_menu_set=True))
    no_account = _panel(
        status=InstagramStatus.NOT_CONNECTED, account_connected=False, persistent_menu_set=False,
    )
    assert "menu" not in _codes(no_account)


def test_avviso_chiave_non_valida():
    panel = _panel(status=InstagramStatus.KEY_INVALID, key_masked="…ef56", key_saved=True)
    assert "key_invalid" in _codes(panel)
    assert "key_invalid" not in _codes(_panel())


def test_il_nome_della_parola_chiave_arriva_dal_chiamante():
    panel = instagram_panel(
        InstagramPanelInput(status=InstagramStatus.AWAITING_TEST_DM, account_connected=True, persistent_menu_set=True),
        0, NOW, keyword="TESSERA", send_limit=100, warn_percent=50,
    )
    assert panel.keyword == "TESSERA"


def test_quota_con_limite_non_configurato_non_avvisa():
    panel = instagram_panel(
        InstagramPanelInput(status=InstagramStatus.ACTIVE, account_connected=True, persistent_menu_set=True),
        50, NOW, keyword="CARTA", send_limit=0, warn_percent=75,
    )
    assert "quota" not in _codes(panel)
