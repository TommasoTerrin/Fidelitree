"""
Test del core puro di `zernio_service`: classificazione errori, corpi delle richieste, parsing degli account,
credenziali senza segreti nel repr. Nessun DB, nessuna rete, nessun mock.
"""

import pytest

from app.services import zernio_service as zs
from app.services.instagram_service import build_card_message
from app.services.zernio_service import (
    ZernioAccount, ZernioCredentials, ZernioErrorKind, build_card_body, build_menu_body, build_text_body,
    build_webhook_body, classify_error, parse_accounts, quota_scope_for,
)

CARD_URL = "https://fidelitree.example/c/abc123"
KEY = "sk_" + "ab12" * 16
K = ZernioErrorKind


# --- classify_error: una riga della mappatura per caso ---

@pytest.mark.parametrize("status,body,expected", [
    (401, {"code": "invalid_credentials"}, K.AUTH),
    (401, {"code": "missing_credentials"}, K.AUTH),
    (401, None, K.AUTH),
    (403, {"code": "insufficient_permissions", "required_group": "messages"}, K.AUTH),
    (403, {"code": "invalid_credentials"}, K.AUTH),
    (403, {"code": "message_allowance_exceeded"}, K.QUOTA),
    (409, {"code": "not_thread_owner"}, K.NOT_THREAD_OWNER),
    (409, {"code": "platform_api_error", "platformError": {"code": 10, "subcode": 2534037}}, K.NOT_THREAD_OWNER),
    (400, {"code": "platform_api_error", "platformError": {"code": 2, "subcode": 1545133}}, K.NOT_FOLLOWER),
    (400, {"platformError": {"code": "2", "subcode": "1545133"}}, K.NOT_FOLLOWER),
    (429, None, K.RATE_LIMITED),
    (429, {"error": "Too many requests"}, K.RATE_LIMITED),
    (500, None, K.SERVER),
    (502, {"error": "bad gateway"}, K.SERVER),
    (503, {}, K.SERVER),
    (400, {"code": "validation_error"}, K.BAD_REQUEST),
    (404, {"code": "account_not_found"}, K.BAD_REQUEST),
    (422, None, K.BAD_REQUEST),
])
def test_classify_error_mappatura(status, body, expected):
    assert classify_error(status, body) == expected


def test_403_senza_code_non_e_auth():
    assert classify_error(403, None) == K.BAD_REQUEST
    assert classify_error(403, {}) == K.BAD_REQUEST
    assert classify_error(403, {"error": "Inbox addon required"}) == K.BAD_REQUEST


def test_403_con_code_diverso_non_e_auth_ne_quota():
    # fuori finestra rifiutato da Meta, addon inbox mancante: non sono problemi di chiave
    assert classify_error(403, {"code": "platform_api_error"}) == K.BAD_REQUEST
    assert classify_error(403, {"code": "addon_required"}) == K.BAD_REQUEST


def test_classificazione_ignora_il_testo_di_error():
    # il testo non è stabile: decidono status, code e platformError
    assert classify_error(400, {"error": "invalid_credentials message_allowance_exceeded"}) == K.BAD_REQUEST
    assert classify_error(403, {"error": "invalid_credentials"}) == K.BAD_REQUEST
    assert classify_error(409, {"error": "not_thread_owner"}) == K.BAD_REQUEST


def test_400_con_platform_error_diverso_da_non_follower():
    assert classify_error(400, {"platformError": {"code": 2, "subcode": 999}}) == K.BAD_REQUEST
    assert classify_error(400, {"platformError": {"code": 100, "subcode": 1545133}}) == K.BAD_REQUEST
    assert classify_error(400, {"platformError": "stringa"}) == K.BAD_REQUEST


def test_409_idempotency_in_lavorazione_non_e_thread_owner():
    assert classify_error(409, {"code": "idempotency_in_progress"}) == K.BAD_REQUEST


def test_corpo_non_dizionario_non_manda_in_errore():
    assert classify_error(403, ["x"]) == K.BAD_REQUEST  # type: ignore[arg-type]
    assert classify_error(500, "boom") == K.SERVER  # type: ignore[arg-type]


def test_not_configured_esiste_ma_non_e_prodotto_da_classify():
    assert K.NOT_CONFIGURED.value == "not_configured"
    assert {c.value for c in K} == {
        "auth", "quota", "not_thread_owner", "not_follower", "rate_limited", "server", "bad_request",
        "not_configured",
    }


# --- corpi delle richieste ---

def test_build_card_body_struttura_esatta():
    card = build_card_message("Bar Demo", CARD_URL)
    body = build_card_body("acc_1", card)
    assert body == {
        "accountId": "acc_1",
        "template": {
            "type": "generic",
            "elements": [{
                "title": "Bar Demo",
                "subtitle": card.subtitle,
                "buttons": [{"type": "url", "title": card.button_title, "url": CARD_URL}],
            }],
        },
    }


def test_build_card_body_un_elemento_un_bottone_nessun_campo_di_primo_livello():
    body = build_card_body("acc_1", build_card_message("Bar Demo", CARD_URL))
    assert set(body) == {"accountId", "template"}
    assert "buttons" not in body and "message" not in body
    elements = body["template"]["elements"]
    assert len(elements) == 1
    assert len(elements[0]["buttons"]) == 1
    assert elements[0]["buttons"][0]["type"] == "url"


def test_build_text_body():
    assert build_text_body("acc_1", "ciao") == {"accountId": "acc_1", "message": "ciao"}


def test_build_webhook_body():
    body = build_webhook_body("acc_1", "https://app.example/webhooks/zernio/h", "s3cret")
    assert body == {
        "name": "Fidelitree",
        "url": "https://app.example/webhooks/zernio/h",
        "events": ["message.received"],
        "secret": "s3cret",
        "accountIds": ["acc_1"],
        "isActive": True,
    }


def test_build_menu_body():
    assert build_menu_body("🌳 La mia carta", "FIDELITREE_CARD") == {
        "persistent_menu": [{
            "locale": "default",
            "call_to_actions": [{"type": "postback", "title": "🌳 La mia carta", "payload": "FIDELITREE_CARD"}],
        }],
    }


# --- account ---

def test_parse_accounts_considera_solo_instagram():
    body = {"accounts": [
        {"_id": "a1", "platform": "instagram", "username": "bar_demo", "profileId": "p1"},
        {"_id": "a2", "platform": "facebook", "username": "pagina", "profileId": "p1"},
        {"_id": "a3", "platform": "twitter", "username": "x"},
        {"_id": "a4", "platform": "instagram", "username": "forno", "profileId": {"_id": "p2", "name": "Forno"}},
        {"_id": "a5", "platform": "instagram"},
    ]}
    assert parse_accounts(body) == [
        ZernioAccount(id="a1", username="bar_demo", profile_id="p1"),
        ZernioAccount(id="a4", username="forno", profile_id="p2"),
        ZernioAccount(id="a5", username=None, profile_id=None),
    ]


@pytest.mark.parametrize("body", [None, {}, {"accounts": None}, {"accounts": "x"}, [], {"accounts": [None, 3]}])
def test_parse_accounts_tollera_corpi_strani(body):
    assert parse_accounts(body) == []


def test_parse_accounts_salta_voci_senza_id():
    assert parse_accounts({"accounts": [{"platform": "instagram", "username": "x"}]}) == []


# --- credenziali ---

def test_repr_delle_credenziali_non_contiene_i_segreti():
    creds = ZernioCredentials(
        api_key=KEY, account_id="acc_1", profile_id="p1", webhook_secret="whsec-supersegreto",
        quota_scope="zernio:t1",
    )
    for text in (repr(creds), str(creds), creds.model_dump_json(), repr(creds.model_dump())):
        assert KEY not in text and "whsec-supersegreto" not in text
    assert creds.api_key.get_secret_value() == KEY


def test_quota_scope_for_segue_il_team_poi_l_account():
    assert quota_scope_for("t1", "acc_1") == "zernio:t1"
    assert quota_scope_for(None, "acc_1") == "account:acc_1"
    assert quota_scope_for("", "acc_1") == "account:acc_1"
    assert quota_scope_for(None, None) == ""


# --- messaggi d'errore ---

def test_i_messaggi_degli_errori_sono_in_italiano_e_per_ogni_tipo():
    for kind in ZernioErrorKind:
        assert zs.error_message(kind), kind


def test_zernio_error_ha_kind_e_status_e_nessun_segreto():
    err = zs.ZernioError(K.AUTH, 401)
    assert err.kind == K.AUTH and err.status == 401
    assert KEY not in str(err)
