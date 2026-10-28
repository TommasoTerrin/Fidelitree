"""
Test del webhook Zernio (ticket 06): dalla parola chiave alla card.

SQLite in-memory + `MockTransport` (fixture `zernio_mock`): nessuna rete. Il `conversation.id` dei payload è
volutamente diverso dall'IGSID, come nel formato reale (`conversation.id` è un handle di Zernio).
"""

import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.core import crypto
from app.core.clock import utc_now
from app.core.config import settings
from app.core.crypto import encrypt_secret
from app.core.enums import InstagramStatus, WebhookOutcome
from app.models.models import Card, ProcessedWebhookEvent, ZernioSendCounter
from app.services import instagram_service
from app.services.db_crud import card_crud, merchant_crud
from tests.conftest import (
    INSTAGRAM_ACCOUNT_ID, TEST_PUBLIC_BASE_URL, WEBHOOK_TEST_SECRET, ZERNIO_TEST_KEY, sign_body, signed_webhook,
)

IGSID = "igsid-segreto-777"
CONVERSATION = "conv-handle-42"
MESSAGE_TEXT = "carta!!"          # il testo di un cliente non deve mai comparire nei log
NO_PROFILE = object()              # "instagramProfile" assente dal payload


def _payload(
    event_id="evt-1", text=MESSAGE_TEXT, sender=IGSID, conversation=CONVERSATION, account=INSTAGRAM_ACCOUNT_ID,
    sent_at=None, direction="incoming", event="message.received", standby=False, postback=None,
    is_follower=True,
) -> dict:
    """Payload `message.received` realistico; `sent_at` di default è un minuto fa (la finestra di 24 h è reale)."""
    sent_at = sent_at or (utc_now() - timedelta(minutes=1))
    sender_data = {"id": sender, "name": "Mario Rossi", "username": "mario.rossi"}
    if is_follower is not NO_PROFILE:
        sender_data["instagramProfile"] = {"isFollower": is_follower}
    metadata = {}
    if postback:
        metadata["postbackPayload"] = postback
    if standby:
        metadata["standby"] = True
    return {
        "id": event_id,
        "event": event,
        "message": {
            "id": "m-in-1", "conversationId": conversation, "platform": "instagram", "direction": direction,
            "text": None if postback else text, "attachments": [], "sender": sender_data,
            "sentAt": sent_at.isoformat().replace("+00:00", "Z"),
        },
        "conversation": {"id": conversation, "platformConversationId": sender, "status": "active"},
        "account": {"id": account, "accountId": account, "platform": "instagram", "username": "bar_demo"},
        "metadata": metadata,
        "timestamp": sent_at.isoformat().replace("+00:00", "Z"),
        "test": False,
    }


def _utc(value: datetime) -> datetime:
    """SQLite restituisce datetime senza fuso: si ricostruisce l'UTC per confrontarli."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _cards(session) -> list[Card]:
    session.expire_all()
    return list(session.exec(select(Card)))


def _event(session, event_id="evt-1") -> ProcessedWebhookEvent | None:
    session.expire_all()
    return session.get(ProcessedWebhookEvent, event_id)


def _counters(session) -> list[ZernioSendCounter]:
    session.expire_all()
    return list(session.exec(select(ZernioSendCounter)))


def _link_of(body: dict) -> str:
    return body["template"]["elements"][0]["buttons"][0]["url"]


def _error(status: int, **body) -> httpx.Response:
    return httpx.Response(status, json={"error": "testo-non-stabile", **body})


def _not_follower() -> httpx.Response:
    """Risposta di Zernio quando Meta rifiuta la card a chi non segue l'account (2/1545133)."""
    return httpx.Response(400, json={
        "error": "x", "type": "platform_error", "code": "platform_api_error",
        "platformError": {"code": 2, "subcode": 1545133},
    })


def _other_merchant(session, hook_id="hook-2", account_id="acc-2", team_id=None, name="Forno Demo"):
    """Secondo negozio con Instagram collegato (stesso secret del primo)."""
    merchant = merchant_crud.create_merchant(session, {
        "business_name": name, "email": f"{hook_id}@test.it", "is_approved": True,
    })
    merchant.zernio_api_key_enc = encrypt_secret(ZERNIO_TEST_KEY)
    merchant.zernio_account_id = account_id
    merchant.zernio_team_id = team_id
    merchant.webhook_hook_id = hook_id
    merchant.webhook_secret_enc = encrypt_secret(WEBHOOK_TEST_SECRET)
    merchant.instagram_status = InstagramStatus.ACTIVE
    session.add(merchant)
    session.commit()
    session.refresh(merchant)
    return merchant


# --- flusso base ---

def test_flusso_base_crea_la_carta_e_invia_una_card(client, session, instagram_merchant, zernio_mock):
    response = signed_webhook(client, instagram_merchant, _payload())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    cards = _cards(session)
    assert len(cards) == 1
    card = cards[0]
    assert card.merchant_id == instagram_merchant.id
    assert card.igsid_hash == crypto.igsid_blind_index(IGSID)
    token = crypto.card_link_token(card.id, 1)
    assert card.link_token_hash == crypto.token_hash(token)

    assert len(zernio_mock.requests) == 1
    request = zernio_mock.requests[0]
    assert request.method == "POST"
    assert request.url.path == f"/api/v1/inbox/conversations/{CONVERSATION}/messages"
    assert request.headers["Authorization"] == f"Bearer {ZERNIO_TEST_KEY}"
    assert request.headers["Idempotency-Key"] == "evt-1"
    body = zernio_mock.bodies()[0]
    assert body["accountId"] == INSTAGRAM_ACCOUNT_ID
    element = body["template"]["elements"][0]
    assert element["title"] == "Bar Demo"
    assert element["buttons"] == [{"type": "url", "title": "Apri la carta", "url": f"{TEST_PUBLIC_BASE_URL}/c/{token}"}]
    assert _event(session).outcome == WebhookOutcome.SENT


def test_card_link_url_ricalcola_il_token(session, instagram_merchant):
    card, created = instagram_service.get_or_create_card(session, instagram_merchant, IGSID)
    assert created is True
    assert instagram_service.card_link_url(card) == f"{TEST_PUBLIC_BASE_URL}/c/{crypto.card_link_token(card.id, 1)}"


def test_secondo_messaggio_stessa_carta_stesso_link_e_dati_aggiornati(client, session, instagram_merchant, zernio_mock):
    first = datetime.now(timezone.utc) - timedelta(hours=3)
    second = datetime.now(timezone.utc) - timedelta(minutes=2)
    signed_webhook(client, instagram_merchant, _payload("evt-1", sent_at=first, conversation="conv-A"))
    signed_webhook(client, instagram_merchant, _payload("evt-2", text="carta!", sent_at=second, conversation="conv-B"))

    cards = _cards(session)
    assert len(cards) == 1
    assert cards[0].zernio_conversation_id == "conv-B"
    assert abs(_utc(cards[0].last_inbound_at) - second) < timedelta(seconds=1)
    first_body, second_body = zernio_mock.bodies()
    assert _link_of(first_body) == _link_of(second_body)
    assert zernio_mock.requests[1].url.path.endswith("/conv-B/messages")


def test_postback_del_menu_ha_lo_stesso_effetto_della_parola_chiave(client, session, instagram_merchant, zernio_mock):
    response = signed_webhook(
        client, instagram_merchant, _payload(postback=instagram_service.CARD_POSTBACK_PAYLOAD),
    )

    assert response.status_code == 200
    assert len(_cards(session)) == 1
    assert "template" in zernio_mock.bodies()[0]


def test_stesso_igsid_su_due_negozi_da_due_carte(client, session, instagram_merchant, zernio_mock):
    other = _other_merchant(session)
    signed_webhook(client, instagram_merchant, _payload("evt-1"))
    signed_webhook(client, other, _payload("evt-2", account="acc-2"))

    cards = _cards(session)
    assert len(cards) == 2
    assert {c.merchant_id for c in cards} == {instagram_merchant.id, other.id}
    assert cards[0].igsid_hash == cards[1].igsid_hash
    assert _link_of(zernio_mock.bodies()[0]) != _link_of(zernio_mock.bodies()[1])


# --- get_or_create_card ---

def test_get_or_create_card_e_idempotente(session, instagram_merchant):
    first, created_first = instagram_service.get_or_create_card(session, instagram_merchant, IGSID)
    again, created_again = instagram_service.get_or_create_card(session, instagram_merchant, IGSID)

    assert (created_first, created_again) == (True, False)
    assert first.id == again.id
    assert first.link_version == 1


def test_get_or_create_card_con_richieste_simultanee_riusa_la_carta(session, instagram_merchant, monkeypatch):
    """Un'altra richiesta crea la carta tra la ricerca e l'insert: si riusa quella, senza errori."""
    existing, _ = instagram_service.get_or_create_card(session, instagram_merchant, IGSID)
    real_lookup = card_crud.get_card_by_igsid_hash
    calls = []

    def lookup(session_, merchant_id, igsid_hash):
        calls.append(1)
        return None if len(calls) == 1 else real_lookup(session_, merchant_id, igsid_hash)

    monkeypatch.setattr(card_crud, "get_card_by_igsid_hash", lookup)

    card, created = instagram_service.get_or_create_card(session, instagram_merchant, IGSID)

    assert created is False
    assert card.id == existing.id
    assert len(calls) == 2


def test_get_or_create_card_rilancia_un_integrity_error_senza_doppione(session, instagram_merchant, monkeypatch):
    """Se dopo il conflitto la carta non si trova, l'errore non va nascosto."""
    def conflict(session_, card):
        raise IntegrityError("insert", {}, Exception("conflitto"))

    monkeypatch.setattr(card_crud, "add_card", conflict)
    with pytest.raises(IntegrityError):
        instagram_service.get_or_create_card(session, instagram_merchant, IGSID)


# --- idempotenza ---

def test_evento_duplicato_un_solo_invio_e_una_sola_carta(client, session, instagram_merchant, zernio_mock):
    payload = _payload("evt-dup")
    first = signed_webhook(client, instagram_merchant, payload)
    second = signed_webhook(client, instagram_merchant, payload)

    assert (first.status_code, second.status_code) == (200, 200)
    assert len(zernio_mock.requests) == 1
    assert len(_cards(session)) == 1


def test_senza_header_l_id_dell_evento_e_quello_del_payload(client, session, instagram_merchant, zernio_mock):
    payload = _payload("evt-nel-corpo")
    signed_webhook(client, instagram_merchant, payload, event_id="")
    signed_webhook(client, instagram_merchant, payload, event_id="")

    assert len(zernio_mock.requests) == 1
    assert _event(session, "evt-nel-corpo").outcome == WebhookOutcome.SENT
    assert zernio_mock.requests[0].headers["Idempotency-Key"] == "evt-nel-corpo"


def test_senza_nessun_id_dell_evento_non_si_elabora(client, session, instagram_merchant, zernio_mock):
    payload = _payload()
    del payload["id"]

    response = signed_webhook(client, instagram_merchant, payload, event_id="")

    assert response.status_code == 200
    assert zernio_mock.requests == []
    assert _cards(session) == []
    assert list(session.exec(select(ProcessedWebhookEvent))) == []


def test_un_evento_rimasto_received_non_si_rielabora(client, session, instagram_merchant, zernio_mock):
    """Un'elaborazione interrotta lascia `RECEIVED`: il retry non la ripete (rischio di doppio invio)."""
    session.add(ProcessedWebhookEvent(event_id="evt-1", merchant_id=instagram_merchant.id, received_at=utc_now()))
    session.commit()

    response = signed_webhook(client, instagram_merchant, _payload("evt-1"))

    assert response.status_code == 200
    assert zernio_mock.requests == []
    assert _cards(session) == []


# --- firma e routing ---

def test_firma_errata_401_senza_effetti(client, session, instagram_merchant, zernio_mock):
    response = signed_webhook(client, instagram_merchant, _payload(), secret="un-altro-secret")

    assert response.status_code == 401
    assert _cards(session) == []
    assert zernio_mock.requests == []
    assert list(session.exec(select(ProcessedWebhookEvent))) == []


def test_firma_assente_401(client, session, instagram_merchant, zernio_mock):
    response = signed_webhook(client, instagram_merchant, _payload(), signature="")

    assert response.status_code == 401
    assert _cards(session) == []
    assert zernio_mock.requests == []


def test_il_corpo_modificato_dopo_la_firma_e_rifiutato(client, session, instagram_merchant, zernio_mock):
    body = json.dumps(_payload()).encode()
    signature = sign_body(body)
    tampered = body.replace(b"evt-1", b"evt-9")

    response = signed_webhook(client, instagram_merchant, {}, event_id="evt-9", signature=signature, raw=tampered)

    assert response.status_code == 401
    assert zernio_mock.requests == []


def test_hook_id_sconosciuto_404(client, session, instagram_merchant, zernio_mock):
    response = signed_webhook(client, instagram_merchant, _payload(), hook_id="non-esiste")

    assert response.status_code == 404
    assert zernio_mock.requests == []


def test_negozio_senza_chiave_o_account_risponde_404(client, session, instagram_merchant, zernio_mock):
    instagram_merchant.zernio_api_key_enc = None
    session.add(instagram_merchant)
    session.commit()

    response = signed_webhook(client, instagram_merchant, _payload())

    assert response.status_code == 404
    assert zernio_mock.requests == []


def test_negozio_senza_secret_del_webhook_401(client, session, instagram_merchant, zernio_mock):
    instagram_merchant.webhook_secret_enc = None
    session.add(instagram_merchant)
    session.commit()

    assert signed_webhook(client, instagram_merchant, _payload()).status_code == 401
    assert zernio_mock.requests == []


def test_un_negozio_non_accetta_la_firma_di_un_altro(client, session, instagram_merchant, zernio_mock):
    other = _other_merchant(session)
    other.webhook_secret_enc = encrypt_secret("secret-del-secondo-negozio")
    session.add(other)
    session.commit()

    response = signed_webhook(client, other, _payload(account="acc-2"))  # firmato col secret del primo

    assert response.status_code == 401


def test_account_id_diverso_da_quello_del_negozio_200_senza_carta(client, session, instagram_merchant, zernio_mock):
    response = signed_webhook(client, instagram_merchant, _payload(account="acc-di-un-altro"))

    assert response.status_code == 200
    assert _cards(session) == []
    assert zernio_mock.requests == []
    assert _event(session).outcome == WebhookOutcome.IGNORED


# --- messaggi ignorati ---

@pytest.mark.parametrize("overrides", [
    {"text": "ciao"},
    {"text": "vorrei la carta"},
    {"postback": "ALTRO_PAYLOAD"},
    {"direction": "outgoing"},
    {"event": "message.sent"},
])
def test_messaggi_ignorati_senza_carta_e_senza_invio(client, session, instagram_merchant, zernio_mock, overrides):
    response = signed_webhook(client, instagram_merchant, _payload(**overrides))

    assert response.status_code == 200
    assert _cards(session) == []
    assert zernio_mock.requests == []
    assert _event(session).outcome == WebhookOutcome.IGNORED


def test_json_non_valido_ma_firmato_200(client, session, instagram_merchant, zernio_mock):
    response = signed_webhook(client, instagram_merchant, {}, event_id="evt-x", raw=b"{non e json")

    assert response.status_code == 200
    assert _cards(session) == []
    assert zernio_mock.requests == []


def test_json_che_non_e_un_oggetto_200(client, session, instagram_merchant, zernio_mock):
    response = signed_webhook(client, instagram_merchant, {}, event_id="evt-x", raw=b"[1, 2]")

    assert response.status_code == 200
    assert zernio_mock.requests == []


def test_payload_incompleto_firmato_200_ignorato(client, session, instagram_merchant, zernio_mock):
    payload = _payload()
    del payload["message"]["sender"]["id"]

    response = signed_webhook(client, instagram_merchant, payload)

    assert response.status_code == 200
    assert _cards(session) == []
    assert _event(session).outcome == WebhookOutcome.IGNORED


# --- standby ---

def test_standby_nessuna_carta_nessun_invio_e_rilevamento(client, session, instagram_merchant, zernio_mock):
    assert instagram_merchant.standby_detected_at is None

    response = signed_webhook(client, instagram_merchant, _payload(standby=True))

    assert response.status_code == 200
    assert _cards(session) == []
    assert zernio_mock.requests == []
    session.refresh(instagram_merchant)
    assert abs(_utc(instagram_merchant.standby_detected_at) - utc_now()) < timedelta(seconds=30)
    assert _event(session).outcome == WebhookOutcome.STANDBY


# --- finestra di 24 ore ---

def test_fuori_finestra_la_carta_si_aggiorna_ma_non_si_invia(client, session, instagram_merchant, zernio_mock):
    sent_at = utc_now() - timedelta(hours=25)

    response = signed_webhook(client, instagram_merchant, _payload(sent_at=sent_at))

    assert response.status_code == 200
    assert zernio_mock.requests == []
    cards = _cards(session)
    assert len(cards) == 1
    assert cards[0].zernio_conversation_id == CONVERSATION
    assert abs(_utc(cards[0].last_inbound_at) - sent_at) < timedelta(seconds=1)
    assert _event(session).outcome == WebhookOutcome.OUT_OF_WINDOW


# --- carta solo a chi segue (decisione 2026-10-23) ---

def test_follower_riceve_la_card(client, session, instagram_merchant, zernio_mock):
    signed_webhook(client, instagram_merchant, _payload(is_follower=True))

    assert len(_cards(session)) == 1
    assert "template" in zernio_mock.bodies()[0]


@pytest.mark.parametrize("profile", [None, NO_PROFILE])
def test_follower_non_disponibile_riceve_la_card(client, session, instagram_merchant, zernio_mock, profile):
    """`isFollower` null o assente → card (ipotesi da rivedere nel collaudo finale)."""
    signed_webhook(client, instagram_merchant, _payload(is_follower=profile))

    assert len(_cards(session)) == 1
    assert "template" in zernio_mock.bodies()[0]
    assert _event(session).outcome == WebhookOutcome.SENT


def test_non_follower_nessuna_carta_e_un_solo_testo_di_invito(client, session, instagram_merchant, zernio_mock):
    response = signed_webhook(client, instagram_merchant, _payload(is_follower=False))

    assert response.status_code == 200
    assert _cards(session) == []
    assert len(zernio_mock.requests) == 1
    request = zernio_mock.requests[0]
    assert request.method == "POST"
    assert request.url.path == f"/api/v1/inbox/conversations/{CONVERSATION}/messages"
    assert request.headers["Idempotency-Key"] == "evt-1:follow"
    body = zernio_mock.bodies()[0]
    assert set(body) == {"accountId", "message"}
    assert body["message"] == instagram_service.build_follow_prompt_text(
        "Bar Demo", "bar_demo", settings.INSTAGRAM_CARD_KEYWORD,
    )
    assert "@bar_demo" in body["message"]
    assert "/c/" not in body["message"]
    assert _event(session).outcome == WebhookOutcome.FOLLOW_REQUESTED


def test_invito_senza_handle_cita_il_nome_del_negozio(client, session, instagram_merchant, zernio_mock):
    instagram_merchant.instagram_username = None
    session.add(instagram_merchant)
    session.commit()

    signed_webhook(client, instagram_merchant, _payload(is_follower=False))

    message = zernio_mock.bodies()[0]["message"]
    assert "@" not in message
    assert message.count("Bar Demo") == 2


def test_non_follower_che_riscrive_riceve_di_nuovo_l_invito_e_poi_la_card_dopo_il_follow(
    client, session, instagram_merchant, zernio_mock,
):
    signed_webhook(client, instagram_merchant, _payload("evt-1", is_follower=False))
    signed_webhook(client, instagram_merchant, _payload("evt-2", is_follower=True))

    assert len(_cards(session)) == 1
    bodies = zernio_mock.bodies()
    assert "message" in bodies[0] and "template" in bodies[1]


def test_non_follower_fuori_finestra_nessun_invio_proattivo(client, session, instagram_merchant, zernio_mock):
    sent_at = utc_now() - timedelta(hours=25)

    signed_webhook(client, instagram_merchant, _payload(is_follower=False, sent_at=sent_at))

    assert zernio_mock.requests == []
    assert _cards(session) == []
    assert _event(session).outcome == WebhookOutcome.OUT_OF_WINDOW


def test_non_follower_l_invito_conta_per_la_quota(client, session, instagram_merchant, zernio_mock):
    signed_webhook(client, instagram_merchant, _payload(is_follower=False))

    counters = _counters(session)
    assert [(c.quota_scope, c.sent) for c in counters] == [(f"account:{INSTAGRAM_ACCOUNT_ID}", 1)]


def test_non_follower_l_invito_attiva_il_negozio_in_attesa(client, session, instagram_merchant, zernio_mock):
    instagram_merchant.instagram_status = InstagramStatus.AWAITING_TEST_DM
    session.add(instagram_merchant)
    session.commit()

    signed_webhook(client, instagram_merchant, _payload(is_follower=False))

    session.refresh(instagram_merchant)
    assert instagram_merchant.instagram_status == InstagramStatus.ACTIVE


def test_non_follower_se_anche_l_invito_fallisce_send_failed(client, session, instagram_merchant, zernio_mock):
    zernio_mock.queue(_error(500, code="internal_error"))

    response = signed_webhook(client, instagram_merchant, _payload(is_follower=False))

    assert response.status_code == 200
    assert len(zernio_mock.requests) == 1
    assert _cards(session) == []
    assert _event(session).outcome == WebhookOutcome.SEND_FAILED
    assert _counters(session) == []


def test_non_follower_con_chiave_rifiutata_segna_key_invalid(client, session, instagram_merchant, zernio_mock):
    zernio_mock.queue(_error(401, code="invalid_credentials"))

    signed_webhook(client, instagram_merchant, _payload(is_follower=False))

    session.refresh(instagram_merchant)
    assert instagram_merchant.instagram_status == InstagramStatus.KEY_INVALID
    assert _event(session).outcome == WebhookOutcome.SEND_FAILED


# --- errori di invio ---

def test_card_rifiutata_a_un_non_follower_ripiega_sul_testo_con_il_link(client, session, instagram_merchant, zernio_mock):
    zernio_mock.queue(_not_follower())

    response = signed_webhook(client, instagram_merchant, _payload())

    assert response.status_code == 200
    assert len(zernio_mock.requests) == 2
    card = _cards(session)[0]
    expected_url = f"{TEST_PUBLIC_BASE_URL}/c/{crypto.card_link_token(card.id, 1)}"
    second = zernio_mock.bodies()[1]
    assert second == {"accountId": INSTAGRAM_ACCOUNT_ID, "message": instagram_service.build_fallback_text("Bar Demo", expected_url)}
    assert zernio_mock.requests[1].headers["Idempotency-Key"] == "evt-1:text"
    assert _event(session).outcome == WebhookOutcome.FALLBACK_SENT
    assert [c.sent for c in _counters(session)] == [1]


def test_se_anche_il_ripiego_fallisce_send_failed(client, session, instagram_merchant, zernio_mock):
    zernio_mock.queue(_not_follower(), _error(500, code="internal_error"))

    response = signed_webhook(client, instagram_merchant, _payload())

    assert response.status_code == 200
    assert len(zernio_mock.requests) == 2
    assert _event(session).outcome == WebhookOutcome.SEND_FAILED
    assert _counters(session) == []


def test_chiave_rifiutata_401_key_invalid_e_risposta_200(client, session, instagram_merchant, zernio_mock):
    zernio_mock.queue(_error(401, code="invalid_credentials"))

    response = signed_webhook(client, instagram_merchant, _payload())

    assert response.status_code == 200
    session.refresh(instagram_merchant)
    assert instagram_merchant.instagram_status == InstagramStatus.KEY_INVALID
    assert _event(session).outcome == WebhookOutcome.SEND_FAILED
    assert len(zernio_mock.requests) == 1


def test_errore_500_un_solo_tentativo(client, session, instagram_merchant, zernio_mock):
    zernio_mock.queue(_error(500, code="internal_error"))

    response = signed_webhook(client, instagram_merchant, _payload())

    assert response.status_code == 200
    assert len(zernio_mock.requests) == 1
    assert _event(session).outcome == WebhookOutcome.SEND_FAILED
    assert _counters(session) == []


def test_timeout_un_solo_tentativo_esito_incerto_e_contato(client, session, instagram_merchant, zernio_mock):
    """Nessuna risposta entro il tempo: il messaggio può essere partito (collaudo 2026-10-28), quindi non è `send_failed`."""
    zernio_mock.queue(httpx.ReadTimeout("lento"))

    response = signed_webhook(client, instagram_merchant, _payload())

    assert response.status_code == 200
    assert len(zernio_mock.requests) == 1
    assert _event(session).outcome == WebhookOutcome.SEND_UNCERTAIN
    assert [c.sent for c in _counters(session)] == [1]


def test_timeout_non_attiva_il_negozio(client, session, instagram_merchant, zernio_mock):
    instagram_merchant.instagram_status = InstagramStatus.AWAITING_TEST_DM
    session.add(instagram_merchant)
    session.commit()
    zernio_mock.queue(httpx.ReadTimeout("lento"))

    signed_webhook(client, instagram_merchant, _payload())

    session.refresh(instagram_merchant)
    assert instagram_merchant.instagram_status == InstagramStatus.AWAITING_TEST_DM


def test_timeout_dell_invito_a_seguire_esito_incerto_e_contato(client, session, instagram_merchant, zernio_mock):
    zernio_mock.queue(httpx.ReadTimeout("lento"))

    signed_webhook(client, instagram_merchant, _payload(is_follower=False))

    assert len(zernio_mock.requests) == 1
    assert _event(session).outcome == WebhookOutcome.SEND_UNCERTAIN
    assert [c.sent for c in _counters(session)] == [1]


def test_connessione_mancata_resta_send_failed_e_non_conta(client, session, instagram_merchant, zernio_mock):
    """La richiesta non è mai partita: il messaggio non c'è, quindi nessun invio da contare."""
    zernio_mock.queue(httpx.ConnectError("rete assente"))

    signed_webhook(client, instagram_merchant, _payload())

    assert _event(session).outcome == WebhookOutcome.SEND_FAILED
    assert _counters(session) == []


def test_conversazione_di_un_altra_app_vale_come_standby(client, session, instagram_merchant, zernio_mock):
    zernio_mock.queue(_error(409, code="not_thread_owner"))

    response = signed_webhook(client, instagram_merchant, _payload())

    assert response.status_code == 200
    assert _event(session).outcome == WebhookOutcome.STANDBY
    assert len(zernio_mock.requests) == 1
    session.refresh(instagram_merchant)
    assert instagram_merchant.standby_detected_at is not None


def test_quota_esaurita_non_blocca_la_risposta(client, session, instagram_merchant, zernio_mock):
    zernio_mock.queue(_error(403, code="message_allowance_exceeded"))

    response = signed_webhook(client, instagram_merchant, _payload())

    assert response.status_code == 200
    assert _event(session).outcome == WebhookOutcome.SEND_FAILED


def test_link_non_https_non_manda_nulla_e_risponde_200(client, session, instagram_merchant, zernio_mock, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "http://127.0.0.1:8001")

    response = signed_webhook(client, instagram_merchant, _payload())

    assert response.status_code == 200
    assert zernio_mock.requests == []
    assert _event(session).outcome == WebhookOutcome.SEND_FAILED


def test_nome_del_negozio_troppo_lungo_non_manda_nulla_e_risponde_200(client, session, instagram_merchant, zernio_mock):
    instagram_merchant.business_name = "x" * 81
    session.add(instagram_merchant)
    session.commit()

    response = signed_webhook(client, instagram_merchant, _payload())

    assert response.status_code == 200
    assert zernio_mock.requests == []
    assert _event(session).outcome == WebhookOutcome.SEND_FAILED


# --- contatore della quota e attivazione ---

def test_contatore_due_invii_nello_stesso_mese(client, session, instagram_merchant, zernio_mock):
    signed_webhook(client, instagram_merchant, _payload("evt-1"))
    signed_webhook(client, instagram_merchant, _payload("evt-2"))

    counters = _counters(session)
    assert len(counters) == 1
    assert counters[0].quota_scope == f"account:{INSTAGRAM_ACCOUNT_ID}"
    assert counters[0].period == datetime.now(timezone.utc).strftime("%Y-%m")
    assert counters[0].sent == 2


def test_due_negozi_dello_stesso_team_condividono_il_contatore(client, session, instagram_merchant, zernio_mock):
    instagram_merchant.zernio_team_id = "team-9"
    session.add(instagram_merchant)
    other = _other_merchant(session, team_id="team-9")

    signed_webhook(client, instagram_merchant, _payload("evt-1"))
    signed_webhook(client, other, _payload("evt-2", account="acc-2"))

    counters = _counters(session)
    assert [(c.quota_scope, c.sent) for c in counters] == [("zernio:team-9", 2)]


def test_il_contatore_non_cresce_se_non_si_invia(client, session, instagram_merchant, zernio_mock):
    signed_webhook(client, instagram_merchant, _payload("evt-1", text="ciao"))
    signed_webhook(client, instagram_merchant, _payload("evt-2", sent_at=utc_now() - timedelta(hours=30)))

    assert _counters(session) == []


def test_avviso_di_quota_una_sola_volta_al_superamento_della_soglia(
    client, session, instagram_merchant, zernio_mock, monkeypatch, caplog,
):
    monkeypatch.setattr(settings, "ZERNIO_MONTHLY_SEND_LIMIT", 4)
    monkeypatch.setattr(settings, "ZERNIO_SEND_WARN_PERCENT", 50)
    caplog.set_level(logging.WARNING)

    for i in range(1, 5):
        signed_webhook(client, instagram_merchant, _payload(f"evt-{i}"))

    warnings = [r for r in caplog.records if "quota" in r.getMessage().lower() and r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert str(instagram_merchant.id) in warnings[0].getMessage()


def test_attivazione_al_primo_invio_riuscito(client, session, instagram_merchant, zernio_mock):
    instagram_merchant.instagram_status = InstagramStatus.AWAITING_TEST_DM
    session.add(instagram_merchant)
    session.commit()

    signed_webhook(client, instagram_merchant, _payload())

    session.refresh(instagram_merchant)
    assert instagram_merchant.instagram_status == InstagramStatus.ACTIVE


def test_attivazione_anche_con_il_ripiego(client, session, instagram_merchant, zernio_mock):
    instagram_merchant.instagram_status = InstagramStatus.AWAITING_TEST_DM
    session.add(instagram_merchant)
    session.commit()
    zernio_mock.queue(_not_follower())

    signed_webhook(client, instagram_merchant, _payload())

    session.refresh(instagram_merchant)
    assert instagram_merchant.instagram_status == InstagramStatus.ACTIVE


def test_con_standby_resta_in_attesa_del_dm_di_prova(client, session, instagram_merchant, zernio_mock):
    instagram_merchant.instagram_status = InstagramStatus.AWAITING_TEST_DM
    session.add(instagram_merchant)
    session.commit()

    signed_webhook(client, instagram_merchant, _payload(standby=True))

    session.refresh(instagram_merchant)
    assert instagram_merchant.instagram_status == InstagramStatus.AWAITING_TEST_DM


def test_un_invio_riuscito_non_riattiva_una_chiave_non_valida(client, session, instagram_merchant, zernio_mock):
    instagram_merchant.instagram_status = InstagramStatus.KEY_INVALID
    session.add(instagram_merchant)
    session.commit()

    signed_webhook(client, instagram_merchant, _payload())

    session.refresh(instagram_merchant)
    assert instagram_merchant.instagram_status == InstagramStatus.KEY_INVALID


# --- pulizia degli eventi vecchi ---

def test_pulizia_degli_eventi_oltre_i_7_giorni(client, session, instagram_merchant, zernio_mock):
    now = utc_now()
    for event_id, age in (("old-8d", 8), ("recent-6d", 6)):
        session.add(ProcessedWebhookEvent(
            event_id=event_id, merchant_id=instagram_merchant.id, received_at=now - timedelta(days=age),
            outcome=WebhookOutcome.SENT,
        ))
    session.commit()

    signed_webhook(client, instagram_merchant, _payload("evt-nuovo"))

    assert _event(session, "old-8d") is None
    assert _event(session, "recent-6d") is not None
    assert _event(session, "evt-nuovo") is not None


# --- nessun segreto nei log né nelle risposte ---

def test_nessun_segreto_nei_log_ne_nelle_risposte(client, session, instagram_merchant, zernio_mock, caplog):
    """Flusso completo con errori: IGSID, token, link, chiave, secret e testo del messaggio non compaiono mai."""
    caplog.set_level(logging.DEBUG)
    other = _other_merchant(session)
    zernio_mock.queue(
        _not_follower(),                                  # evt-1: card rifiutata → ripiego (ok)
        httpx.Response(200, json={"success": True, "data": {"messageId": "m_x"}}),
        _error(401, code="invalid_credentials"),          # evt-2: chiave rifiutata
        httpx.ReadTimeout("lento"),                       # evt-3: timeout
        _error(500, code="internal_error"),               # evt-4: errore del server
        httpx.Response(200, json={"success": True, "data": {"messageId": "m_y"}}),  # evt-6: invito
    )
    responses = [
        signed_webhook(client, instagram_merchant, _payload("evt-1")),
        signed_webhook(client, instagram_merchant, _payload("evt-2")),
        signed_webhook(client, instagram_merchant, _payload("evt-3")),
        signed_webhook(client, instagram_merchant, _payload("evt-4")),
        signed_webhook(client, instagram_merchant, _payload("evt-5", text="ciao-segretissimo")),
        signed_webhook(client, instagram_merchant, _payload("evt-6", is_follower=False)),
        signed_webhook(client, instagram_merchant, _payload("evt-7", standby=True)),
        signed_webhook(client, instagram_merchant, _payload("evt-8", sent_at=utc_now() - timedelta(hours=30))),
        signed_webhook(client, instagram_merchant, _payload("evt-9"), secret="firma-sbagliata"),
        signed_webhook(client, instagram_merchant, {}, event_id="evt-10", raw=b"{rotto"),
        signed_webhook(client, instagram_merchant, _payload("evt-11"), hook_id="sconosciuto"),
        signed_webhook(client, other, _payload("evt-12", account="acc-2", is_follower=NO_PROFILE)),
    ]

    logs = caplog.text
    bodies = " ".join(r.text for r in responses)
    tokens = [crypto.card_link_token(c.id, c.link_version) for c in _cards(session)]
    assert tokens
    secrets = [IGSID, MESSAGE_TEXT, "ciao-segretissimo", ZERNIO_TEST_KEY, WEBHOOK_TEST_SECRET, "firma-sbagliata",
               "/c/", "mario.rossi", "Mario Rossi", *tokens]
    for secret in secrets:
        assert secret not in logs, f"{secret!r} compare nei log"
        assert secret not in bodies, f"{secret!r} compare nelle risposte"
    assert crypto.igsid_blind_index(IGSID) not in logs
