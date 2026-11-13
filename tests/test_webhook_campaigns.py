"""
Test del webhook Zernio per le campagne (v0.4.1, ticket 03, AC-09..13).

SQLite in-memory + `MockTransport` (fixture `zernio_mock`): nessuna rete. Si entra dal confine pubblico, cioe'
`POST /webhooks/zernio/{hook_id}` firmato, e si legge la riga `campaign` e la richiesta inviata a Zernio.
"""

from datetime import timedelta

import httpx
import pytest

from sqlmodel import select

from app.core.clock import utc_now
from app.core.config import settings
from app.core.enums import InstagramStatus, WebhookOutcome
from app.models.models import Campaign, Card, PointTransaction, ProcessedWebhookEvent, ZernioSendCounter
from tests.conftest import INSTAGRAM_ACCOUNT_ID, signed_webhook

CONVERSATION = "conv-handle-42"
PROMO_TEXT = "Black Friday: un caffe' in omaggio con la tua carta."


def _dm_payload(text: str, event_id: str = "evt-bf-1") -> dict:
    """`message.received` di un DM di testo (cliente che scrive `text`), inviato un minuto fa (finestra di 24 h aperta)."""
    sent_at = (utc_now() - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    return {
        "id": event_id,
        "event": "message.received",
        "message": {
            "id": "m-in-1", "conversationId": CONVERSATION, "platform": "instagram", "direction": "incoming",
            "text": text, "attachments": [],
            "sender": {"id": "igsid-cliente-1", "name": "Mario Rossi", "username": "mario.rossi"},
            "sentAt": sent_at,
        },
        "conversation": {"id": CONVERSATION, "platformConversationId": "igsid-cliente-1", "status": "active"},
        "account": {"id": INSTAGRAM_ACCOUNT_ID, "accountId": INSTAGRAM_ACCOUNT_ID, "platform": "instagram"},
        "metadata": {},
        "timestamp": sent_at,
        "test": False,
    }


def test_dm_con_parola_chiave_scritta_diversamente_invia_la_promo_e_conta_una_richiesta(
    client, session, instagram_merchant, zernio_mock,
):
    """
    AC-09: il DM «Black-Friday!» a un negozio attivo con la campagna `black-friday` e' riconosciuto (il testo
    normalizzato, «black friday», e' esattamente la parola chiave normalizzata, «black friday»). Il valore atteso e'
    quindi: esito SENT; UN solo invio di testo nella conversazione del cliente, con il testo della promo seguito dal
    pie' di pagina fisso (letterale del contract §4, con la parola della carta); `dm_requests` passa da 0 a 1 e gli
    altri contatori restano a 0 (e' un DM, non un commento, e nessuno ha ancora premuto «Applica»). Il flusso
    delle campagne non crea alcuna carta (contract §6, punto 4): la parola chiave non e' `CARTA`.
    """
    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id

    response = signed_webhook(client, instagram_merchant, _dm_payload("Black-Friday!"))

    assert response.status_code == 200
    # Testo atteso scritto a mano dal contract (byte per byte), non costruito con build_promo_text.
    atteso = (
        PROMO_TEXT + "\n\n"
        "Per utilizzare questa offerta devi avere la nostra carta fedeltà. "
        f"Se non l'hai ricevuta o non la ritrovi nella chat scrivi {settings.INSTAGRAM_CARD_KEYWORD}."
    )
    assert len(zernio_mock.requests) == 1
    request = zernio_mock.requests[0]
    assert request.url.path == f"/api/v1/inbox/conversations/{CONVERSATION}/messages"
    assert request.headers["Idempotency-Key"] == "evt-bf-1:promo"
    body = zernio_mock.bodies()[0]
    assert body["accountId"] == INSTAGRAM_ACCOUNT_ID
    assert body["message"] == atteso

    session.expire_all()
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (1, 0, 0)
    assert session.get(ProcessedWebhookEvent, "evt-bf-1").outcome == WebhookOutcome.SENT
    assert list(session.exec(select(Card))) == []


@pytest.mark.parametrize("testo", ["Black-Friday!", "black friday", "BLACK-FRIDAY 🎄"])
def test_dm_con_varianti_di_maiuscole_punteggiatura_ed_emoji_riconosce_la_campagna(
    client, session, instagram_merchant, zernio_mock, testo,
):
    """
    AC-09: con la campagna `black-friday` scattano tutte le varianti che, dopo la normalizzazione (minuscole,
    punteggiatura ed emoji diventano spazi, spazi compattati), valgono «black friday»: «Black-Friday!»,
    «black friday» e «BLACK-FRIDAY 🎄». Il valore atteso (esempi del contract §2, scritti a mano) e' quindi: esito
    SENT, UN solo invio a Zernio e `dm_requests` a 1, con gli altri contatori a 0.
    """
    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id

    response = signed_webhook(client, instagram_merchant, _dm_payload(testo, event_id="evt-bf-var"))

    assert response.status_code == 200
    assert len(zernio_mock.requests) == 1
    session.expire_all()
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (1, 0, 0)
    assert session.get(ProcessedWebhookEvent, "evt-bf-var").outcome == WebhookOutcome.SENT


@pytest.mark.parametrize("testo", ["blackfriday", "black friday per me"])
def test_dm_che_non_coincide_per_intero_con_la_parola_chiave_non_scatta(
    client, session, instagram_merchant, zernio_mock, testo,
):
    """
    AC-09: con la campagna `black-friday` NON scattano «blackfriday» (normalizzato resta «blackfriday», senza lo
    spazio, quindi diverso da «black friday») e «black friday per me» (contiene la parola ma non coincide per
    intero: il confronto e' di uguaglianza, non di sottostringa). Il valore atteso e' quindi: esito IGNORED,
    nessuna richiesta a Zernio e tutti i contatori della campagna a 0 (la richiesta non e' stata riconosciuta, quindi
    non e' contata).
    """
    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id

    response = signed_webhook(client, instagram_merchant, _dm_payload(testo, event_id="evt-bf-neg"))

    assert response.status_code == 200
    assert zernio_mock.requests == []
    session.expire_all()
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (0, 0, 0)
    assert session.get(ProcessedWebhookEvent, "evt-bf-neg").outcome == WebhookOutcome.IGNORED


def test_dm_con_parola_in_una_campagna_archiviata_e_in_una_non_archiviata_usa_solo_la_non_archiviata(
    client, session, instagram_merchant, zernio_mock,
):
    """
    AC-09: con la parola `NATALE` presente sia in una campagna archiviata sia in una non archiviata dello stesso
    negozio, il DM «NATALE» risponde con la promo della NON archiviata (contract §5: il riconoscimento avviene solo
    tra le non archiviate) e incrementa solo i contatori di quella: `dm_requests` a 1, mentre la archiviata resta a
    (0, 0, 0). La archiviata e' creata col modello (aggira il conflitto di parola chiave) e con `created_at` PIU'
    RECENTE di quella attiva, cosi' un riconoscimento che ignorasse `is_archived` (ordine per `created_at`
    decrescente) sceglierebbe proprio lei e il test fallirebbe. Il testo atteso e' la promo dell'attiva seguita dal
    pie' di pagina del contract §4, scritto a mano.
    """
    promo_attiva = "Natale: un caffe' in omaggio con la tua carta."
    promo_archiviata = "Natale scorso: sconto del 10% su tutto."
    attiva = Campaign(
        merchant_id=instagram_merchant.id, name="Natale attiva", keyword="NATALE", promo_text=promo_attiva,
        created_at=utc_now() - timedelta(days=2),
    )
    archiviata = Campaign(
        merchant_id=instagram_merchant.id, name="Natale vecchia", keyword="NATALE", promo_text=promo_archiviata,
        is_archived=True, created_at=utc_now() - timedelta(days=1),
    )
    session.add(attiva)
    session.add(archiviata)
    session.commit()
    attiva_id, archiviata_id = attiva.id, archiviata.id

    response = signed_webhook(client, instagram_merchant, _dm_payload("NATALE", event_id="evt-nat-1"))

    assert response.status_code == 200
    atteso = (
        promo_attiva + "\n\n"
        "Per utilizzare questa offerta devi avere la nostra carta fedeltà. "
        f"Se non l'hai ricevuta o non la ritrovi nella chat scrivi {settings.INSTAGRAM_CARD_KEYWORD}."
    )
    assert len(zernio_mock.requests) == 1
    assert zernio_mock.bodies()[0]["message"] == atteso

    session.expire_all()
    stored_attiva = session.get(Campaign, attiva_id)
    stored_archiviata = session.get(Campaign, archiviata_id)
    assert (stored_attiva.dm_requests, stored_attiva.comment_requests, stored_attiva.uses) == (1, 0, 0)
    assert (stored_archiviata.dm_requests, stored_archiviata.comment_requests, stored_archiviata.uses) == (0, 0, 0)
    assert session.get(ProcessedWebhookEvent, "evt-nat-1").outcome == WebhookOutcome.SENT


def test_risposta_a_una_storia_segue_lo_stesso_riconoscimento_di_un_dm(
    client, session, instagram_merchant, zernio_mock,
):
    """
    AC-09: una risposta a una storia (`message.received` con `metadata.storyReply` e il testo in `message.text`)
    con la campagna attiva `natale` e il testo «Natale!» si legge come un DM di testo (contract §6). Il valore
    atteso e' quindi: esito SENT; UN solo invio di testo nella conversazione del cliente, con
    `Idempotency-Key` `<event_id>:promo` e il corpo «promo + pie' di pagina» scritto a mano dal contract §4; e
    `dm_requests` a 1 (le risposte alle storie contano come DM, contract §3), con `comment_requests` e `uses` a 0.
    Nessuna carta viene creata: la parola non e' `CARTA`.
    """
    promo = "Natale: un caffe' in omaggio con la tua carta."
    campaign = Campaign(merchant_id=instagram_merchant.id, name="Natale", keyword="natale", promo_text=promo)
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id

    payload = _dm_payload("Natale!", event_id="evt-story-1")
    payload["metadata"] = {"storyReply": {"storyId": "s_1", "storyUrl": "https://example.com/story/s_1"}}

    response = signed_webhook(client, instagram_merchant, payload)

    assert response.status_code == 200
    atteso = (
        promo + "\n\n"
        "Per utilizzare questa offerta devi avere la nostra carta fedeltà. "
        f"Se non l'hai ricevuta o non la ritrovi nella chat scrivi {settings.INSTAGRAM_CARD_KEYWORD}."
    )
    assert len(zernio_mock.requests) == 1
    request = zernio_mock.requests[0]
    assert request.url.path == f"/api/v1/inbox/conversations/{CONVERSATION}/messages"
    assert request.headers["Idempotency-Key"] == "evt-story-1:promo"
    assert zernio_mock.bodies()[0]["message"] == atteso

    session.expire_all()
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (1, 0, 0)
    assert session.get(ProcessedWebhookEvent, "evt-story-1").outcome == WebhookOutcome.SENT
    assert list(session.exec(select(Card))) == []


def test_dm_di_chi_non_segue_riceve_un_solo_invio_di_testo_identico_a_quello_di_un_follower(
    client, session, instagram_merchant, zernio_mock,
):
    """
    AC-10: il DM con la parola della campagna inviato da un mittente con `instagramProfile.isFollower` falso
    produce UN solo invio di testo, senza invito a seguire e senza card, e il testo e' quello che riceverebbe
    un follower: promo + riga vuota + riga fissa del contract §4 (`isFollower` e' ignorato nel flusso delle
    campagne, contract §6 punto 4). Il testo atteso e' scritto a mano dal contract, non costruito con
    `build_promo_text`. Gli effetti che NON devono esserci: nessuna riga `Card` e nessuna `PointTransaction`
    (nessuna carta creata o modificata, nessun tree point, nessun cashback). `dm_requests` passa da 0 a 1 (la
    richiesta e' sotto il limite: 1 <= 5), con `comment_requests` e `uses` a 0; l'esito e' SENT.
    """
    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
        request_limit=5,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id

    payload = _dm_payload("Black-Friday!", event_id="evt-nofollow-1")
    payload["message"]["sender"]["instagramProfile"] = {"isFollower": False}

    response = signed_webhook(client, instagram_merchant, payload)

    assert response.status_code == 200
    atteso = (
        PROMO_TEXT + "\n\n"
        "Per utilizzare questa offerta devi avere la nostra carta fedeltà. "
        f"Se non l'hai ricevuta o non la ritrovi nella chat scrivi {settings.INSTAGRAM_CARD_KEYWORD}."
    )
    # Un solo invio: niente invito a seguire, niente card (che sarebbero richieste aggiuntive a Zernio).
    assert len(zernio_mock.requests) == 1
    request = zernio_mock.requests[0]
    assert request.url.path == f"/api/v1/inbox/conversations/{CONVERSATION}/messages"
    assert request.headers["Idempotency-Key"] == "evt-nofollow-1:promo"
    assert zernio_mock.bodies()[0]["message"] == atteso

    session.expire_all()
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (1, 0, 0)
    assert session.get(ProcessedWebhookEvent, "evt-nofollow-1").outcome == WebhookOutcome.SENT
    assert list(session.exec(select(Card))) == []
    assert list(session.exec(select(PointTransaction))) == []


@pytest.mark.parametrize("scenario", ["campagna_archiviata", "negozio_in_attesa", "negozio_in_pausa"])
def test_parola_di_campagna_archiviata_o_di_negozio_non_attivo_e_ignorata_senza_contare(
    client, session, instagram_merchant, zernio_mock, scenario,
):
    """
    AC-12: il DM con la parola della campagna produce esito IGNORED, nessuna richiesta a Zernio e tutti i
    contatori della campagna ancora a (0, 0, 0) in tre scenari: (a) campagna archiviata su negozio attivo (il
    riconoscimento avviene solo tra le non archiviate, contract §5); (b) campagna non archiviata su negozio in
    attesa (non approvato) e (c) su negozio in pausa (`is_paused=True`): con il negozio non ACTIVE
    `handle_campaign_request` risponde `None` PRIMA di contare (contract §5, AC-12/AC-17). Il valore atteso e'
    zero ovunque perche' il criterio vieta sia l'invio sia l'incremento: un'implementazione che contasse e poi
    tacesse avrebbe `dm_requests` a 1 e il test fallirebbe. Il negozio resta collegato a Zernio (account e hook)
    in tutti gli scenari, quindi il webhook risponde 200 e non 404 per un altro motivo. Lo stato si imposta con
    `merchant_crud.update_merchant` (contract §11), non scrivendo i campi a mano.
    """
    from app.services.db_crud import merchant_crud

    archiviata = scenario == "campagna_archiviata"
    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
        is_archived=archiviata,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id

    if scenario == "negozio_in_attesa":
        merchant_crud.update_merchant(session, instagram_merchant, {"is_approved": False})
    elif scenario == "negozio_in_pausa":
        merchant_crud.update_merchant(session, instagram_merchant, {"is_paused": True})

    event_id = f"evt-ac12-{scenario}"
    response = signed_webhook(client, instagram_merchant, _dm_payload("Black-Friday!", event_id=event_id))

    assert response.status_code == 200
    assert zernio_mock.requests == []
    session.expire_all()
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (0, 0, 0)
    assert session.get(ProcessedWebhookEvent, event_id).outcome == WebhookOutcome.IGNORED


def test_dm_oltre_il_limite_riceve_offerte_terminate_ed_e_contato(
    client, session, instagram_merchant, zernio_mock,
):
    """
    AC-11: la campagna ha `request_limit=3` e ha gia' 3 richieste (2 da DM + 1 da commento, quindi il totale e'
    gia' a N). Un nuovo DM con la parola e' comunque RICONOSCIUTO e CONTATO: il totale dopo l'incremento diventa 4,
    cioe' oltre il limite (contract §4: `is_within_limit` e' `totale <= limite`, con il totale DM + commenti
    calcolato DOPO l'incremento). Il valore atteso e' quindi: esito SENT; UN solo invio di testo, con il testo
    «offerte terminate» (EXHAUSTED_TEXT del contract §4, scritto a mano byte per byte) e NON la promo; `dm_requests`
    passa da 2 a 3 (il canale DM e' incrementato) mentre `comment_requests` resta a 1 (il canale commento non e'
    toccato); `uses` resta a 0. L'invio avviene davvero (non e' un IGNORED): la richiesta e' contata e riceve la
    risposta di esaurimento.
    """
    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
        request_limit=3, dm_requests=2, comment_requests=1,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id

    response = signed_webhook(client, instagram_merchant, _dm_payload("Black-Friday!", event_id="evt-limite-1"))

    assert response.status_code == 200
    # Testo atteso scritto a mano dal contract §4, byte per byte («più» con la lettera accentata, due punti esclamativi finali).
    atteso = (
        "Le offerte disponibili sono terminate. Per essere informato più velocemente la prossima volta "
        "attiva la campanella delle notifiche al profilo!!"
    )
    assert len(zernio_mock.requests) == 1
    request = zernio_mock.requests[0]
    assert request.url.path == f"/api/v1/inbox/conversations/{CONVERSATION}/messages"
    assert request.headers["Idempotency-Key"] == "evt-limite-1:promo"
    body = zernio_mock.bodies()[0]
    assert body["accountId"] == INSTAGRAM_ACCOUNT_ID
    assert body["message"] == atteso
    assert PROMO_TEXT not in body["message"]

    session.expire_all()
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (3, 1, 0)
    assert session.get(ProcessedWebhookEvent, "evt-limite-1").outcome == WebhookOutcome.SENT


def test_dm_che_porta_il_totale_esattamente_al_limite_riceve_ancora_la_promo(
    client, session, instagram_merchant, zernio_mock,
):
    """
    AC-11 (ultimo posto): la campagna ha `request_limit=3` e ha gia' 2 richieste (1 da DM + 1 da commento). Il
    nuovo DM con la parola porta il totale DOPO l'incremento a 3, cioe' esattamente a N. Il contract §4 definisce
    `is_within_limit` come `totale <= limite`, quindi 3 e' ancora dentro il limite (con un `<` stretto il test
    fallirebbe). Il valore atteso e' quindi: esito SENT; UN solo invio di testo con la PROMO normale (testo della
    promo + riga vuota + pie' di pagina del contract §4, scritto a mano) e NON il testo «offerte terminate»;
    `dm_requests` passa da 1 a 2 (il canale DM e' incrementato), `comment_requests` resta a 1 (il canale commento
    non e' toccato) e `uses` resta a 0.
    """
    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
        request_limit=3, dm_requests=1, comment_requests=1,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id

    response = signed_webhook(client, instagram_merchant, _dm_payload("Black-Friday!", event_id="evt-ultimo-1"))

    assert response.status_code == 200
    # Testo atteso scritto a mano dal contract §4 (promo + riga vuota + pie' di pagina), non costruito con il codice.
    atteso = (
        PROMO_TEXT + "\n\n"
        "Per utilizzare questa offerta devi avere la nostra carta fedeltà. "
        f"Se non l'hai ricevuta o non la ritrovi nella chat scrivi {settings.INSTAGRAM_CARD_KEYWORD}."
    )
    assert len(zernio_mock.requests) == 1
    request = zernio_mock.requests[0]
    assert request.url.path == f"/api/v1/inbox/conversations/{CONVERSATION}/messages"
    assert request.headers["Idempotency-Key"] == "evt-ultimo-1:promo"
    body = zernio_mock.bodies()[0]
    assert body["accountId"] == INSTAGRAM_ACCOUNT_ID
    assert body["message"] == atteso
    assert "terminate" not in body["message"]

    session.expire_all()
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (2, 1, 0)
    assert session.get(ProcessedWebhookEvent, "evt-ultimo-1").outcome == WebhookOutcome.SENT


def test_evento_ripetuto_con_lo_stesso_event_id_non_invia_e_non_conta_una_seconda_volta(
    client, session, instagram_merchant, zernio_mock,
):
    """
    AC-13: lo stesso DM con la parola della campagna, consegnato due volte da Zernio con lo stesso `event_id`
    (un nuovo tentativo di consegna), viene elaborato UNA volta sola: la riga di dedup e' inserita per prima
    (contract §6) e il secondo arrivo si ferma li'. Il valore atteso e' quindi: risposta 200 a entrambe le
    consegne (la risposta HTTP e' sempre 200, anche per il duplicato: Zernio non deve ritentare ancora); in
    totale UNA sola richiesta a Zernio (quella della prima consegna, nessun secondo invio) e `dm_requests` a 1
    (il duplicato non e' contato; con un'implementazione che contasse prima della dedup varrebbe 2), con
    `comment_requests` e `uses` a 0. L'esito registrato per l'evento resta quello della prima consegna, SENT.
    """
    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id

    payload = _dm_payload("Black-Friday!", event_id="evt-dedup-1")
    prima = signed_webhook(client, instagram_merchant, payload)
    seconda = signed_webhook(client, instagram_merchant, payload)

    assert prima.status_code == 200
    assert seconda.status_code == 200
    assert len(zernio_mock.requests) == 1
    session.expire_all()
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (1, 0, 0)
    assert session.get(ProcessedWebhookEvent, "evt-dedup-1").outcome == WebhookOutcome.SENT


def test_dm_in_standby_non_invia_non_conta_ed_e_registrato_come_standby(
    client, session, instagram_merchant, zernio_mock,
):
    """
    AC-13 (standby): il DM con la parola di una campagna attiva, ma con `metadata.standby: true` (un'altra app
    possiede la conversazione), non viene gestito da noi: il contract §6 dice che il controllo di standby resta
    invariato e viene PRIMA del flusso delle campagne. Il valore atteso e' quindi: risposta 200 (sempre 200, anche
    qui); nessuna richiesta a Zernio (non si scrive in una conversazione altrui); tutti i contatori della campagna a
    (0, 0, 0) (la richiesta non e' contata: un'implementazione che riconoscesse la campagna prima di guardare lo
    standby avrebbe `dm_requests` a 1); esito `STANDBY` sulla riga di dedup (e non IGNORED o SENT). Nessuna carta
    viene creata.
    """
    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id

    payload = _dm_payload("Black-Friday!", event_id="evt-standby-1")
    payload["metadata"] = {"standby": True}

    response = signed_webhook(client, instagram_merchant, payload)

    assert response.status_code == 200
    assert zernio_mock.requests == []
    session.expire_all()
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (0, 0, 0)
    assert session.get(ProcessedWebhookEvent, "evt-standby-1").outcome == WebhookOutcome.STANDBY
    assert list(session.exec(select(Card))) == []


def test_dm_piu_vecchio_di_24_ore_non_invia_ma_la_richiesta_e_contata(
    client, session, instagram_merchant, zernio_mock,
):
    """
    AC-13 (finestra di 24 ore): il DM con la parola di una campagna attiva ha `sentAt` di 25 ore fa, quindi la
    finestra di risposta di Instagram e' chiusa. Il contract §6 (punto 3) dice che l'esito e' `OUT_OF_WINDOW`, che
    non si invia nulla e che la richiesta e' GIA' contata (il conteggio avviene al riconoscimento, prima del
    controllo della finestra). Il valore atteso e' quindi: risposta 200; nessuna richiesta a Zernio; esito
    `OUT_OF_WINDOW` sulla riga di dedup; `dm_requests` a 1 (contata, con un'implementazione che controllasse la
    finestra prima di riconoscere la campagna varrebbe 0), con `comment_requests` e `uses` a 0. Nessuna quota
    consumata: la quota si incrementa solo con un invio (contract §6, punto 4), quindi nessuna riga
    `ZernioSendCounter` ha `sent` maggiore di 0. Nessuna carta viene creata.
    """
    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id

    payload = _dm_payload("Black-Friday!", event_id="evt-finestra-1")
    vecchio = (utc_now() - timedelta(hours=25)).isoformat().replace("+00:00", "Z")
    payload["message"]["sentAt"] = vecchio
    payload["timestamp"] = vecchio

    response = signed_webhook(client, instagram_merchant, payload)

    assert response.status_code == 200
    assert zernio_mock.requests == []
    session.expire_all()
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (1, 0, 0)
    assert session.get(ProcessedWebhookEvent, "evt-finestra-1").outcome == WebhookOutcome.OUT_OF_WINDOW
    assert [c.sent for c in session.exec(select(ZernioSendCounter)) if c.sent] == []
    assert list(session.exec(select(Card))) == []


def test_timeout_di_lettura_e_esito_incerto_quota_contata_un_solo_tentativo_e_negozio_non_attivato(
    client, session, instagram_merchant, zernio_mock,
):
    """
    AC-13 (timeout): il negozio e' in `AWAITING_TEST_DM` e l'invio della promo va in timeout di lettura (la
    richiesta e' partita ma Zernio non ha risposto entro il tempo: il messaggio puo' essere arrivato). Il contract §6
    (punto 5) dice che l'esito e' `SEND_UNCERTAIN` e che la quota e' contata comunque. Il valore atteso e' quindi:
    risposta 200; UNA sola richiesta a Zernio (nessun nuovo tentativo: un secondo invio rischierebbe di mandare la
    promo due volte); esito `SEND_UNCERTAIN` sulla riga di dedup; una sola riga `ZernioSendCounter`, di ambito
    `account:<id>`, con `sent` a 1 (letterali scritti a mano: il messaggio puo' essere partito, quindi conta); il
    negozio NON si attiva e resta `AWAITING_TEST_DM` (l'attivazione richiede un invio certo, non un esito
    incerto); `dm_requests` a 1 (la richiesta e' stata riconosciuta e contata prima dell'invio), con
    `comment_requests` e `uses` a 0.
    """
    instagram_merchant.instagram_status = InstagramStatus.AWAITING_TEST_DM
    session.add(instagram_merchant)
    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id
    zernio_mock.queue(httpx.ReadTimeout("lento"))

    response = signed_webhook(client, instagram_merchant, _dm_payload("Black-Friday!", event_id="evt-timeout-1"))

    assert response.status_code == 200
    assert len(zernio_mock.requests) == 1
    session.expire_all()
    assert session.get(ProcessedWebhookEvent, "evt-timeout-1").outcome == WebhookOutcome.SEND_UNCERTAIN
    counters = list(session.exec(select(ZernioSendCounter)))
    assert [(c.quota_scope, c.sent) for c in counters] == [(f"account:{INSTAGRAM_ACCOUNT_ID}", 1)]
    session.refresh(instagram_merchant)
    assert instagram_merchant.instagram_status == InstagramStatus.AWAITING_TEST_DM
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (1, 0, 0)


def test_invio_riuscito_conta_la_quota_e_attiva_il_negozio_in_attesa_del_dm_di_prova(
    client, session, instagram_merchant, zernio_mock,
):
    """
    AC-13 (invio riuscito): il negozio e' in `AWAITING_TEST_DM` e la promo parte senza errori. Il contract §6
    (punto 4) dice che l'invio riuscito registra la quota (+1) e attiva il negozio. Il valore atteso e' quindi:
    risposta 200; UNA sola richiesta a Zernio; esito `SENT`; una sola riga `ZernioSendCounter`, di ambito
    `account:<id>`, con `sent` a 1 (letterali a mano, non ricalcolati); il negozio passa a `ACTIVE` (il DM
    di prova ha dimostrato che l'invio funziona).
    """
    instagram_merchant.instagram_status = InstagramStatus.AWAITING_TEST_DM
    session.add(instagram_merchant)
    session.add(Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
    ))
    session.commit()

    response = signed_webhook(client, instagram_merchant, _dm_payload("Black-Friday!", event_id="evt-ok-quota-1"))

    assert response.status_code == 200
    assert len(zernio_mock.requests) == 1
    session.expire_all()
    assert session.get(ProcessedWebhookEvent, "evt-ok-quota-1").outcome == WebhookOutcome.SENT
    counters = list(session.exec(select(ZernioSendCounter)))
    assert [(c.quota_scope, c.sent) for c in counters] == [(f"account:{INSTAGRAM_ACCOUNT_ID}", 1)]
    session.refresh(instagram_merchant)
    assert instagram_merchant.instagram_status == InstagramStatus.ACTIVE


@pytest.mark.parametrize("invio", ["riuscito", "errore_500"])
def test_log_del_dm_di_campagna_non_contengono_testi_igsid_promo_ne_segreti(
    client, session, instagram_merchant, zernio_mock, caplog, invio,
):
    """
    AC-13 (log): il webhook di un DM con la parola di una campagna, sia con invio riuscito sia con errore 500 di
    Zernio, scrive almeno una riga di log (contiene l'id dell'evento, che il contract §6 elenca tra i dati
    ammessi: cosi' il test non passa per un log vuoto) ma in NESSUNA riga, a nessun livello, compaiono: il testo
    scritto dal cliente (con un marcatore unico, anche in forma normalizzata), l'IGSID del mittente, il testo della
    promo (marcatore unico), la chiave API Zernio, il secret del webhook. Il valore atteso e' l'assenza di ciascuno
    di questi valori nel testo concatenato di tutti i record catturati (contract §6, ultimo capoverso: «mai testo,
    IGSID, chiavi, token»; §12: «nessun valore inviato e nessun segreto dentro»). Non si asserisce il testo dei
    log (non congelato). In questo flusso non nasce alcuna carta, quindi non esiste un token di link da cercare.
    """
    import logging

    from tests.conftest import WEBHOOK_TEST_SECRET, ZERNIO_TEST_KEY

    marcatore_testo = "zq81xk"
    testo_cliente = f"Natale-{marcatore_testo}!"
    promo = "Promo riservata wq47pl: un caffe' in omaggio."
    igsid = "igsid-riservato-7731905"
    event_id = f"evt-log-{invio}"
    session.add(Campaign(
        merchant_id=instagram_merchant.id, name="Natale", keyword=f"natale-{marcatore_testo}", promo_text=promo,
    ))
    session.commit()
    if invio == "errore_500":
        zernio_mock.queue(httpx.Response(500, json={"error": "testo-non-stabile", "code": "internal_error"}))

    payload = _dm_payload(testo_cliente, event_id=event_id)
    payload["message"]["sender"]["id"] = igsid
    payload["conversation"]["platformConversationId"] = igsid

    with caplog.at_level(logging.DEBUG):
        response = signed_webhook(client, instagram_merchant, payload)

    assert response.status_code == 200
    assert len(zernio_mock.requests) == 1  # l'invio e' stato davvero tentato (anche nel caso con errore)
    # Tutti i record, con messaggio formattato e (se presente) traceback, in minuscolo per il confronto.
    righe = [record.getMessage() + (record.exc_text or "") for record in caplog.records]
    log = "\n".join(righe)
    assert event_id in log
    log = log.lower()
    for valore in (
        testo_cliente, marcatore_testo, igsid, "wq47pl", promo, ZERNIO_TEST_KEY, WEBHOOK_TEST_SECRET,
    ):
        assert valore.lower() not in log, f"valore sensibile nei log: {valore!r}"


@pytest.mark.parametrize("ingresso", ["parola_carta", "voce_di_menu"])
def test_carta_e_voce_di_menu_seguono_il_flusso_di_oggi_senza_toccare_i_contatori_della_campagna(
    client, session, instagram_merchant, zernio_mock, ingresso,
):
    """
    AC-09 (CARTA invariata): con un negozio attivo e una campagna attiva con `request_limit`, un follower che scrive
    la parola della carta (`settings.INSTAGRAM_CARD_KEYWORD`) o preme la voce di menu (postback `FIDELITREE_CARD`)
    segue il flusso di oggi, invariato (contract §6, punto 1). Il valore atteso e' quindi: esito SENT; UN solo invio
    a Zernio, ma con una CARD (`template` con un bottone «Apri la carta») e non un testo di promo (nessun campo
    `message`); una riga `Card` creata per il negozio (come in `test_flusso_base_crea_la_carta_e_invia_una_card`);
    e tutti i contatori della campagna ancora a (0, 0, 0), perche' `CARTA` non e' una richiesta di campagna e non va
    contata (un'implementazione che provasse prima il riconoscimento delle campagne, o che contasse ogni DM, avrebbe
    `dm_requests` a 1). La campagna ha un limite per provare che neppure quello interferisce con la card.
    """
    campaign = Campaign(
        merchant_id=instagram_merchant.id, name="Black Friday", keyword="black-friday", promo_text=PROMO_TEXT,
        request_limit=5,
    )
    session.add(campaign)
    session.commit()
    campaign_id = campaign.id

    payload = _dm_payload(settings.INSTAGRAM_CARD_KEYWORD, event_id=f"evt-carta-{ingresso}")
    payload["message"]["sender"]["instagramProfile"] = {"isFollower": True}
    if ingresso == "voce_di_menu":
        # Il postback non ha testo: il payload sta in `metadata.postbackPayload` (come in tests/test_webhook.py).
        payload["message"]["text"] = None
        payload["metadata"] = {"postbackPayload": "FIDELITREE_CARD"}

    response = signed_webhook(client, instagram_merchant, payload)

    assert response.status_code == 200
    assert len(zernio_mock.requests) == 1
    request = zernio_mock.requests[0]
    assert request.url.path == f"/api/v1/inbox/conversations/{CONVERSATION}/messages"
    body = zernio_mock.bodies()[0]
    assert body["accountId"] == INSTAGRAM_ACCOUNT_ID
    assert "message" not in body
    assert body["template"]["elements"][0]["buttons"][0]["title"] == "Apri la carta"

    session.expire_all()
    cards = list(session.exec(select(Card)))
    assert [c.merchant_id for c in cards] == [instagram_merchant.id]
    stored = session.get(Campaign, campaign_id)
    assert (stored.dm_requests, stored.comment_requests, stored.uses) == (0, 0, 0)
    assert session.get(ProcessedWebhookEvent, f"evt-carta-{ingresso}").outcome == WebhookOutcome.SENT
