"""
Test del webhook Zernio per i commenti (v0.4.1, ticket 04, AC-14..19).

SQLite in-memory + `MockTransport` (fixture `zernio_mock`): nessuna rete. Si entra dal confine pubblico, cioe'
`POST /webhooks/zernio/{hook_id}` firmato con un evento `comment.received`, e si leggono la richiesta inviata a
Zernio (risposta privata), la riga di dedup, la riga `campaign` e la tabella `Card`.
"""

import httpx
import pytest

from sqlmodel import select

from app.core.config import settings
from app.core.enums import InstagramStatus, WebhookOutcome
from app.models.models import Campaign, Card, ProcessedWebhookEvent, ZernioSendCounter
from tests.conftest import INSTAGRAM_ACCOUNT_ID, signed_webhook

POST_ID = "17890000000000001"
COMMENT_ID = "c_1"
PROMO_TEXT = "Black Friday: un caffe' in omaggio con la tua carta."


def _comment_payload(text: str, event_id: str = "evt_c1") -> dict:
    """`comment.received` di un commento `text` al post `POST_ID` (payload di riferimento del contract §11)."""
    return {
        "id": event_id,
        "event": "comment.received",
        "account": {"accountId": INSTAGRAM_ACCOUNT_ID},
        "comment": {
            "id": COMMENT_ID, "platformPostId": POST_ID, "postId": None, "text": text,
            "author": {"id": "igsid-commentatore", "username": "cliente"},
        },
    }


@pytest.mark.parametrize("stato", ["attivo", "in_attesa", "in_pausa"])
def test_commento_carta_riceve_l_invito_in_risposta_privata_in_ogni_stato_senza_carta_ne_contatori(
    client, session, instagram_merchant, zernio_mock, stato,
):
    """
    AC-16: il commento uguale alla parola della carta (`settings.INSTAGRAM_CARD_KEYWORD`, «CARTA») produce, con il
    negozio attivo, in attesa (non approvato) o in pausa (D7: l'invito non dipende dallo stato), UNA sola risposta
    privata al commento giusto: `POST .../v1/inbox/comments/{post_id}/{comment_id}/private-reply`, corpo
    `{"accountId", "message"}` e `message` uguale al letterale del contract §6 «Per ricevere la tua carta scrivici
    CARTA qui in chat» (scritto a mano, senza punto finale, non costruito con
    `build_comment_card_invite_text`); nessun `Idempotency-Key` (contract §7: la risposta privata non lo usa);
    esito SENT sulla riga di dedup. Gli effetti che NON devono esserci: nessuna riga `Card` (il commento non crea la
    carta, la crea il DM) e tutti i contatori della campagna ancora a (0, 0, 0): `CARTA` non e' una richiesta di
    campagna, e una campagna con limite e' presente per provare che neppure lei viene toccata. Lo stato si imposta
    con `merchant_crud.update_merchant` (contract §11); il negozio resta collegato a Zernio in tutti i casi.
    """
    from app.services.db_crud import merchant_crud

    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
        request_limit=5,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id

    if stato == "in_attesa":
        merchant_crud.update_merchant(session, instagram_merchant, {"is_approved": False})
    elif stato == "in_pausa":
        merchant_crud.update_merchant(session, instagram_merchant, {"is_paused": True})

    event_id = f"evt-ac16-{stato}"
    response = signed_webhook(
        client, instagram_merchant, _comment_payload(settings.INSTAGRAM_CARD_KEYWORD, event_id=event_id),
    )

    assert response.status_code == 200
    atteso = f"Per ricevere la tua carta scrivici {settings.INSTAGRAM_CARD_KEYWORD} qui in chat"
    assert len(zernio_mock.requests) == 1
    request = zernio_mock.requests[0]
    assert request.url.path == f"/api/v1/inbox/comments/{POST_ID}/{COMMENT_ID}/private-reply"
    assert "Idempotency-Key" not in request.headers
    body = zernio_mock.bodies()[0]
    assert body == {"accountId": INSTAGRAM_ACCOUNT_ID, "message": atteso}

    session.expire_all()
    assert session.get(ProcessedWebhookEvent, event_id).outcome == WebhookOutcome.SENT
    assert list(session.exec(select(Card))) == []
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (0, 0, 0)


def test_commento_con_parola_di_campagna_riceve_la_promo_in_risposta_privata_e_conta_come_commento(
    client, session, instagram_merchant, zernio_mock,
):
    """
    AC-15 (con AC-14): il commento «Black-Friday!» a un negozio attivo con la campagna `black-friday` e' riconosciuto
    come lo sarebbe un DM (AC-14: corrispondenza esatta sul testo normalizzato, «black friday» contro «black
    friday»). Il valore atteso e' quindi: esito SENT; UNA sola richiesta a Zernio, sul percorso della risposta privata
    al commento giusto (mai una risposta pubblica, che avrebbe un altro percorso o sarebbe una seconda richiesta);
    corpo `{"accountId", "message"}` con `message` uguale al testo di AC-10 (promo + riga vuota + pie' di pagina del
    contract §4, scritto a mano e non costruito con `build_promo_text`; il limite di 5 non e' superato, quindi non
    e' il testo «offerte terminate» di AC-11). Contatori: `comment_requests` passa da 0 a 1 e `dm_requests` resta a 0
    (il canale e' il commento, contract §3), `uses` a 0. Nessuna riga `Card`: la richiesta di campagna non crea
    la carta.
    """
    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
        request_limit=5,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id

    response = signed_webhook(
        client, instagram_merchant, _comment_payload("Black-Friday!", event_id="evt-ac15-1"),
    )

    assert response.status_code == 200
    # Testo atteso scritto a mano dal contract §4 (byte per byte), con la parola della carta delle impostazioni.
    atteso = (
        PROMO_TEXT + "\n\n"
        "Per utilizzare questa offerta devi avere la nostra carta fedeltà. "
        f"Se non l'hai ricevuta o non la ritrovi nella chat scrivi {settings.INSTAGRAM_CARD_KEYWORD}."
    )
    assert len(zernio_mock.requests) == 1
    request = zernio_mock.requests[0]
    assert request.url.path == f"/api/v1/inbox/comments/{POST_ID}/{COMMENT_ID}/private-reply"
    assert zernio_mock.bodies()[0] == {"accountId": INSTAGRAM_ACCOUNT_ID, "message": atteso}

    session.expire_all()
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (0, 1, 0)
    assert session.get(ProcessedWebhookEvent, "evt-ac15-1").outcome == WebhookOutcome.SENT
    assert list(session.exec(select(Card))) == []


@pytest.mark.parametrize(
    "caso, testo, archiviata, stato",
    [
        ("senza_parola_esatta", "Black Friday 2026", False, "attivo"),
        ("campagna_archiviata", "black-friday", True, "attivo"),
        ("negozio_in_attesa", "black-friday", False, "in_attesa"),
        ("negozio_in_pausa", "black-friday", False, "in_pausa"),
    ],
)
def test_commento_che_non_attiva_nessuna_campagna_e_ignorato_senza_invio_ne_contatori(
    client, session, instagram_merchant, zernio_mock, caso, testo, archiviata, stato,
):
    """
    AC-17: in nessuno dei quattro casi parte una richiesta a Zernio, nessun contatore della campagna si muove e
    l'esito sulla riga di dedup e' IGNORED. I casi: (1) il commento contiene la parola ma non e' uguale ad essa dopo
    la normalizzazione («black friday 2026» contro «black friday»: la corrispondenza e' esatta, non per
    sottostringa); (2) la parola e' esatta ma la campagna e' archiviata, quindi fuori dal confronto; (3) e (4) la
    parola e' esatta e la campagna attiva, ma il negozio e' in attesa o in pausa e non puo' rispondere con offerte
    (contract §5: negozio non ACTIVE -> `None`, niente contato). Il valore atteso dei contatori e' (0, 0, 0)
    perche' il criterio dice «nessun contatore»: la campagna ha un limite e il commento non deve consumarlo. Nessuna
    riga `Card` (il commento non crea carte). Lo stato si imposta con `merchant_crud.update_merchant` (contract §11).
    """
    from app.services.db_crud import merchant_crud

    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
        request_limit=5, is_archived=archiviata,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id

    if stato == "in_attesa":
        merchant_crud.update_merchant(session, instagram_merchant, {"is_approved": False})
    elif stato == "in_pausa":
        merchant_crud.update_merchant(session, instagram_merchant, {"is_paused": True})

    event_id = f"evt-ac17-{caso}"
    response = signed_webhook(client, instagram_merchant, _comment_payload(testo, event_id=event_id))

    assert response.status_code == 200
    assert zernio_mock.requests == []

    session.expire_all()
    assert session.get(ProcessedWebhookEvent, event_id).outcome == WebhookOutcome.IGNORED
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (0, 0, 0)
    assert list(session.exec(select(Card))) == []


@pytest.mark.parametrize(
    "caso, risposta, esito_atteso, quota_attesa, stato_atteso",
    [
        ("gia_usata_400", httpx.Response(400, json={"error": "x", "details": {"privateReplyConsumed": True}}),
         WebhookOutcome.SEND_FAILED, [], InstagramStatus.ACTIVE),
        ("rifiuto_meta_403", httpx.Response(403, json={"error": "x", "code": "platform_api_error"}),
         WebhookOutcome.SEND_FAILED, [], InstagramStatus.ACTIVE),
        ("errore_500", httpx.Response(500, json={"error": "x", "code": "internal_error"}),
         WebhookOutcome.SEND_FAILED, [], InstagramStatus.ACTIVE),
        ("non_thread_owner_409", httpx.Response(409, json={"error": "x", "code": "not_thread_owner"}),
         WebhookOutcome.SEND_FAILED, [], InstagramStatus.ACTIVE),
        ("chiave_rifiutata_401", httpx.Response(401, json={"error": "x", "code": "invalid_credentials"}),
         WebhookOutcome.SEND_FAILED, [], InstagramStatus.KEY_INVALID),
        ("timeout", httpx.ReadTimeout("lento"),
         WebhookOutcome.SEND_UNCERTAIN, [1], InstagramStatus.ACTIVE),
        ("502_esito_sconosciuto", httpx.Response(502, json={"details": {"privateReplyOutcome": "unknown"}}),
         WebhookOutcome.SEND_UNCERTAIN, [1], InstagramStatus.ACTIVE),
    ],
)
def test_errore_della_risposta_privata_un_solo_tentativo_esito_giusto_e_richiesta_contata(
    client, session, instagram_merchant, zernio_mock, caso, risposta, esito_atteso, quota_attesa, stato_atteso,
):
    """
    AC-18 (contract §6 punto 5): quando la risposta privata a una richiesta di campagna fallisce, la risposta HTTP e'
    comunque 200 e parte UNA sola richiesta a Zernio (nessun nuovo tentativo). L'esito sulla riga di dedup e'
    SEND_FAILED per ogni errore certo: risposta gia' usata (400 `privateReplyConsumed`), rifiuto di Meta (403), 5xx
    (500), conversazione di un'altra app (409 `not_thread_owner`, che sui DM varrebbe STANDBY ma qui NON deve
    esserlo: `standby_detected_at` resta vuoto) e chiave rifiutata (401, che in piu' porta il negozio a
    KEY_INVALID; in tutti gli altri casi resta ACTIVE). E' SEND_UNCERTAIN per timeout e per 502 con
    `privateReplyOutcome: unknown`, perche' il messaggio potrebbe essere partito: in questi due casi la quota di invii
    Zernio sale a 1 (letterale: un solo invio possibile) e il negozio, gia' attivo, non cambia stato; per gli errori
    certi non c'e' nessun invio da contare (lista vuota). In ogni caso `comment_requests` vale 1: la richiesta di
    campagna e' contata al riconoscimento, prima dell'invio, e un errore non la annulla (`dm_requests` e `uses` a 0).
    """
    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
        request_limit=5,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id
    zernio_mock.queue(risposta)

    event_id = f"evt-ac18-{caso}"
    response = signed_webhook(client, instagram_merchant, _comment_payload("black-friday", event_id=event_id))

    assert response.status_code == 200
    assert len(zernio_mock.requests) == 1
    assert zernio_mock.requests[0].url.path == f"/api/v1/inbox/comments/{POST_ID}/{COMMENT_ID}/private-reply"

    session.expire_all()
    assert session.get(ProcessedWebhookEvent, event_id).outcome == esito_atteso
    assert [c.sent for c in session.exec(select(ZernioSendCounter))] == quota_attesa
    session.refresh(instagram_merchant)
    assert instagram_merchant.instagram_status == stato_atteso
    assert instagram_merchant.standby_detected_at is None
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (0, 1, 0)


def test_risposta_privata_riuscita_conta_nella_quota_come_un_dm_e_attiva_il_negozio_in_attesa_del_dm_di_prova(
    client, session, instagram_merchant, zernio_mock,
):
    """
    AC-19: una risposta privata riuscita conta nella quota di invii Zernio come un DM (D5, contract §6 punto 4:
    `SENT` e `_record_send`). Il negozio parte in AWAITING_TEST_DM; il primo commento e' `CARTA` (l'invito parte in
    ogni stato, D7) ed e' riuscito: dopo di esso il contatore del mese per l'ambito `account:<id>` (il negozio non ha
    team, come nei test dei DM) vale 1 e il negozio e' passato a ACTIVE, come con il primo DM riuscito. Il secondo
    commento ha un evento diverso e porta la parola di campagna: anch'esso riuscito, quindi il contatore sale a 2
    (un invio per ogni risposta privata, non uno per commento riconosciuto ne' uno per campagna). Il valore 2 e'
    scritto a mano: due risposte private riuscite, due invii. Resta una sola riga di contatore, quella del mese
    corrente, con l'ambito dell'account.
    """
    from datetime import datetime, timezone

    instagram_merchant.instagram_status = InstagramStatus.AWAITING_TEST_DM
    session.add(instagram_merchant)
    session.add(Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
        request_limit=5,
    ))
    session.commit()

    response = signed_webhook(
        client, instagram_merchant, _comment_payload(settings.INSTAGRAM_CARD_KEYWORD, event_id="evt-ac19-carta"),
    )
    assert response.status_code == 200
    session.expire_all()
    session.refresh(instagram_merchant)
    assert instagram_merchant.instagram_status == InstagramStatus.ACTIVE
    assert [c.sent for c in session.exec(select(ZernioSendCounter))] == [1]

    response = signed_webhook(
        client, instagram_merchant, _comment_payload("black-friday", event_id="evt-ac19-campagna"),
    )
    assert response.status_code == 200
    assert len(zernio_mock.requests) == 2

    session.expire_all()
    contatori = list(session.exec(select(ZernioSendCounter)))
    assert [(c.quota_scope, c.period, c.sent) for c in contatori] == [
        (f"account:{INSTAGRAM_ACCOUNT_ID}", datetime.now(timezone.utc).strftime("%Y-%m"), 2),
    ]


def test_commento_ripetuto_con_lo_stesso_evento_non_invia_ne_conta_due_volte_e_firma_errata_401(
    client, session, instagram_merchant, zernio_mock,
):
    """
    AC-14: `comment.received` passa dalla stessa route, con la stessa firma e la stessa dedup dei DM. Valori attesi:
    (1) lo STESSO evento (stesso `id`, quindi stesso `X-Zernio-Event-Id`) inviato due volte risponde 200 entrambe le
    volte, ma parte UNA sola risposta privata a Zernio e `comment_requests` vale 1, non 2 (un evento ripetuto non
    invia e non conta, contract §6): 1 e' il letterale di una sola richiesta di campagna reale, scritto a mano;
    (2) lo stesso commento con firma sbagliata e un evento nuovo risponde 401 e non produce nessun invio ne'
    alcun conteggio: i totali restano quelli di prima (1 richiesta a Zernio, `comment_requests` a 1).
    """
    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
        request_limit=5,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id

    payload = _comment_payload("black-friday", event_id="evt-ac14-dup")
    assert signed_webhook(client, instagram_merchant, payload).status_code == 200
    assert signed_webhook(client, instagram_merchant, payload).status_code == 200

    assert len(zernio_mock.requests) == 1
    session.expire_all()
    assert session.get(Campaign, campaign_id).comment_requests == 1

    firma_errata = signed_webhook(
        client, instagram_merchant, _comment_payload("black-friday", event_id="evt-ac14-firma"),
        signature="0" * 64,
    )

    assert firma_errata.status_code == 401
    assert len(zernio_mock.requests) == 1
    session.expire_all()
    assert session.get(Campaign, campaign_id).comment_requests == 1


def test_risposta_a_un_altro_commento_vale_come_un_commento_normale(
    client, session, instagram_merchant, zernio_mock,
):
    """
    AC-14: un commento che e' una risposta a un altro commento (payload con `parentId` e `isReply`, campi che il
    contract §6 non legge: «nessun altro campo letto») vale come un commento normale. Valori attesi, identici a quelli
    del commento semplice di AC-15: UNA risposta privata al commento `COMMENT_ID` del post `POST_ID` (non al commento
    padre), `comment_requests` a 1 e `dm_requests` a 0, esito SENT. Il letterale 1 e' una sola richiesta di campagna.
    """
    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
        request_limit=5,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id

    payload = _comment_payload("black-friday", event_id="evt-ac14-reply")
    payload["comment"]["parentId"] = "c_padre"
    payload["comment"]["isReply"] = True

    assert signed_webhook(client, instagram_merchant, payload).status_code == 200

    assert len(zernio_mock.requests) == 1
    assert zernio_mock.requests[0].url.path == f"/api/v1/inbox/comments/{POST_ID}/{COMMENT_ID}/private-reply"
    session.expire_all()
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (0, 1, 0)
    assert session.get(ProcessedWebhookEvent, "evt-ac14-reply").outcome == WebhookOutcome.SENT
