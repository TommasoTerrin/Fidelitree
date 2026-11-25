"""
v0.4.1, ticket 02, AC-01: lista delle campagne di un negozio nella dashboard admin
(`GET /admin/api/merchants/{merchant_id}/campaigns`). SQLite in-memory: le campagne di partenza si creano con il
modello `Campaign(...)` direttamente, e il comportamento si verifica solo sull'endpoint HTTP.
"""

from datetime import datetime, timezone

from app.models.models import Campaign
from tests.test_admin import ORIGIN, admin_login, new_merchant

BASE = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def day(n: int) -> datetime:
    """`BASE` spostato di `n` giorni: date esplicite, così l'ordine atteso non dipende dall'orologio."""
    return BASE.replace(day=BASE.day + n)


def add_campaign(session, merchant, name, keyword, created_at, *, archived=False, value_cents=0,
                 request_limit=None, dm=0, comments=0, uses=0) -> Campaign:
    """Inserisce una campagna con il modello, con `created_at` e contatori scelti dal test."""
    campaign = Campaign(
        merchant_id=merchant.id, name=name, keyword=keyword, promo_text=f"Offerta {name}",
        value_cents=value_cents, request_limit=request_limit, is_archived=archived,
        dm_requests=dm, comment_requests=comments, uses=uses, created_at=created_at,
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign


def test_lista_campagne_mostra_campi_stato_e_contatori_nell_ordine_di_d11(session, client):
    """
    AC-01: la lista contiene per ogni campagna nome, parola chiave, importo, limite, stato derivato e i tre
    contatori, con le non archiviate prima delle archiviate e, dentro ciascun gruppo, `created_at` decrescente e
    poi `id` decrescente. Le campagne si inseriscono volutamente in un ordine diverso da quello atteso (l'archiviata
    più recente ha anche la data più recente di tutte), così né l'ordine d'inserimento né la sola data bastano a
    produrre l'ordine giusto. L'ordine atteso è scritto a mano: non archiviate per data decrescente (nuova, poi
    le due pari data con l'id più alto per prima, poi la vecchia), quindi le archiviate per data decrescente. Le
    campagne di un altro negozio non compaiono, e per il negozio in attesa lo stato è «stopped» (non «active»).
    """
    active = new_merchant(session, "Bar Attivo", is_approved=True)
    pending = new_merchant(session, "Bar Attesa")   # non approvato: in attesa

    # Ordine d'inserimento (= ordine degli id) mescolato rispetto all'ordine atteso.
    add_campaign(session, active, "Vecchia", "VECCHIA", day(1), value_cents=250, request_limit=10, dm=3, comments=2, uses=1)
    add_campaign(session, active, "Archiviata vecchia", "ARCHVEC", day(0), archived=True, dm=7, comments=0, uses=4)
    add_campaign(session, active, "Pari a", "PARIA", day(2), dm=1)
    add_campaign(session, active, "Archiviata nuova", "ARCHNUOVA", day(5), archived=True, value_cents=500, comments=9)
    add_campaign(session, active, "Pari b", "PARIB", day(2), comments=6)    # stessa data di «Pari a», id più alto
    add_campaign(session, active, "Nuova", "NUOVA", day(3), dm=5, comments=4, uses=2)
    add_campaign(session, pending, "Altro negozio", "ALTRO", day(4), value_cents=100, request_limit=5, dm=2)

    assert admin_login(client).status_code == 303

    # --- negozio attivo ---
    response = client.get(f"/admin/api/merchants/{active.id}/campaigns", headers=ORIGIN)
    assert response.status_code == 200
    campaigns = response.json()["campaigns"]

    assert [c["name"] for c in campaigns] == [
        "Nuova", "Pari b", "Pari a", "Vecchia", "Archiviata nuova", "Archiviata vecchia",
    ]

    by_name = {c["name"]: c for c in campaigns}
    # Valori attesi scritti a mano dai dati di partenza: importo e limite restano numeri (0 e null = «nessuno»,
    # lo rende la pagina), i contatori escono uno per uno.
    assert {k: by_name["Vecchia"][k] for k in (
        "keyword", "value_cents", "request_limit", "status", "dm_requests", "comment_requests", "uses",
    )} == {
        "keyword": "VECCHIA", "value_cents": 250, "request_limit": 10, "status": "active",
        "dm_requests": 3, "comment_requests": 2, "uses": 1,
    }
    assert {k: by_name["Nuova"][k] for k in (
        "keyword", "value_cents", "request_limit", "status", "dm_requests", "comment_requests", "uses",
    )} == {
        "keyword": "NUOVA", "value_cents": 0, "request_limit": None, "status": "active",
        "dm_requests": 5, "comment_requests": 4, "uses": 2,
    }
    assert {k: by_name["Archiviata nuova"][k] for k in (
        "keyword", "value_cents", "request_limit", "status", "is_archived", "dm_requests", "comment_requests", "uses",
    )} == {
        "keyword": "ARCHNUOVA", "value_cents": 500, "request_limit": None, "status": "archived",
        "is_archived": True, "dm_requests": 0, "comment_requests": 9, "uses": 0,
    }
    assert by_name["Archiviata vecchia"]["status"] == "archived"
    assert by_name["Archiviata vecchia"]["dm_requests"] == 7 and by_name["Archiviata vecchia"]["uses"] == 4
    assert {c["status"] for c in campaigns if not c["is_archived"]} == {"active"}

    # --- negozio in attesa: la sua campagna non archiviata è ferma ---
    response = client.get(f"/admin/api/merchants/{pending.id}/campaigns", headers=ORIGIN)
    assert response.status_code == 200
    [only] = response.json()["campaigns"]
    assert only["name"] == "Altro negozio" and only["status"] == "stopped"
    assert only["value_cents"] == 100 and only["request_limit"] == 5 and only["dm_requests"] == 2


def test_creazione_salva_campagna_non_archiviata_con_contatori_a_zero_e_importo_in_centesimi(session, client):
    """
    v0.4.1 AC-02: `POST /admin/api/merchants/{id}/campaigns` risponde 201 e salva una campagna non archiviata con
    i tre contatori a 0, nome, parola chiave, testo e limite come inviati. L'importo arriva in euro (`value_eur`) e
    si salva in centesimi: 2,50 euro deve dare 250 (valore scritto a mano, non ricalcolato). Importo vuoto («»)
    o assente vale 0 («nessun importo», D1), con il limite assente che resta `null`. La riga deve esistere davvero
    nel DB: la risposta da sola non basterebbe a provarlo, quindi si rilegge con la sessione di test, che deve
    trovare esattamente le tre campagne create e nessuna di più.
    """
    from sqlmodel import select

    merchant = new_merchant(session, "Bar Creazione", is_approved=True)
    assert admin_login(client).status_code == 303
    url = f"/admin/api/merchants/{merchant.id}/campaigns"

    # --- importo 2,50 e limite 10 ---
    response = client.post(url, headers=ORIGIN, json={
        "name": "Sconto Natale", "keyword": "NATALE", "promo_text": "Un caffè in omaggio",
        "value_eur": 2.5, "request_limit": 10,
    })
    assert response.status_code == 201
    body = response.json()
    assert body["merchant_id"] == merchant.id
    assert body["name"] == "Sconto Natale" and body["keyword"] == "NATALE"
    assert body["promo_text"] == "Un caffè in omaggio"
    assert body["value_cents"] == 250 and body["request_limit"] == 10
    assert body["is_archived"] is False
    assert (body["dm_requests"], body["comment_requests"], body["uses"]) == (0, 0, 0)

    # --- importo vuoto: nessun importo ---
    response = client.post(url, headers=ORIGIN, json={
        "name": "Promo vuota", "keyword": "SCONTO", "promo_text": "Offerta senza importo",
        "value_eur": "", "request_limit": None,
    })
    assert response.status_code == 201
    assert response.json()["value_cents"] == 0 and response.json()["request_limit"] is None

    # --- importo assente dal corpo ---
    response = client.post(url, headers=ORIGIN, json={
        "name": "Promo assente", "keyword": "ESTATE", "promo_text": "Offerta senza campo importo",
    })
    assert response.status_code == 201
    assert response.json()["value_cents"] == 0

    # --- le righe sono davvero nel DB, non archiviate e con i contatori a zero ---
    session.expire_all()
    rows = session.exec(select(Campaign).where(Campaign.merchant_id == merchant.id)).all()
    by_keyword = {row.keyword: row for row in rows}
    assert set(by_keyword) == {"NATALE", "SCONTO", "ESTATE"}
    assert by_keyword["NATALE"].value_cents == 250 and by_keyword["NATALE"].request_limit == 10
    assert by_keyword["SCONTO"].value_cents == 0 and by_keyword["ESTATE"].value_cents == 0
    for row in rows:
        assert row.is_archived is False
        assert (row.dm_requests, row.comment_requests, row.uses) == (0, 0, 0)


def test_creazione_rifiuta_ogni_valore_fuori_dai_limiti_con_400_senza_eco_e_senza_scrivere(session, client):
    """
    v0.4.1 AC-03: ogni limite della decisione 12 e il formato della parola chiave (decisione 4) sono verificati
    prima di scrivere. Per ciascun corpo non valido, `POST /admin/api/merchants/{id}/campaigns` deve rispondere 400
    (mai 422: il corpo malformato lo giudica il service, non FastAPI), con un messaggio non vuoto che non contiene
    il valore inviato (il contract vieta di rimandarlo indietro), e la tabella `campaign` deve restare vuota.
    I casi sono quelli del criterio: nome di 2 caratteri, parola con uno spazio, parola vuota dopo la
    normalizzazione («!!»), testo di 851 caratteri (un oltre il massimo di 850), importo 50,01 (un centesimo oltre
    i 50,00 euro ammessi) e limite 0 (si ammette solo >= 1); più un tipo sbagliato (nome numerico), che deve dare
    400 e non un errore interno. Il nome di 2 caratteri è «Zq» e non «ab»: una sequenza così rara non compare per
    caso in un messaggio italiano, così il controllo «nessun eco» non dà falsi allarmi. Per il limite 0 non si
    cerca l'eco (la cifra «0» comparirebbe legittimamente in «3-40»): conta il 400 e il DB vuoto. Gli altri campi
    di ogni corpo sono validi, così l'unico motivo del rifiuto è il campo sotto esame.
    """
    from sqlmodel import func, select

    merchant = new_merchant(session, "Bar Limiti", is_approved=True)
    assert admin_login(client).status_code == 303
    url = f"/admin/api/merchants/{merchant.id}/campaigns"

    valido = {
        "name": "Sconto Natale", "keyword": "NATALE", "promo_text": "Un caffè in omaggio",
        "value_eur": 2.5, "request_limit": 10,
    }
    # (etichetta, campo, valore non valido, testo che NON deve comparire nella risposta, o None)
    casi = [
        ("nome di 2 caratteri", "name", "Zq", "Zq"),
        ("parola con uno spazio", "keyword", "NATALE 2026", "NATALE 2026"),
        ("parola vuota dopo la normalizzazione", "keyword", "!!", "!!"),
        ("testo di 851 caratteri", "promo_text", "Y" * 851, "Y" * 100),
        ("importo 50,01 euro", "value_eur", 50.01, "50.01"),
        ("limite 0", "request_limit", 0, None),
        ("nome numerico (tipo sbagliato)", "name", 987654, "987654"),
    ]

    for etichetta, campo, valore, eco in casi:
        response = client.post(url, headers=ORIGIN, json={**valido, campo: valore})
        assert response.status_code == 400, f"{etichetta}: atteso 400, ricevuto {response.status_code}"
        assert response.text.strip(), f"{etichetta}: il messaggio d'errore è vuoto"
        if eco is not None:
            assert eco not in response.text, f"{etichetta}: la risposta rimanda indietro il valore inviato"

    # Nessuna campagna scritta, per nessuno dei casi (conteggio sul DB, non sulla risposta).
    session.expire_all()
    assert session.exec(select(func.count()).select_from(Campaign)).one() == 0


def test_parola_chiave_in_conflitto_da_409_senza_scrivere_a_creazione_modifica_e_ripristino(session, client):
    """
    v0.4.1 AC-04: una parola chiave che, normalizzata, coincide con quella della carta
    (`settings.INSTAGRAM_CARD_KEYWORD`) o con quella di un'altra campagna NON archiviata dello stesso negozio dà 409
    e non scrive nulla, in tutti e tre i punti d'ingresso: creazione (`POST`), modifica (`PUT`) e ripristino
    (`POST .../restore`). I confronti si fanno su forme scritte diverse (`natale!` contro `NATALE`; la parola della
    carta in minuscolo e con un punto esclamativo), perché la normalizzazione toglie maiuscole e punteggiatura: un
    confronto sulla stringa grezza lascerebbe passare entrambe. «Nulla scritto» si verifica rileggendo il DB con la
    sessione di test: il numero di campagne resta quello di partenza, la campagna modificata conserva parola e nome
    di prima, e la campagna da ripristinare resta archiviata. Le due eccezioni del criterio devono invece passare con
    201: un altro negozio può usare la stessa parola, e una campagna archiviata non blocca nessuna parola (né alla
    creazione, qui provata con una campagna archiviata inserita col modello). Gli stati attesi sono scritti a mano
    dal criterio, non ricalcolati.
    """
    from sqlmodel import func, select

    from app.core.config import settings

    shop = new_merchant(session, "Bar Conflitti", is_approved=True)
    other = new_merchant(session, "Bar Altro", email="altro@example.com", is_approved=True)
    assert admin_login(client).status_code == 303

    def corpo(keyword, name="Nuova promo"):
        """Corpo valido in tutto tranne, eventualmente, la parola chiave sotto esame."""
        return {"name": name, "keyword": keyword, "promo_text": "Un caffè in omaggio",
                "value_eur": "", "request_limit": None}

    def totale():
        """Numero di campagne nel DB, riletto da zero (conteggio sul DB, non sulla risposta)."""
        session.expire_all()
        return session.exec(select(func.count()).select_from(Campaign)).one()

    def riga(campaign_id):
        """La riga `Campaign` riletta dal DB."""
        session.expire_all()
        return session.get(Campaign, campaign_id)

    url = f"/admin/api/merchants/{shop.id}/campaigns"
    natale = add_campaign(session, shop, "Natale", "NATALE", day(0))
    pasqua = add_campaign(session, shop, "Pasqua", "PASQUA", day(1))
    assert totale() == 2

    # --- creazione: «natale!» si normalizza come «NATALE» (in uso); la parola della carta, in un'altra forma, è riservata ---
    assert client.post(url, headers=ORIGIN, json=corpo("natale!")).status_code == 409
    carta_alterata = settings.INSTAGRAM_CARD_KEYWORD.lower() + "!"
    assert carta_alterata != settings.INSTAGRAM_CARD_KEYWORD
    assert client.post(url, headers=ORIGIN, json=corpo(carta_alterata)).status_code == 409
    assert totale() == 2

    # --- un altro negozio può usare la stessa parola ---
    response = client.post(f"/admin/api/merchants/{other.id}/campaigns", headers=ORIGIN, json=corpo("NATALE"))
    assert response.status_code == 201
    assert totale() == 3

    # --- una campagna archiviata non blocca la parola: «estate» è libera anche se «ESTATE» è archiviata ---
    add_campaign(session, shop, "Estate vecchia", "ESTATE", day(2), archived=True)
    assert totale() == 4
    response = client.post(url, headers=ORIGIN, json=corpo("estate", name="Estate nuova"))
    assert response.status_code == 201
    assert totale() == 5

    # --- modifica: portare «Pasqua» sulla parola di «Natale» (forma diversa) dà 409 e non cambia nulla ---
    response = client.put(f"{url}/{pasqua.id}", headers=ORIGIN, json=corpo("Natale!", name="Pasqua cambiata"))
    assert response.status_code == 409
    pasqua_dopo = riga(pasqua.id)
    assert pasqua_dopo.keyword == "PASQUA" and pasqua_dopo.name == "Pasqua"
    assert riga(natale.id).keyword == "NATALE"
    assert totale() == 5

    # --- ripristino: archivio «Sconto», creo «sconto» (permesso, l'altra è archiviata), poi il ripristino confligge ---
    sconto = add_campaign(session, shop, "Sconto", "SCONTO", day(3))
    assert client.post(f"{url}/{sconto.id}/archive", headers=ORIGIN).status_code == 200
    assert riga(sconto.id).is_archived is True
    response = client.post(url, headers=ORIGIN, json=corpo("sconto", name="Sconto bis"))
    assert response.status_code == 201
    prima = totale()

    response = client.post(f"{url}/{sconto.id}/restore", headers=ORIGIN)
    assert response.status_code == 409
    assert riga(sconto.id).is_archived is True
    assert totale() == prima


def test_modifica_sostituisce_ogni_campo_e_lascia_invariati_contatori_archiviazione_e_data(session, client):
    """
    v0.4.1 AC-05: `PUT /admin/api/merchants/{id}/campaigns/{cid}` risponde 200 e sostituisce tutti i campi
    modificabili (nome, parola chiave, testo, importo, limite) con quelli del corpo completo; i tre contatori,
    `is_archived` e `created_at` restano identici a quelli di partenza. Tre casi, ognuno con i valori attesi scritti
    a mano: (1) campagna attiva con contatori 4+3 DM/commenti e 2 usi: importo «1,20» euro (stringa con virgola)
    deve dare 120 centesimi, e il limite scende a 5, cioè SOTTO la somma dei contatori (7): la modifica è comunque
    accettata (200), perché l'effetto «offerte terminate» riguarda il webhook, non la modifica; (2) campagna
    archiviata: il limite vuoto («») diventa `null` (nessun limite) e `is_archived` resta vero, cioè la modifica non
    ripristina; (3) una campagna di un altro negozio dà 404 e la sua riga non cambia. La risposta da sola non
    basta: ogni riga si rilegge dal DB con la sessione di test. `created_at` si confronta senza fuso perché SQLite
    non lo conserva; il valore atteso è la data scelta dal test, non quella riletta prima della modifica.
    """
    shop = new_merchant(session, "Bar Modifica", is_approved=True)
    other = new_merchant(session, "Bar Altro Modifica", email="altro-modifica@example.com", is_approved=True)
    assert admin_login(client).status_code == 303

    attiva = add_campaign(session, shop, "Vecchio nome", "VECCHIA", day(0), value_cents=250, request_limit=100,
                          dm=4, comments=3, uses=2)
    archiviata = add_campaign(session, shop, "Archiviata", "ARCHIVIATA", day(1), archived=True, value_cents=500,
                              request_limit=20, dm=1, comments=0, uses=6)
    estranea = add_campaign(session, other, "Estranea", "ESTRANEA", day(2), value_cents=100, request_limit=9, dm=2)

    def riga(campaign_id):
        """La riga `Campaign` riletta dal DB."""
        session.expire_all()
        return session.get(Campaign, campaign_id)

    def senza_fuso(value):
        """Data senza fuso: SQLite restituisce `created_at` naive."""
        return value.replace(tzinfo=None)

    url = f"/admin/api/merchants/{shop.id}/campaigns"

    # --- (1) campagna attiva: tutti i campi cambiano, limite sotto i contatori accettato ---
    response = client.put(f"{url}/{attiva.id}", headers=ORIGIN, json={
        "name": "Nuovo nome", "keyword": "NUOVA", "promo_text": "Testo nuovo",
        "value_eur": "1,20", "request_limit": 5,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == attiva.id and body["merchant_id"] == shop.id
    assert body["name"] == "Nuovo nome" and body["keyword"] == "NUOVA" and body["promo_text"] == "Testo nuovo"
    assert body["value_cents"] == 120 and body["request_limit"] == 5
    assert body["is_archived"] is False
    assert (body["dm_requests"], body["comment_requests"], body["uses"]) == (4, 3, 2)

    dopo = riga(attiva.id)
    assert (dopo.name, dopo.keyword, dopo.promo_text) == ("Nuovo nome", "NUOVA", "Testo nuovo")
    assert (dopo.value_cents, dopo.request_limit) == (120, 5)
    assert (dopo.dm_requests, dopo.comment_requests, dopo.uses) == (4, 3, 2)
    assert dopo.is_archived is False
    assert senza_fuso(dopo.created_at) == senza_fuso(day(0))

    # --- (2) campagna archiviata: limite vuoto = nessun limite, resta archiviata ---
    response = client.put(f"{url}/{archiviata.id}", headers=ORIGIN, json={
        "name": "Archiviata bis", "keyword": "ARCHBIS", "promo_text": "Altro testo",
        "value_eur": "", "request_limit": "",
    })
    assert response.status_code == 200
    assert response.json()["is_archived"] is True
    assert response.json()["value_cents"] == 0 and response.json()["request_limit"] is None

    dopo = riga(archiviata.id)
    assert (dopo.name, dopo.keyword, dopo.promo_text) == ("Archiviata bis", "ARCHBIS", "Altro testo")
    assert (dopo.value_cents, dopo.request_limit) == (0, None)
    assert (dopo.dm_requests, dopo.comment_requests, dopo.uses) == (1, 0, 6)
    assert dopo.is_archived is True
    assert senza_fuso(dopo.created_at) == senza_fuso(day(1))

    # --- (3) campagna di un altro negozio: 404 e riga intatta ---
    response = client.put(f"{url}/{estranea.id}", headers=ORIGIN, json={
        "name": "Rubata", "keyword": "RUBATA", "promo_text": "Non deve passare",
        "value_eur": 9, "request_limit": 1,
    })
    assert response.status_code == 404
    dopo = riga(estranea.id)
    assert (dopo.name, dopo.keyword, dopo.promo_text) == ("Estranea", "ESTRANEA", "Offerta Estranea")
    assert (dopo.value_cents, dopo.request_limit, dopo.dm_requests) == (100, 9, 2)


def test_archivia_e_ripristina_cambiano_solo_lo_stato_ed_elimina_cancella_la_riga_e_libera_la_parola(session, client):
    """
    v0.4.1 AC-06: su una campagna con contatori non zero (3 DM, 2 commenti, 4 usi), `archive` e `restore` cambiano
    solo lo stato e ripeterli non cambia nulla. Dopo `archive` (200) lo stato è «archived» e `is_archived` vero;
    ripetuto, la risposta è identica alla prima (idempotenza). Dopo `restore` (200) lo stato è «active»; ripetuto,
    identico. In entrambi i passaggi gli altri campi (nome, parola, testo, importo, limite, i tre contatori e
    `created_at`) restano uguali a quelli di partenza, scritti a mano: il confronto è su tutta la risposta tranne i
    due campi che devono cambiare (`is_archived` e `status`), così un campo azzerato o riscritto sarebbe visto.
    Poi `DELETE` risponde 200 `{"deleted": true}`; la riga non c'è più nel DB (riletta con la sessione di test: con
    la riga spariscono anche i contatori, che non esistono altrove), la campagna non compare nella lista admin e la
    sua parola torna libera (D10): una nuova campagna con la stessa parola si crea con 201. Un secondo `DELETE` sulla
    stessa campagna dà 404. Il controllo del ripristino contro le parole in conflitto (AC-04) non si ripete qui. Il
    controllo sullo scanner appartiene al ticket 05 (`scanner_campaigns` non esiste ancora).
    """
    merchant = new_merchant(session, "Bar Stati", is_approved=True)
    assert admin_login(client).status_code == 303
    url = f"/admin/api/merchants/{merchant.id}/campaigns"

    campagna = add_campaign(session, merchant, "Natale", "NATALE", day(0), value_cents=250, request_limit=10,
                            dm=3, comments=2, uses=4)
    campaign_id = campagna.id
    item = f"{url}/{campaign_id}"

    def senza_stato(body):
        """La risposta senza i due campi che archiviare e ripristinare devono cambiare."""
        return {k: v for k, v in body.items() if k not in ("is_archived", "status")}

    def riga():
        """La riga `Campaign` riletta dal DB (None se non esiste più)."""
        session.expire_all()
        return session.get(Campaign, campaign_id)

    # Valori di partenza scritti a mano: contatori non zero, importo e limite impostati.
    assert (campagna.dm_requests, campagna.comment_requests, campagna.uses) == (3, 2, 4)
    assert (campagna.value_cents, campagna.request_limit) == (250, 10)

    # --- archivia, due volte ---
    response = client.post(f"{item}/archive", headers=ORIGIN)
    assert response.status_code == 200
    archiviata = response.json()
    assert archiviata["is_archived"] is True and archiviata["status"] == "archived"
    assert (archiviata["name"], archiviata["keyword"], archiviata["promo_text"]) == (
        "Natale", "NATALE", "Offerta Natale")
    assert (archiviata["value_cents"], archiviata["request_limit"]) == (250, 10)
    assert (archiviata["dm_requests"], archiviata["comment_requests"], archiviata["uses"]) == (3, 2, 4)

    response = client.post(f"{item}/archive", headers=ORIGIN)
    assert response.status_code == 200
    assert response.json() == archiviata
    assert riga().is_archived is True

    # --- ripristina, due volte ---
    response = client.post(f"{item}/restore", headers=ORIGIN)
    assert response.status_code == 200
    ripristinata = response.json()
    assert ripristinata["is_archived"] is False and ripristinata["status"] == "active"
    assert senza_stato(ripristinata) == senza_stato(archiviata)
    assert (ripristinata["dm_requests"], ripristinata["comment_requests"], ripristinata["uses"]) == (3, 2, 4)

    response = client.post(f"{item}/restore", headers=ORIGIN)
    assert response.status_code == 200
    assert response.json() == ripristinata
    dopo = riga()
    assert dopo.is_archived is False
    assert (dopo.dm_requests, dopo.comment_requests, dopo.uses) == (3, 2, 4)

    # --- elimina: la riga sparisce, la lista non la mostra più ---
    response = client.delete(item, headers=ORIGIN)
    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert riga() is None

    response = client.get(url, headers=ORIGIN)
    assert response.status_code == 200
    assert response.json()["campaigns"] == []

    # --- la parola «NATALE» è di nuovo libera ---
    response = client.post(url, headers=ORIGIN, json={
        "name": "Natale bis", "keyword": "NATALE", "promo_text": "Di nuovo in offerta",
        "value_eur": "", "request_limit": None,
    })
    assert response.status_code == 201

    # --- secondo «Elimina» sulla stessa campagna: 404 ---
    assert client.delete(item, headers=ORIGIN).status_code == 404


def test_api_e_pagina_delle_campagne_seguono_le_regole_della_dashboard_admin(session, client, admin_headers):
    """
    v0.4.1 AC-07: i sei endpoint admin delle campagne (lista, crea, modifica, archivia, ripristina, elimina) e la
    pagina seguono le regole di oggi della dashboard. Si verifica, nell'ordine: (1) senza sessione né chiave ogni
    endpoint dà 401 e non cambia nulla; (2) con `X-Admin-Key` corretta ogni endpoint funziona anche senza `Origin`
    (uso da curl e script), con gli esiti attesi scritti a mano (200, 201, `{"deleted": true}`); (3) con il cookie
    di sessione, `POST`/`PUT`/`DELETE` con `Origin` estraneo, `null` o assente (e `Referer` estraneo) dànno 403 e la
    tabella `campaign` resta identica riga per riga, mentre con l'`Origin` giusto funzionano; (4) negozio
    inesistente, campagna inesistente e campagna di un altro negozio dànno 404, e la campagna dell'altro negozio
    resta intatta; (5) ogni risposta di successo (200/201) porta `Cache-Control: no-store`,
    `X-Robots-Tag: noindex` e `Referrer-Policy: same-origin` (come i test di oggi sulla dashboard: con
    `no-referrer` il browser manderebbe `Origin: null` e il controllo CSRF rifiuterebbe ogni azione). Sulle
    risposte di errore (400, 401, 403, 404, 409) gli header privati NON si asseriscono, né la presenza né
    l'assenza: scelta del founder (2026-11-13: «come oggi», come nelle API admin esistenti). «Nulla
    cambia» si prova rileggendo il DB con la sessione di test, non dalla risposta. Infine, sul sorgente di
    `app/templates/admin/dashboard.html`, la pagina contiene i testi «Campagne», «Archivia», «Ripristina»,
    «Elimina» e `confirm(` (l'eliminazione chiede conferma) e nessuno dei costrutti vietati dei test di oggi
    (DOM solo con `textContent`/`createElement`). I controlli sul sorgente sono in fondo, così un errore sugli
    endpoint si vede prima e con il suo messaggio.
    """
    from pathlib import Path

    from sqlmodel import select

    shop = new_merchant(session, "Bar Regole", is_approved=True)
    other = new_merchant(session, "Bar Estraneo", email="estraneo@example.com", is_approved=True)
    mine = add_campaign(session, shop, "Mia", "MIA", day(0))
    to_delete = add_campaign(session, shop, "Da eliminare", "ELIMINA", day(1))
    foreign = add_campaign(session, other, "Estranea", "ESTRANEA", day(2), value_cents=100, request_limit=9, dm=2)
    mine_id, to_delete_id, foreign_id, foreign_merchant_id = mine.id, to_delete.id, foreign.id, other.id

    body = {"name": "Corpo valido", "keyword": "CORPO", "promo_text": "Un caffè in omaggio",
            "value_eur": "", "request_limit": None}
    collection = f"/admin/api/merchants/{shop.id}/campaigns"

    def snapshot():
        """Tutte le righe `campaign` rilette dal DB, campo per campo: due istantanee uguali = nulla è cambiato."""
        session.expire_all()
        rows = session.exec(select(Campaign).order_by(Campaign.id)).all()
        return [(r.id, r.merchant_id, r.name, r.keyword, r.promo_text, r.value_cents, r.request_limit,
                 r.is_archived, r.dm_requests, r.comment_requests, r.uses) for r in rows]

    def private(response, label):
        """
        Gli header privati che ogni risposta di SUCCESSO (200/201) deve avere. Si chiama solo sui successi: per le
        risposte di errore il founder ha deciso (2026-11-13: «come oggi») di non fissare nulla.
        """
        assert response.headers.get("Cache-Control") == "no-store", label
        assert response.headers.get("X-Robots-Tag") == "noindex", label
        assert response.headers.get("Referrer-Policy") == "same-origin", label

    def endpoints(merchant_id, campaign_id):
        """I sei endpoint come (etichetta, metodo, percorso, corpo JSON o None, scrive?)."""
        base = f"/admin/api/merchants/{merchant_id}/campaigns"
        item = f"{base}/{campaign_id}"
        return [
            ("lista", "GET", base, None, False),
            ("crea", "POST", base, body, True),
            ("modifica", "PUT", item, body, True),
            ("archivia", "POST", f"{item}/archive", None, True),
            ("ripristina", "POST", f"{item}/restore", None, True),
            ("elimina", "DELETE", item, None, True),
        ]

    def call(method, path, payload, headers):
        """Chiama l'endpoint con gli header dati (il corpo JSON solo se c'è)."""
        kwargs = {"headers": headers}
        if payload is not None:
            kwargs["json"] = payload
        return client.request(method, path, **kwargs)

    start = snapshot()
    assert [row[3] for row in start] == ["MIA", "ELIMINA", "ESTRANEA"]

    # --- (1) senza sessione né chiave: 401 per tutti e sei, nulla cambia ---
    for label, method, path, payload, _ in endpoints(shop.id, mine_id):
        for headers in ({}, ORIGIN, {"X-Admin-Key": "sbagliata"}):
            response = call(method, path, payload, headers)
            assert response.status_code == 401, f"{label} {headers}: atteso 401, ricevuto {response.status_code}"
            # Niente asserzione sugli header privati del 401 (né di alcun altro errore): scelta del founder,
            # 2026-11-13, «come oggi» (le API admin esistenti li mettono solo sui successi).
    assert snapshot() == start

    # --- (2) X-Admin-Key corretta, nessun Origin e nessun cookie: tutti e sei funzionano ---
    response = call("GET", collection, None, admin_headers)
    assert response.status_code == 200, "lista con chiave"
    assert [c["name"] for c in response.json()["campaigns"]] == ["Da eliminare", "Mia"]
    private(response, "lista con chiave")

    response = call("POST", collection, body, admin_headers)
    assert response.status_code == 201, "crea con chiave"
    assert response.json()["keyword"] == "CORPO" and response.json()["merchant_id"] == shop.id
    private(response, "crea con chiave")

    response = call("PUT", f"{collection}/{mine_id}", {**body, "name": "Mia rinominata", "keyword": "RINOMINATA"},
                    admin_headers)
    assert response.status_code == 200, "modifica con chiave"
    assert response.json()["name"] == "Mia rinominata"
    private(response, "modifica con chiave")

    response = call("POST", f"{collection}/{mine_id}/archive", None, admin_headers)
    assert response.status_code == 200 and response.json()["is_archived"] is True, "archivia con chiave"
    private(response, "archivia con chiave")

    response = call("POST", f"{collection}/{mine_id}/restore", None, admin_headers)
    assert response.status_code == 200 and response.json()["is_archived"] is False, "ripristina con chiave"
    private(response, "ripristina con chiave")

    response = call("DELETE", f"{collection}/{to_delete_id}", None, admin_headers)
    assert response.status_code == 200 and response.json() == {"deleted": True}, "elimina con chiave"
    private(response, "elimina con chiave")
    session.expire_all()
    assert session.get(Campaign, to_delete_id) is None

    # La chiave vale anche per gli errori (header privati non asseriti sugli errori: scelta del founder).
    response = call("GET", "/admin/api/merchants/999999/campaigns", None, admin_headers)
    assert response.status_code == 404, "lista di un negozio inesistente con chiave"

    # --- (3) con il cookie: Origin estraneo, «null», assente o Referer estraneo → 403 e nulla cambia ---
    assert admin_login(client).status_code == 303
    to_delete_again = add_campaign(session, shop, "Da eliminare bis", "ELIMINABIS", day(3))
    to_delete_again_id = to_delete_again.id
    before = snapshot()
    rejected = ({"Origin": "https://evil.example"}, {"Origin": "null"}, {}, {"Referer": "https://evil.example/admin"},
                {"Origin": "http://testserver.evil.example"})
    for label, method, path, payload, writes in endpoints(shop.id, mine_id):
        if not writes:
            continue
        target = f"{collection}/{to_delete_again_id}" if label == "elimina" else path
        for headers in rejected:
            response = call(method, target, payload, headers)
            assert response.status_code == 403, f"{label} {headers}: atteso 403, ricevuto {response.status_code}"
            # Header privati non asseriti sul 403 (scelta del founder, 2026-11-13: «come oggi»).
    assert snapshot() == before

    # La lista (GET) con il cookie non richiede l'Origin; gli altri con l'origine giusta funzionano.
    response = call("GET", collection, None, {})
    assert response.status_code == 200, "lista con cookie senza Origin"
    private(response, "lista con cookie")
    response = call("POST", f"{collection}/{mine_id}/archive", None, {"Referer": "http://testserver/admin"})
    assert response.status_code == 200, "archivia con cookie e Referer giusto"
    response = call("POST", f"{collection}/{mine_id}/restore", None, ORIGIN)
    assert response.status_code == 200, "ripristina con cookie e Origin giusto"
    response = call("DELETE", f"{collection}/{to_delete_again_id}", None, ORIGIN)
    assert response.status_code == 200 and response.json() == {"deleted": True}, "elimina con cookie e Origin giusto"

    # --- (4) 404: negozio inesistente, campagna inesistente, campagna di un altro negozio ---
    before = snapshot()
    casi = {
        "negozio inesistente": endpoints(999999, mine_id),
        "campagna inesistente": endpoints(shop.id, 999999)[2:],   # i quattro con id campagna (la raccolta è valida)
        "campagna di un altro negozio": endpoints(shop.id, foreign_id)[2:],
    }
    for nome, lista in casi.items():
        for label, method, path, payload, _ in lista:
            for headers in (ORIGIN, admin_headers):
                response = call(method, path, payload, headers)
                assert response.status_code == 404, (
                    f"{nome}, {label} {list(headers)}: atteso 404, ricevuto {response.status_code}")
                # Header privati non asseriti sul 404 (scelta del founder, 2026-11-13: «come oggi»).
    assert snapshot() == before
    intatta = [row for row in before if row[0] == foreign_id]
    assert intatta == [(foreign_id, foreign_merchant_id, "Estranea", "ESTRANEA", "Offerta Estranea", 100, 9,
                        False, 2, 0, 0)]

    # --- (5) la pagina: testi richiesti e nessun costrutto vietato (controlli sul sorgente, come oggi) ---
    source = Path("app/templates/admin/dashboard.html").read_text(encoding="utf-8")
    for required in ("Campagne", "Archivia", "Ripristina", "Elimina", "confirm("):
        assert required in source, f"manca nella dashboard: {required}"
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "| safe", "|safe"):
        assert forbidden not in source, forbidden
