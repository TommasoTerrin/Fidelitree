"""
Test del core puro di `instagram_service`: payload, firma, trigger, card, finestra 24 ore, quota.
Nessun DB, nessuna rete, nessun mock.
"""

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.core.errors import InvalidInputError, MessageTooLongError
from app.services import instagram_service as ig
from app.services.instagram_service import (
    CARD_BUTTON_TITLE, CARD_POSTBACK_PAYLOAD, CARD_SUBTITLE, InboundMessage, Trigger,
    build_card_message, build_fallback_text, can_reply, detect_trigger, normalize_text,
    parse_message_received, quota_status, verify_signature,
)

CARD_URL = "https://fidelitree.example/c/abc123"
SENT_AT = "2026-10-22T10:00:00.000Z"


def _payload(**overrides):
    """Payload `message.received` d'esempio (formato di zernio-notes), con `sentAt`."""
    payload = {
        "id": "evt-1",
        "event": "message.received",
        "message": {
            "id": "m-1",
            "conversationId": "conv-1",
            "platform": "instagram",
            "direction": "incoming",
            "text": "CARTA",
            "attachments": [],
            "sender": {"id": "igsid-1", "name": "Mario", "username": "mario"},
            "sentAt": SENT_AT,
        },
        "conversation": {"id": "conv-1", "platformConversationId": "igsid-1", "status": "active"},
        "account": {"id": "acc-1", "accountId": "acc-1", "platform": "instagram", "username": "bar"},
        "metadata": {},
        "timestamp": SENT_AT,
        "test": False,
    }
    payload.update(overrides)
    return payload


def _msg(**overrides):
    data = dict(
        event_id="evt-1", source="dm_text", account_id="acc-1", conversation_id="conv-1",
        sender_id="igsid-1", direction="incoming", text="CARTA", postback_payload=None,
        sent_at=datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc), standby=False,
    )
    data.update(overrides)
    return InboundMessage(**data)


# --- parse_message_received ---

def test_parse_estrae_i_campi_del_payload_di_esempio():
    msg = parse_message_received(_payload(), "evt-1")
    assert msg.event_id == "evt-1"
    assert msg.source == "dm_text"
    assert (msg.account_id, msg.conversation_id, msg.sender_id) == ("acc-1", "conv-1", "igsid-1")
    assert msg.direction == "incoming"
    assert msg.text == "CARTA"
    assert msg.postback_payload is None
    assert msg.standby is False
    assert msg.sent_at == datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc)


def test_parse_postback():
    msg = parse_message_received(_payload(metadata={"postbackPayload": CARD_POSTBACK_PAYLOAD}), "evt-1")
    assert msg.source == "dm_postback"
    assert msg.postback_payload == CARD_POSTBACK_PAYLOAD


def test_parse_standby():
    assert parse_message_received(_payload(metadata={"standby": True}), "evt-1").standby is True


def test_parse_evento_diverso_da_message_received():
    assert parse_message_received(_payload(event="message.sent"), "evt-1") is None


def test_parse_testo_nullo_ammesso():
    payload = _payload()
    payload["message"]["text"] = None
    assert parse_message_received(payload, "evt-1").text is None


def test_parse_sent_at_senza_fuso_vale_utc():
    payload = _payload()
    payload["message"]["sentAt"] = "2026-10-22T10:00:00"
    assert parse_message_received(payload, "evt-1").sent_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("path", [
    ("account", "accountId"), ("conversation", "id"), ("message", "sender", "id"), ("message", "sentAt"),
])
def test_parse_campo_obbligatorio_mancante(path):
    payload = _payload()
    node = payload
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    with pytest.raises(InvalidInputError, match=path[-1]):
        parse_message_received(payload, "evt-1")


def test_parse_blocco_intero_mancante():
    payload = _payload()
    del payload["conversation"]
    with pytest.raises(InvalidInputError):
        parse_message_received(payload, "evt-1")


def test_parse_sent_at_illeggibile():
    payload = _payload()
    payload["message"]["sentAt"] = "ieri"
    with pytest.raises(InvalidInputError, match="sentAt"):
        parse_message_received(payload, "evt-1")


# --- verify_signature ---

def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_firma_corretta():
    body = json.dumps(_payload()).encode()
    assert verify_signature("segreto", body, _sign("segreto", body)) is True


def test_firma_non_valida():
    body = b'{"event":"message.received"}'
    good = _sign("segreto", body)
    assert verify_signature("segreto", body[:-1] + b" ", good) is False  # un byte del corpo cambiato
    assert verify_signature("altro-secret", body, good) is False
    assert verify_signature("segreto", body, None) is False
    assert verify_signature("segreto", body, "") is False
    assert verify_signature("segreto", body, "non-esadecimale-€") is False


# --- normalize_text ---

@pytest.mark.parametrize("text", [" Carta! ", "/carta", "CARTA 🌳", "cartà", "CaRtA"])
def test_normalize_text_riduce_a_carta(text):
    assert normalize_text(text) == "carta"


def test_normalize_text_nullo_e_spazi():
    assert normalize_text(None) == ""
    assert normalize_text("") == ""
    assert normalize_text("  vorrei   la\tcarta ") == "vorrei la carta"


# --- detect_trigger ---

def test_trigger_da_testo():
    assert detect_trigger(_msg(text="Carta!"), "CARTA") == Trigger.CARD_REQUEST


def test_trigger_da_postback_anche_con_testo_diverso():
    msg = _msg(source="dm_postback", text="🌳 La mia carta", postback_payload=CARD_POSTBACK_PAYLOAD)
    assert detect_trigger(msg, "CARTA") == Trigger.CARD_REQUEST


@pytest.mark.parametrize("overrides", [
    dict(text="vorrei la carta"),
    dict(text=""),
    dict(text=None),
    dict(source="dm_postback", text="CARTA", postback_payload="ALTRO"),
    dict(source="dm_postback", text="CARTA", postback_payload=None),
    dict(direction="outgoing"),
    dict(direction="outgoing", source="dm_postback", postback_payload=CARD_POSTBACK_PAYLOAD),
])
def test_nessun_trigger(overrides):
    assert detect_trigger(_msg(**overrides), "CARTA") is None


def test_trigger_keyword_configurabile_e_vuota():
    assert detect_trigger(_msg(text="Tessera"), "tessera") == Trigger.CARD_REQUEST
    assert detect_trigger(_msg(text=""), "") is None
    assert detect_trigger(_msg(text="!!!"), "???") is None


# --- build_card_message ---

def test_card_bar_demo():
    card = build_card_message("Bar Demo", CARD_URL)
    assert card.title == "Bar Demo"
    assert card.subtitle == "La tua carta fedeltà: punti, cashback e alberi 🌳"
    assert card.button_title == "Apri la carta"
    assert card.button_url == CARD_URL


def test_card_nome_di_80_caratteri_ok_81_troppo_lungo():
    assert build_card_message("a" * 80, CARD_URL).title == "a" * 80
    with pytest.raises(MessageTooLongError, match="title") as exc:
        build_card_message("a" * 81, CARD_URL)
    assert "80" in str(exc.value) and "81" in str(exc.value)
    assert CARD_URL not in str(exc.value)


def test_card_url_non_https():
    with pytest.raises(InvalidInputError, match="https") as exc:
        build_card_message("Bar Demo", "http://fidelitree.example/c/segreto-token")
    assert "segreto-token" not in str(exc.value)


@pytest.mark.parametrize("name", ["", "   "])
def test_card_nome_vuoto(name):
    with pytest.raises(InvalidInputError):
        build_card_message(name, CARD_URL)


def test_costanti_fisse_nei_limiti():
    assert len(CARD_SUBTITLE) <= ig.CARD_SUBTITLE_MAX == 80
    assert len(CARD_BUTTON_TITLE) <= ig.CARD_BUTTON_TITLE_MAX == 20
    assert ig.CARD_TITLE_MAX == 80


# --- build_fallback_text ---

def test_fallback_contiene_nome_e_link():
    text = build_fallback_text("Bar Demo", CARD_URL)
    assert text == f"La tua carta fedeltà di Bar Demo: {CARD_URL}"
    assert len(text) <= 640


def test_fallback_controlli():
    with pytest.raises(MessageTooLongError, match="text"):
        build_fallback_text("a" * 80, "https://x.example/" + "p" * 600)
    with pytest.raises(InvalidInputError):
        build_fallback_text("Bar Demo", "http://x.example/c/t")
    with pytest.raises(InvalidInputError):
        build_fallback_text("", CARD_URL)


# --- can_reply ---

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def test_finestra_24_ore():
    assert can_reply(NOW - timedelta(hours=23, minutes=59), NOW) is True
    assert can_reply(NOW - timedelta(hours=24), NOW) is False
    assert can_reply(NOW - timedelta(hours=51), NOW) is False


# --- quota_status ---

def test_quota_sotto_soglia_di_avviso():
    status = quota_status(7499, 10000, 75)
    assert (status.warning, status.exhausted, status.percent) == (False, False, 74)


def test_quota_avviso_ed_esaurimento():
    assert quota_status(7500, 10000, 75).warning is True
    assert quota_status(7500, 10000, 75).exhausted is False
    esaurita = quota_status(10000, 10000, 75)
    assert (esaurita.warning, esaurita.exhausted, esaurita.percent) == (True, True, 100)


def test_quota_limite_zero_non_divide():
    status = quota_status(5, 0, 75)
    assert (status.percent, status.warning, status.exhausted) == (0, False, False)
