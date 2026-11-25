"""
v0.4.1, ticket 05, AC-21: le campagne nella gestione della carta del negozio.

Si testa sul confine pubblico `GET /merchant/card/{card_id}/manage` con `auth_client` (SQLite in-memory dalle
fixture di `conftest.py`). Le campagne si creano con `campaign_service` (contract §5), mai scrivendo righe a mano.
"""

import re

import pytest
from sqlmodel import select

from app.core import crypto
from app.models.models import Campaign, Card, MerchantPool, PointTransaction
from app.services import campaign_service, card_service
from app.services.db_crud import merchant_crud
from tests.conftest import make_card


def _bottone(html: str, campaign_id: int) -> str | None:
    """
    Ritorna il testo (senza spazi ai lati) del `<button>` con `data-campaign-id="<campaign_id>"`, oppure `None`
    se non esiste. L'ordine degli attributi dentro il tag non è congelato dal contract: si accetta qualunque.
    """
    trovato = re.search(
        r'<button\b[^>]*\bdata-campaign-id="' + str(campaign_id) + r'"[^>]*>(.*?)</button>',
        html,
        flags=re.DOTALL,
    )
    return trovato.group(1).strip() if trovato else None


def test_gestione_carta_mostra_solo_le_campagne_non_archiviate_con_la_loro_etichetta(
    session, merchant, card, auth_client
):
    """
    AC-21: con un negozio attivo la pagina di gestione della carta contiene il blocco `id="campaigns-section"` e
    un bottone `data-campaign-id` per ogni campagna NON archiviata, con l'etichetta del contract §4
    (`scanner_label`): «Applica <nome> (+X €)» se c'è un importo, «Applica <nome>» se l'importo è 0. La campagna
    archiviata non compare: né il suo bottone né il suo nome.

    I valori attesi sono letterali scritti a mano dal contract, non calcolati: 2,50 € → «+2,50 €» (due decimali,
    virgola decimale, spazio prima del simbolo dell'euro).
    """
    con_importo = campaign_service.create_campaign(session, merchant, {
        "name": "Natale", "keyword": "NATALE26", "promo_text": "Sconto di Natale", "value_eur": 2.5,
    })
    senza_importo = campaign_service.create_campaign(session, merchant, {
        "name": "Estate", "keyword": "ESTATE26", "promo_text": "Sconto estivo", "value_eur": 0,
    })
    archiviata = campaign_service.create_campaign(session, merchant, {
        "name": "Pasqua", "keyword": "PASQUA26", "promo_text": "Sconto pasquale", "value_eur": 1,
    })
    campaign_service.archive_campaign(session, merchant, archiviata.id)

    resp = auth_client.get(f"/merchant/card/{card.id}/manage")

    assert resp.status_code == 200
    html = resp.text
    assert 'id="campaigns-section"' in html
    assert _bottone(html, con_importo.id) == "Applica Natale (+2,50 €)"
    assert _bottone(html, senza_importo.id) == "Applica Estate"
    # La campagna archiviata non ha bottone e il suo nome non compare da nessuna parte nella pagina.
    assert _bottone(html, archiviata.id) is None
    assert "Pasqua" not in html


def test_applica_campagna_confermata_accredita_l_importo_attuale_e_conta_un_utilizzo(
    session, merchant, card, auth_client
):
    """
    AC-23: con un negozio attivo, «Applica» confermato (`POST .../campaigns/{id}/apply`) risponde 200 e
    accredita sulla carta l'importo ATTUALE della campagna, sommato al cashback che la carta aveva già, e
    incrementa di 1 gli utilizzi (`uses`) della campagna. La risposta riporta `applied_cashback` (l'importo
    accreditato, in euro) e il cashback aggiornato della carta (`card.cashback_point`, in euro); gli stessi valori
    sono nel DB.

    Valori scelti non banali per distinguere un «+ importo» da un valore sbagliato: cashback iniziale 3,70 € (370
    centesimi) e importo della campagna 1,35 € (135 centesimi). Il valore atteso è scritto a mano: 370 + 135 = 505
    centesimi = 5,05 €, non 1,35 € (cashback sovrascritto) né 3,70 € (nessun accredito). `uses` parte da 0 e deve
    diventare esattamente 1.
    """
    campagna = campaign_service.create_campaign(session, merchant, {
        "name": "Natale", "keyword": "NATALE26", "promo_text": "Sconto di Natale", "value_eur": 1.35,
    })
    # Cashback iniziale della carta: 3,70 € (centesimi interi, come nel DB).
    card.cashback_cents = 370
    session.add(card)
    session.commit()
    assert campagna.uses == 0

    resp = auth_client.post(f"/api/merchant/card/{card.id}/campaigns/{campagna.id}/apply")

    assert resp.status_code == 200
    body = resp.json()
    assert body["applied_cashback"] == 1.35
    assert body["card"]["cashback_point"] == 5.05
    # Stato nel DB: si rilegge dalla sessione, scartando gli oggetti già in cache.
    session.expire_all()
    assert session.get(type(card), card.id).cashback_cents == 505
    assert session.get(Campaign, campagna.id).uses == 1


@pytest.mark.parametrize("stato_non_attivo", [{"is_approved": False}, {"is_paused": True}], ids=["attesa", "pausa"])
def test_applica_campagna_con_importo_su_negozio_non_attivo_risponde_403_senza_scrivere(
    session, merchant, card, auth_client, stato_non_attivo
):
    """
    AC-24 (parte API): se il negozio non è attivo (in attesa di approvazione o in pausa) e l'importo della campagna
    è > 0, `POST .../campaigns/{id}/apply` risponde 403 PRIMA di scrivere: il cashback della carta e gli utilizzi
    (`uses`) della campagna restano quelli di partenza. È lo stesso controllo dell'aggiunta di cashback di oggi.

    La campagna si crea a negozio attivo (un negozio non attivo non può avere campagne non archiviate) e solo dopo
    si cambia lo stato del negozio. Valori scelti a mano: cashback iniziale 3,70 € = 370 centesimi, importo 1,35 €;
    dopo la 403 devono restare esattamente 370 centesimi e `uses` = 0 (non 505 né 1: nessun UPDATE, nemmeno parziale).
    """
    campagna = campaign_service.create_campaign(session, merchant, {
        "name": "Natale", "keyword": "NATALE26", "promo_text": "Sconto di Natale", "value_eur": 1.35,
    })
    campagna_id = campagna.id
    card.cashback_cents = 370
    session.add(card)
    session.commit()
    # Il negozio esce dallo stato attivo dopo la creazione della campagna.
    merchant_crud.update_merchant(session, merchant, stato_non_attivo)

    resp = auth_client.post(f"/api/merchant/card/{card.id}/campaigns/{campagna_id}/apply")

    assert resp.status_code == 403
    # Stato nel DB: si rilegge dalla sessione, scartando gli oggetti già in cache.
    session.expire_all()
    assert session.get(type(card), card.id).cashback_cents == 370
    assert session.get(Campaign, campagna_id).uses == 0


@pytest.mark.parametrize("caso", ["campagna_altrui", "carta_altrui", "campagna_inesistente"])
def test_applica_campagna_con_carta_o_campagna_non_del_negozio_risponde_404_senza_scrivere(
    session, merchant, card, auth_client, caso
):
    """
    AC-25 (parte 404): se la carta o la campagna non esistono o appartengono a un altro negozio,
    `POST .../campaigns/{id}/apply` risponde 404 e non scrive niente: il cashback della carta (quella del
    negozio che chiama) e gli utilizzi (`uses`) della campagna coinvolta restano quelli di partenza. Tre casi:
    (a) campagna di un ALTRO negozio applicata a una propria carta; (b) carta di un altro negozio con una
    campagna propria; (c) campagna inesistente.

    Valori scelti a mano: cashback iniziale 3,70 € = 370 centesimi su entrambe le carte e `uses` = 0. Dopo il 404
    devono restare esattamente 370 e 0 (non 505 né 1: nessun UPDATE, nemmeno parziale). Nel caso (c) non c'è
    nessuna campagna da rileggere, quindi si verifica solo la carta.
    """
    altro = merchant_crud.create_merchant(session, {
        "business_name": "Altro Negozio",
        "email": "altro@test.it",
        "contact_phone": "+393339876543",
        "is_approved": True,
    })
    campagna_propria = campaign_service.create_campaign(session, merchant, {
        "name": "Natale", "keyword": "NATALE26", "promo_text": "Sconto di Natale", "value_eur": 1.35,
    })
    campagna_altrui = campaign_service.create_campaign(session, altro, {
        "name": "Estate", "keyword": "ESTATE26", "promo_text": "Sconto estivo", "value_eur": 1.35,
    })
    carta_altrui = make_card(session, altro, igsid="igsid-altro-1")
    card.cashback_cents = 370
    carta_altrui.cashback_cents = 370
    session.add(card)
    session.add(carta_altrui)
    session.commit()

    # Id estratti prima della richiesta: dopo la chiamata gli oggetti in sessione possono essere scaduti.
    carta_id, carta_altrui_id = card.id, carta_altrui.id
    propria_id, altrui_id = campagna_propria.id, campagna_altrui.id

    if caso == "campagna_altrui":
        url_carta, url_campagna = carta_id, altrui_id
    elif caso == "carta_altrui":
        url_carta, url_campagna = carta_altrui_id, propria_id
    else:
        url_carta, url_campagna = carta_id, 999999

    resp = auth_client.post(f"/api/merchant/card/{url_carta}/campaigns/{url_campagna}/apply")

    assert resp.status_code == 404
    # Stato nel DB: si rilegge dalla sessione, scartando gli oggetti già in cache.
    session.expire_all()
    assert session.get(type(card), carta_id).cashback_cents == 370
    assert session.get(type(card), carta_altrui_id).cashback_cents == 370
    assert session.get(Campaign, propria_id).uses == 0
    assert session.get(Campaign, altrui_id).uses == 0


def test_applica_campagna_non_tocca_tree_points_pool_registro_e_pagina_cliente(
    session, merchant, card, auth_client
):
    """
    AC-26: dopo «Applica» (200) i tree points della carta, i punti del pool del mese (`MerchantPool`) e il numero
    di righe del registro `PointTransaction` sono identici a prima, e la pagina carta del cliente `GET /c/<token>`
    è identica a quella di prima salvo il saldo cashback, che è l'unico effetto voluto di «Applica».

    Partenza costruita con il flusso vero (`card_service.add_tree_points`, 20 punti): la carta ha tree points, il
    pool del mese ha una riga con 20 punti e il registro ha una riga. Valori attesi scritti a mano: tree points 20,
    pool 20, 1 riga di registro (non 21 né 0: nessun punto aggiunto o tolto, nessuna riga nuova). Il cashback
    passa da 3,70 € (370 centesimi) a 5,05 € (370 + 135 centesimi): la pagina «dopo» deve essere la pagina
    «prima» con la sola sostituzione «€ 3.70» → «€ 5.05» (formato `€ {euro:.2f}` della pagina di oggi). Se Applica
    cambiasse anche livello, barra di conversione o punti del mese, il confronto esatto fallirebbe. I due importi
    sono scelti diversi dal «€ 2.00» della barra di conversione, così la sostituzione non può toccare altro.
    """
    campagna = campaign_service.create_campaign(session, merchant, {
        "name": "Natale", "keyword": "NATALE26", "promo_text": "Sconto di Natale", "value_eur": 1.35,
    })
    card_service.add_tree_points(session, merchant, card.id, 20)
    card.cashback_cents = 370
    session.add(card)
    session.commit()
    # Id e token estratti prima della richiesta: dopo la chiamata gli oggetti in sessione possono essere scaduti.
    carta_id, campagna_id = card.id, campagna.id
    token = crypto.card_link_token(card.id, card.link_version)

    def stato():
        """Tree points, punti del pool per periodo e numero di righe del registro, riletti dal DB."""
        session.expire_all()
        pool = sorted((p.period, p.points) for p in session.exec(select(MerchantPool)).all())
        return (
            session.get(Card, carta_id).tree_points,
            pool,
            len(session.exec(select(PointTransaction)).all()),
        )

    prima = stato()
    assert prima[0] == 20 and [punti for _, punti in prima[1]] == [20] and prima[2] == 1
    pagina_prima = auth_client.get(f"/c/{token}").text
    assert "€ 3.70" in pagina_prima and "€ 5.05" not in pagina_prima

    resp = auth_client.post(f"/api/merchant/card/{carta_id}/campaigns/{campagna_id}/apply")

    assert resp.status_code == 200
    assert stato() == prima
    assert session.get(Card, carta_id).cashback_cents == 505
    pagina_dopo = auth_client.get(f"/c/{token}").text
    assert pagina_dopo == pagina_prima.replace("€ 3.70", "€ 5.05")


def test_applica_campagna_archiviata_dopo_il_caricamento_della_pagina_si_applica_comunque(
    session, merchant, card, auth_client
):
    """
    AC-25 (parte archiviata): una campagna archiviata dopo che la pagina è stata caricata si applica comunque
    (decisione 11). Con un negozio attivo, `POST .../campaigns/{id}/apply` su una campagna ARCHIVATA risponde 200,
    accredita l'importo sulla carta e conta un utilizzo: l'archiviazione toglie la campagna dalla pagina e dal
    webhook, ma non impedisce il «Applica» di chi aveva già la pagina aperta.

    Valori scelti a mano: cashback iniziale 3,70 € = 370 centesimi, importo 1,35 € = 135 centesimi; atteso
    370 + 135 = 505 centesimi (non 370: applicazione rifiutata o ignorata) e `uses` = 1 (non 0).
    """
    campagna = campaign_service.create_campaign(session, merchant, {
        "name": "Natale", "keyword": "NATALE26", "promo_text": "Sconto di Natale", "value_eur": 1.35,
    })
    campagna_id = campagna.id
    card.cashback_cents = 370
    session.add(card)
    session.commit()
    # La campagna viene archiviata DOPO il caricamento della pagina: qui, prima del POST di conferma.
    campaign_service.archive_campaign(session, merchant, campagna_id)

    resp = auth_client.post(f"/api/merchant/card/{card.id}/campaigns/{campagna_id}/apply")

    assert resp.status_code == 200
    # Stato nel DB: si rilegge dalla sessione, scartando gli oggetti già in cache.
    session.expire_all()
    assert session.get(type(card), card.id).cashback_cents == 505
    assert session.get(Campaign, campagna_id).uses == 1


def test_applica_campagna_senza_importo_conta_solo_l_utilizzo_anche_a_negozio_non_attivo(
    session, merchant, card, auth_client
):
    """
    AC-23 (importo 0): «Applica» su una campagna senza importo (`value_cents` = 0) con negozio attivo risponde 200
    con `applied_cashback` = 0, lascia invariato il cashback della carta e porta `uses` da 0 a 1. Con il negozio
    NON attivo (messo in pausa dopo la creazione) la stessa richiesta NON è bloccata, perché il 403 del contract
    vale solo per importo > 0: risponde 200, il cashback resta invariato e `uses` passa a 2.

    Valori scelti a mano: cashback iniziale 3,70 € = 370 centesimi, che deve restare esattamente 370 (3,70 €
    nella risposta) dopo entrambe le richieste, perché l'importo da accreditare è 0. `uses` atteso 1 e poi 2: ogni
    «Applica» conta un utilizzo (non 0: solo accredito senza contatore; non 403 alla seconda: blocco indebito).
    """
    campagna = campaign_service.create_campaign(session, merchant, {
        "name": "Estate", "keyword": "ESTATE26", "promo_text": "Sconto estivo", "value_eur": 0,
    })
    campagna_id, carta_id = campagna.id, card.id
    card.cashback_cents = 370
    session.add(card)
    session.commit()
    assert campagna.value_cents == 0 and campagna.uses == 0

    # Prima richiesta, a negozio attivo.
    resp = auth_client.post(f"/api/merchant/card/{carta_id}/campaigns/{campagna_id}/apply")

    assert resp.status_code == 200
    body = resp.json()
    assert body["applied_cashback"] == 0
    assert body["card"]["cashback_point"] == 3.7
    # Stato nel DB: si rilegge dalla sessione, scartando gli oggetti già in cache.
    session.expire_all()
    assert session.get(Card, carta_id).cashback_cents == 370
    assert session.get(Campaign, campagna_id).uses == 1

    # Il negozio esce dallo stato attivo: con importo 0 «Applica» non deve essere bloccato.
    merchant_crud.update_merchant(session, merchant, {"is_paused": True})

    resp = auth_client.post(f"/api/merchant/card/{carta_id}/campaigns/{campagna_id}/apply")

    assert resp.status_code == 200
    assert resp.json()["applied_cashback"] == 0
    session.expire_all()
    assert session.get(Card, carta_id).cashback_cents == 370
    assert session.get(Campaign, campagna_id).uses == 2


def test_gestione_carta_senza_campagne_da_mostrare_non_ha_il_blocco_campagne(
    session, merchant, card, auth_client
):
    """
    AC-21 (senza campagne): se il negozio non ha campagne NON archiviate, la pagina di gestione della carta non
    contiene `campaigns-section` (contract §9: la pagina resta quella di oggi) né alcun bottone `data-campaign-id`.
    Due situazioni, nello stesso negozio e in sequenza: (a) nessuna campagna propria, mentre un ALTRO negozio ne ha
    una attiva; (b) dopo aver creato e archiviato una campagna propria (solo campagne archiviate).

    Il valore atteso è l'assenza dei marcatori del contract (`id="campaigns-section"`, `data-campaign-id`), non un
    confronto con il markup: il contract congela solo quelli. Nel caso (a) il nome della campagna dell'altro negozio
    non deve comparire, perché le campagne di un altro negozio non sono mai proprie; nel caso (b) non deve comparire
    il nome della campagna archiviata, perché l'archiviata non si mostra (stessa regola di AC-21 con campagne).
    """
    altro = merchant_crud.create_merchant(session, {
        "business_name": "Altro Negozio",
        "email": "altro@test.it",
        "contact_phone": "+393339876543",
        "is_approved": True,
    })
    altrui = campaign_service.create_campaign(session, altro, {
        "name": "Estate", "keyword": "ESTATE26", "promo_text": "Sconto estivo", "value_eur": 1.35,
    })

    # (a) Nessuna campagna propria: quella dell'altro negozio non compare.
    resp = auth_client.get(f"/merchant/card/{card.id}/manage")

    assert resp.status_code == 200
    assert 'id="campaigns-section"' not in resp.text
    assert "data-campaign-id" not in resp.text
    assert _bottone(resp.text, altrui.id) is None
    assert "Estate" not in resp.text

    # (b) Solo una campagna propria, archiviata: la pagina resta senza blocco.
    archiviata = campaign_service.create_campaign(session, merchant, {
        "name": "Pasqua", "keyword": "PASQUA26", "promo_text": "Sconto pasquale", "value_eur": 1,
    })
    campaign_service.archive_campaign(session, merchant, archiviata.id)

    resp = auth_client.get(f"/merchant/card/{card.id}/manage")

    assert resp.status_code == 200
    assert 'id="campaigns-section"' not in resp.text
    assert "data-campaign-id" not in resp.text
    assert "Pasqua" not in resp.text
    assert "Estate" not in resp.text


@pytest.mark.parametrize(
    "stato, importo_disabilitato, banner",
    [
        ({"is_approved": True, "is_paused": False}, False, False),
        ({"is_approved": False}, True, True),
        ({"is_paused": True}, True, True),
    ],
    ids=["attivo", "attesa", "pausa"],
)
def test_pagina_disabilita_applica_con_importo_se_il_negozio_non_e_attivo(
    session, merchant, card, auth_client, stato, importo_disabilitato, banner
):
    """
    AC-24 (parte pagina): nella pagina di gestione della carta il bottone «Applica» di una campagna con importo > 0
    ha l'attributo `disabled` se e solo se il negozio non è attivo (in attesa o in pausa), insieme al banner di
    oggi (`id="service-banner"`); il bottone di una campagna senza importo NON è mai disabilitato, in nessuno
    stato (contract §9: `disabled` se `value_cents > 0` e `can_add` falso). Con il negozio attivo nessun bottone è
    disabilitato e il banner non c'è.

    Le campagne si creano a negozio attivo e solo dopo si cambia lo stato (stesso schema di AC-24 parte API).
    I valori attesi sono scritti a mano per ciascuno stato nei parametri: attivo → (False, nessun banner),
    attesa e pausa → (True, banner); per la campagna senza importo l'atteso è sempre False, perché il blocco di
    «Applica» a negozio non attivo riguarda solo l'accredito di cashback, che con importo 0 non c'è.
    """
    con_importo = campaign_service.create_campaign(session, merchant, {
        "name": "Natale", "keyword": "NATALE26", "promo_text": "Sconto di Natale", "value_eur": 2.5,
    })
    senza_importo = campaign_service.create_campaign(session, merchant, {
        "name": "Estate", "keyword": "ESTATE26", "promo_text": "Sconto estivo", "value_eur": 0,
    })
    con_importo_id, senza_importo_id = con_importo.id, senza_importo.id
    merchant_crud.update_merchant(session, merchant, stato)

    resp = auth_client.get(f"/merchant/card/{card.id}/manage")

    assert resp.status_code == 200
    html = resp.text

    def disabilitato(campaign_id: int) -> bool:
        """True se il tag di apertura del `<button>` della campagna ha l'attributo `disabled` (non le classi
        Tailwind `disabled:`, che non sono preceduti da spazio e seguiti da spazio, `=` o `>`)."""
        tag = re.search(r'<button\b[^>]*\bdata-campaign-id="' + str(campaign_id) + r'"[^>]*>', html)
        assert tag is not None, f"bottone della campagna {campaign_id} assente"
        return re.search(r"\sdisabled(\s|=|>|/)", tag.group(0)) is not None

    assert ('id="service-banner"' in html) is banner
    assert disabilitato(con_importo_id) is importo_disabilitato
    assert disabilitato(senza_importo_id) is False
