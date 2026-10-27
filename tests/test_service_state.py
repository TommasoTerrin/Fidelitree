"""
Stato del servizio del merchant (ticket 12): in attesa / attivo / in pausa.

Scanner e cashback (solo togliere se non attivo), webhook (carta di prova ai clienti nuovi di un negozio in
attesa), pagine (carta di prova, `/c/<token>` identica in ogni stato, banner e pulsanti del merchant) e
chiusura mensile invariata. SQLite in-memory, Zernio e Ecologi mockati.
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select

from app.core import crypto
from app.core.clock import utc_now
from app.core.enums import InstagramStatus, PointTransactionKind, WebhookOutcome
from app.models.models import Card, MerchantPool, PointTransaction
from app.services import card_service, instagram_service, tree_service
from app.services.db_crud import merchant_crud
from tests.conftest import TEST_PUBLIC_BASE_URL, WEBHOOK_TEST_SECRET, ZERNIO_TEST_KEY, make_card, signed_webhook
from tests.test_webhook import IGSID, MESSAGE_TEXT, _cards, _counters, _event, _link_of, _not_follower, _payload

NOW = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
DEMO_URL = f"{TEST_PUBLIC_BASE_URL}/carta-di-prova"
PENDING = {"is_approved": False}
PAUSED = {"is_approved": True, "is_paused": True}
NOT_ACTIVE = [pytest.param(PENDING, id="in_attesa"), pytest.param(PAUSED, id="in_pausa")]


def _set_state(session, merchant, state):
    """Porta il merchant nello stato indicato (flag di `PENDING`/`PAUSED`, o `ACTIVE` con entrambi azzerati)."""
    return merchant_crud.update_merchant(session, merchant, state)


def _movements(session):
    return session.exec(select(PointTransaction).order_by(PointTransaction.id)).all()


# --- scanner e cashback ---------------------------------------------------------------------------------

@pytest.mark.parametrize("state", NOT_ACTIVE)
def test_aggiungere_tree_points_se_non_attivo_da_403_senza_scrivere(auth_client, session, merchant, card, state):
    _set_state(session, merchant, state)

    resp = auth_client.post(f"/api/merchant/add-tree-points/{card.id}", json={"tree_points": 10})

    assert resp.status_code == 403
    assert resp.json()["detail"] in (
        "In attesa di approvazione: non puoi aggiungere punti",
        "Servizio in pausa: puoi solo togliere il saldo esistente",
    )
    session.refresh(card)
    assert card.tree_points == 0
    assert _movements(session) == []
    assert session.exec(select(MerchantPool)).all() == []


@pytest.mark.parametrize("state", NOT_ACTIVE)
def test_aggiungere_cashback_se_non_attivo_da_403_senza_scrivere(auth_client, session, merchant, card, state):
    _set_state(session, merchant, state)

    resp = auth_client.post(f"/api/merchant/add-point/{card.id}", json={"cb_points": 1.5})

    assert resp.status_code == 403
    session.refresh(card)
    assert card.cashback_cents == 0


def test_messaggi_403_distinguono_attesa_e_pausa(auth_client, session, merchant, card):
    _set_state(session, merchant, PENDING)
    assert auth_client.post(f"/api/merchant/add-point/{card.id}", json={"cb_points": 1}).json()["detail"] == (
        "In attesa di approvazione: non puoi aggiungere punti"
    )
    _set_state(session, merchant, PAUSED)
    assert auth_client.post(f"/api/merchant/add-point/{card.id}", json={"cb_points": 1}).json()["detail"] == (
        "Servizio in pausa: puoi solo togliere il saldo esistente"
    )


def test_un_importo_che_in_centesimi_e_zero_non_e_un_accredito(auth_client, session, merchant, card):
    """Il segno si guarda sui centesimi: 0,004 € arrotonda a 0 e non è un'aggiunta."""
    _set_state(session, merchant, PAUSED)
    resp = auth_client.post(f"/api/merchant/add-point/{card.id}", json={"cb_points": 0.004})
    assert resp.status_code == 200


@pytest.mark.parametrize("state", NOT_ACTIVE)
def test_togliere_funziona_in_ogni_stato_per_tree_points_e_cashback(auth_client, session, merchant, card, state):
    # saldo preso quando il negozio era attivo
    card_service.add_tree_points(session, merchant, card.id, 30, now=NOW)
    card_service.update_cashback(session, merchant, card.id, 3.0)
    _set_state(session, merchant, state)

    tree = auth_client.post(f"/api/merchant/add-tree-points/{card.id}", json={"tree_points": -12})
    cash = auth_client.post(f"/api/merchant/add-point/{card.id}", json={"cb_points": -1.25})

    assert tree.status_code == 200 and tree.json()["card"]["tree_points"] == 18
    assert cash.status_code == 200 and cash.json()["cashback_point"] == 1.75


@pytest.mark.parametrize("state", NOT_ACTIVE)
def test_togliere_in_pausa_scrive_registro_e_pool_senza_divergenze(session, merchant, card, state):
    card_service.add_tree_points(session, merchant, card.id, 30, now=NOW)
    _set_state(session, merchant, state)

    card_service.add_tree_points(session, merchant, card.id, -10, now=NOW)

    assert [(m.kind, m.delta) for m in _movements(session)] == [
        (PointTransactionKind.SCAN, 30), (PointTransactionKind.SCAN, -10),
    ]
    assert tree_service.pool_points(session, merchant.id, "2026-10") == 20
    assert tree_service.pool_mismatches(session, "2026-10") == []


@pytest.mark.parametrize("state", NOT_ACTIVE)
def test_delta_zero_resta_com_e(auth_client, session, merchant, card, state):
    _set_state(session, merchant, state)
    assert auth_client.post(f"/api/merchant/add-tree-points/{card.id}", json={"tree_points": 0}).status_code == 200
    assert auth_client.post(f"/api/merchant/add-point/{card.id}", json={"cb_points": 0}).status_code == 200


@pytest.mark.parametrize("state", NOT_ACTIVE)
def test_nessuna_conversione_se_non_attivo_nemmeno_togliendo(session, merchant, card, state):
    """
    Il merchant abbassa la soglia dalle impostazioni a 10 con la carta a 30 punti: togliere 1 punto, se non
    attivo, non deve convertire (sarebbe un accredito di cashback).
    """
    card_service.add_tree_points(session, merchant, card.id, 30, now=NOW)  # soglia 50: nessuna conversione
    merchant_crud.update_merchant(session, merchant, {"conversion_threshold": 10, **state})

    result = card_service.add_tree_points(session, merchant, card.id, -1, now=NOW)

    assert result.conversions == 0 and result.cashback_added_cents == 0
    assert result.card.tree_points == 29 and result.card.cashback_cents == 0
    assert all(m.kind is PointTransactionKind.SCAN for m in _movements(session))


def test_se_attivo_la_conversione_scatta_come_prima(session, merchant, card):
    merchant_crud.update_merchant(session, merchant, {"conversion_threshold": 10})
    result = card_service.add_tree_points(session, merchant, card.id, 25, now=NOW)
    assert result.conversions == 2 and result.card.tree_points == 5 and result.card.cashback_cents == 400


def test_approvazione_via_api_admin_riapre_lo_scanner(auth_client, session, merchant, card, admin_headers):
    """Esempio end-to-end: in attesa → 403, `POST /{id}/approve` dell'admin, poi l'aggiunta funziona."""
    _set_state(session, merchant, PENDING)
    url = f"/api/merchant/add-tree-points/{card.id}"
    assert auth_client.post(url, json={"tree_points": 10}).status_code == 403

    approve = auth_client.post(f"/api/merchant/{merchant.id}/approve", headers=admin_headers)
    assert approve.status_code == 200

    resp = auth_client.post(url, json={"tree_points": 10})
    assert resp.status_code == 200 and resp.json()["card"]["tree_points"] == 10


def test_riattivare_dalla_pausa_riapre_lo_scanner(auth_client, session, merchant, card):
    _set_state(session, merchant, PAUSED)
    url = f"/api/merchant/add-tree-points/{card.id}"
    assert auth_client.post(url, json={"tree_points": 10}).status_code == 403
    _set_state(session, merchant, {"is_paused": False})
    assert auth_client.post(url, json={"tree_points": 10}).status_code == 200


# --- webhook ----------------------------------------------------------------------------------------------

def _awaiting_test_dm(session, merchant, state=PENDING):
    return merchant_crud.update_merchant(session, merchant, {
        **state, "instagram_status": InstagramStatus.AWAITING_TEST_DM,
    })


def test_in_attesa_cliente_nuovo_riceve_la_carta_di_prova_senza_riga_card(
    client, session, instagram_merchant, zernio_mock,
):
    _awaiting_test_dm(session, instagram_merchant)

    response = signed_webhook(client, instagram_merchant, _payload())

    assert response.status_code == 200
    assert len(zernio_mock.requests) == 1
    body = zernio_mock.bodies()[0]
    element = body["template"]["elements"][0]
    assert element["title"] == "Bar Demo"
    assert _link_of(body) == DEMO_URL
    assert _cards(session) == []                                   # nessuna riga Card, quindi nessun indice cieco
    assert _event(session).outcome == WebhookOutcome.SENT
    assert [c.sent for c in _counters(session)] == [1]
    session.refresh(instagram_merchant)
    assert instagram_merchant.instagram_status == InstagramStatus.ACTIVE


def test_in_attesa_il_postback_del_menu_porta_alla_stessa_carta_di_prova(client, session, instagram_merchant, zernio_mock):
    _set_state(session, instagram_merchant, PENDING)

    signed_webhook(client, instagram_merchant, _payload(postback=instagram_service.CARD_POSTBACK_PAYLOAD))

    assert _link_of(zernio_mock.bodies()[0]) == DEMO_URL
    assert _cards(session) == []


def test_in_attesa_cliente_che_ha_gia_la_carta_riceve_il_link_vero(client, session, instagram_merchant, zernio_mock):
    existing, _ = instagram_service.get_or_create_card(session, instagram_merchant, IGSID)
    _set_state(session, instagram_merchant, PENDING)

    signed_webhook(client, instagram_merchant, _payload(conversation="conv-nuova"))

    token = crypto.card_link_token(existing.id, existing.link_version)
    assert _link_of(zernio_mock.bodies()[0]) == f"{TEST_PUBLIC_BASE_URL}/c/{token}"
    cards = _cards(session)
    assert len(cards) == 1 and cards[0].zernio_conversation_id == "conv-nuova"


def test_in_attesa_chi_non_segue_riceve_l_invito_come_prima(client, session, instagram_merchant, zernio_mock):
    _set_state(session, instagram_merchant, PENDING)

    signed_webhook(client, instagram_merchant, _payload(is_follower=False))

    assert "template" not in zernio_mock.bodies()[0]
    assert "segui" in zernio_mock.bodies()[0]["message"]
    assert _event(session).outcome == WebhookOutcome.FOLLOW_REQUESTED
    assert _cards(session) == []


def test_in_attesa_fuori_dalle_24_ore_nessun_invio_e_nessuna_carta(client, session, instagram_merchant, zernio_mock):
    _set_state(session, instagram_merchant, PENDING)

    signed_webhook(client, instagram_merchant, _payload(sent_at=utc_now() - timedelta(hours=25)))

    assert zernio_mock.requests == []
    assert _event(session).outcome == WebhookOutcome.OUT_OF_WINDOW
    assert _cards(session) == []


def test_in_attesa_se_meta_rifiuta_la_card_il_ripiego_porta_alla_carta_di_prova(
    client, session, instagram_merchant, zernio_mock,
):
    _set_state(session, instagram_merchant, PENDING)
    zernio_mock.queue(_not_follower())

    signed_webhook(client, instagram_merchant, _payload())

    assert len(zernio_mock.requests) == 2
    fallback = zernio_mock.bodies()[1]
    assert fallback["message"].endswith(DEMO_URL)
    assert "/c/" not in fallback["message"]
    assert _event(session).outcome == WebhookOutcome.FALLBACK_SENT
    assert _cards(session) == []


def test_dopo_l_approvazione_un_nuovo_carta_da_la_carta_vera(client, session, instagram_merchant, zernio_mock):
    _set_state(session, instagram_merchant, PENDING)
    signed_webhook(client, instagram_merchant, _payload("evt-1"))
    assert _cards(session) == []

    _set_state(session, instagram_merchant, {"is_approved": True})
    signed_webhook(client, instagram_merchant, _payload("evt-2"))

    [card] = _cards(session)
    token = crypto.card_link_token(card.id, card.link_version)
    assert _link_of(zernio_mock.bodies()[0]) == DEMO_URL
    assert _link_of(zernio_mock.bodies()[1]) == f"{TEST_PUBLIC_BASE_URL}/c/{token}"


def test_in_pausa_il_webhook_fa_come_oggi(client, session, instagram_merchant, zernio_mock):
    _set_state(session, instagram_merchant, PAUSED)

    signed_webhook(client, instagram_merchant, _payload())

    [card] = _cards(session)
    assert _link_of(zernio_mock.bodies()[0]) == f"{TEST_PUBLIC_BASE_URL}/c/{crypto.card_link_token(card.id, 1)}"
    assert _event(session).outcome == WebhookOutcome.SENT


def test_webhook_in_attesa_non_logga_segreti(client, session, instagram_merchant, zernio_mock, caplog):
    _set_state(session, instagram_merchant, PENDING)
    caplog.set_level(logging.DEBUG)

    signed_webhook(client, instagram_merchant, _payload())

    logs = caplog.text
    for secret in (IGSID, MESSAGE_TEXT, ZERNIO_TEST_KEY, WEBHOOK_TEST_SECRET, "/c/", "carta-di-prova", "mario.rossi"):
        assert secret not in logs
    assert crypto.igsid_blind_index(IGSID) not in logs


# --- pagine -----------------------------------------------------------------------------------------------

def test_carta_di_prova_pagina_pubblica_senza_dati(client, session, instagram_merchant):
    resp = client.get("/carta-di-prova")

    assert resp.status_code == 200
    assert "CARTA DI PROVA" in resp.text
    assert "deve ancora richiedere l'approvazione" in resp.text
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert 'name="robots" content="noindex, nofollow"' in resp.text
    assert "Bar Demo" not in resp.text                     # nessun dato di nessun negozio
    assert "set-cookie" not in resp.headers               # nessuna sessione


def test_carta_di_prova_non_ha_un_qr_scansionabile(client):
    text = client.get("/carta-di-prova").text.lower()
    assert "qrcode" not in text and "new qr" not in text and "<canvas" not in text and "<img" not in text
    assert "manifest" not in text and "serviceworker" not in text


def test_pagina_carta_identica_in_ogni_stato(client, session, merchant, card):
    token = crypto.card_link_token(card.id, card.link_version)
    pages = {}
    for name, state in (("attivo", {"is_approved": True, "is_paused": False}), ("attesa", PENDING), ("pausa", PAUSED)):
        _set_state(session, merchant, state)
        resp = client.get(f"/c/{token}")
        assert resp.status_code == 200
        pages[name] = resp.text

    assert pages["attesa"] == pages["attivo"] == pages["pausa"]
    for forbidden in ("attesa", "pausa", "approv", "prova"):
        assert forbidden not in pages["attivo"].lower()


def _button_tag(text, button_id):
    """Tag di apertura del `<button>` con quell'id."""
    start = text.index(f'id="{button_id}"')
    return text[text.rindex("<button", 0, start):text.index(">", start)]


def _is_disabled(tag):
    """True se il tag ha l'attributo `disabled` (non le classi `disabled:` di Tailwind)."""
    return re.search(r"\sdisabled(\s|=|$)", tag) is not None


def _banner(text):
    return 'id="service-banner"' in text


def test_banner_assente_se_attivo(auth_client, card):
    for path in ("/merchant/scanner", "/merchant/settings", f"/merchant/card/{card.id}/manage"):
        assert not _banner(auth_client.get(path).text), path


@pytest.mark.parametrize("state, marker, title", [
    (PENDING, 'data-state="pending"', "In attesa di approvazione"),
    (PAUSED, 'data-state="paused"', "Servizio in pausa"),
])
def test_banner_in_scanner_gestione_e_impostazioni(auth_client, session, merchant, card, state, marker, title):
    _set_state(session, merchant, state)
    for path in ("/merchant/scanner", "/merchant/settings", f"/merchant/card/{card.id}/manage"):
        text = auth_client.get(path).text
        assert marker in text and title in text, path


@pytest.mark.parametrize("state", NOT_ACTIVE)
def test_gestione_carta_disattiva_l_aggiunta_ma_non_la_rimozione(auth_client, session, merchant, card, state):
    _set_state(session, merchant, state)
    text = auth_client.get(f"/merchant/card/{card.id}/manage").text

    assert _is_disabled(_button_tag(text, "btn-add-tree")) and _is_disabled(_button_tag(text, "btn-cashback"))
    assert not _is_disabled(_button_tag(text, "btn-remove-cashback"))
    assert not _is_disabled(_button_tag(text, "btn-use-all-cb"))
    assert "prepareTreeOperation(-1)" in text and "TOGLI TREE POINTS" in text


def test_gestione_carta_attivo_ha_i_pulsanti_di_aggiunta_abilitati(auth_client, card):
    text = auth_client.get(f"/merchant/card/{card.id}/manage").text
    for button_id in ("btn-add-tree", "btn-cashback"):
        assert not _is_disabled(_button_tag(text, button_id))


# --- chiusura mensile invariata ---------------------------------------------------------------------------

def test_close_period_include_un_negozio_approvato_in_pausa(session, approved_merchants, mock_ecologi, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "ECOLOGI_API_KEY", "platform-key")
    monkeypatch.setattr(settings, "ECOLOGI_BASE_URL", "https://eco.real")
    monkeypatch.setattr(settings, "ECOLOGI_TEST_MODE", False)
    paused, attesa = approved_merchants({"Pausa": 350, "Attesa": 350})
    _set_state(session, paused, {"is_paused": True})
    _set_state(session, attesa, PENDING)

    asyncio.run(tree_service.close_period(
        session, "2026-10", global_cap=20, confirm=lambda plan: False,
        now=datetime(2026, 11, 1, 0, 10, tzinfo=timezone.utc),
    ))

    assert [call["name"].split(" · ")[0] for call in mock_ecologi] == ["Pausa"]


@pytest.mark.parametrize("state", NOT_ACTIVE)
def test_carta_di_un_altro_negozio_da_404_prima_del_403(auth_client, session, merchant, state):
    """La proprietà della carta si verifica prima dello stato: nessun 403 su una carta non propria."""
    altro = merchant_crud.create_merchant(session, {
        "business_name": "Altro", "email": "altro@test.it", "is_approved": True,
    })
    altrui = make_card(session, altro, igsid="igsid-altrui")
    _set_state(session, merchant, state)

    assert auth_client.post(f"/api/merchant/add-tree-points/{altrui.id}", json={"tree_points": 5}).status_code == 404
    assert auth_client.post(f"/api/merchant/add-point/{altrui.id}", json={"cb_points": 5}).status_code == 404
