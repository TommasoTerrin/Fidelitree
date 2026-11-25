"""
v0.4.1, ticket 02, AC-08: la pausa di un negozio archivia le sue campagne non archiviate, nella stessa transazione
del cambio di stato. Si verifica solo sui confini HTTP: le azioni della dashboard (`/admin/api/merchants/{id}/...`)
e `PUT /api/merchant/{id}`. SQLite in-memory: le campagne di partenza si inseriscono con il modello.
"""

from sqlmodel import select

from app.models.models import Campaign, Merchant
from tests.test_admin import admin_login, new_merchant, post_action
from tests.test_admin_campaigns import add_campaign, day


def stato_campagne(session, merchant) -> dict:
    """
    Per ogni campagna del negozio (chiave = nome): `(archiviata, dm, commenti, usi)`. La sessione è quella che usa
    anche l'app, quindi si scade la cache prima di leggere: si vede quello che è stato davvero scritto.
    """
    session.expire_all()
    rows = session.exec(select(Campaign).where(Campaign.merchant_id == merchant.id)).all()
    return {c.name: (c.is_archived, c.dm_requests, c.comment_requests, c.uses) for c in rows}


def is_paused(session, merchant) -> bool:
    """Legge `is_paused` dal DB (cache scaduta)."""
    session.expire_all()
    return session.get(Merchant, merchant.id).is_paused


def test_la_pausa_archivia_le_campagne_nella_stessa_transazione_e_nessun_ripristino(session, client, admin_headers):
    """
    AC-08: (1) «Metti in pausa» dalla dashboard archivia le due campagne non archiviate del negozio attivo; quella
    già archiviata resta archiviata e i contatori di tutte restano quelli di partenza (valori scritti a mano sotto).
    (2) Una seconda pausa su un negozio già in pausa non cambia nulla: la campagna creata mentre è in pausa resta
    non archiviata; «Riattiva» e «Avvia» non ripristinano nessuna campagna. (3) Su un negozio in attesa la pausa
    dalla dashboard dà 409 e le sue campagne non archiviate restano tali. (4) `PUT /api/merchant/{id}` con
    `is_paused: true` su un negozio attivo archivia le sue campagne e non quelle di un altro negozio; su un negozio
    non approvato (resta «in attesa») non archivia nulla. (5) Atomicità: un `PUT` con `is_paused: true` e una soglia
    non valida (bronzo 400 >= argento di default 300) dà 400, nessuna campagna risulta archiviata e il negozio
    non è in pausa: archiviazione e cambio di stato stanno insieme o non stanno.
    """
    assert admin_login(client).status_code == 303
    url_put = lambda m: f"/api/merchant/{m.id}"

    # ---- (1) pausa dalla dashboard ----
    attivo = new_merchant(session, "Bar Attivo", is_approved=True)
    add_campaign(session, attivo, "Uno", "UNO", day(1), dm=3, comments=2, uses=1)
    add_campaign(session, attivo, "Due", "DUE", day(2), dm=5, comments=0, uses=4)
    add_campaign(session, attivo, "Gia archiviata", "GIA", day(0), archived=True, dm=7, comments=1, uses=2)

    assert post_action(client, attivo.id, "pause").status_code == 200
    assert is_paused(session, attivo) is True
    assert stato_campagne(session, attivo) == {
        "Uno": (True, 3, 2, 1),
        "Due": (True, 5, 0, 4),
        "Gia archiviata": (True, 7, 1, 2),
    }

    # ---- (2) seconda pausa, riattiva, avvia ----
    add_campaign(session, attivo, "Nata in pausa", "NATA", day(3))
    post_action(client, attivo.id, "pause")   # l'esito HTTP non è fissato dal contract: conta solo l'effetto
    assert stato_campagne(session, attivo)["Nata in pausa"] == (False, 0, 0, 0)

    assert post_action(client, attivo.id, "resume").status_code == 200
    assert is_paused(session, attivo) is False
    post_action(client, attivo.id, "approve")
    assert stato_campagne(session, attivo) == {
        "Uno": (True, 3, 2, 1),
        "Due": (True, 5, 0, 4),
        "Gia archiviata": (True, 7, 1, 2),
        "Nata in pausa": (False, 0, 0, 0),
    }

    # ---- (3) negozio in attesa: pausa dalla dashboard = 409, niente archiviato ----
    attesa = new_merchant(session, "Bar Attesa")
    add_campaign(session, attesa, "Attesa uno", "ATTUNO", day(1), dm=1)
    add_campaign(session, attesa, "Attesa due", "ATTDUE", day(2))
    assert post_action(client, attesa.id, "pause").status_code == 409
    assert stato_campagne(session, attesa) == {"Attesa uno": (False, 1, 0, 0), "Attesa due": (False, 0, 0, 0)}

    # ---- (4) PUT con is_paused: archivia solo le campagne del negozio che entra in pausa ----
    via_put = new_merchant(session, "Bar Via Put", is_approved=True)
    altro = new_merchant(session, "Bar Altro", is_approved=True)
    add_campaign(session, via_put, "Put uno", "PUTUNO", day(1), uses=3)
    add_campaign(session, via_put, "Put due", "PUTDUE", day(2), archived=True)
    add_campaign(session, altro, "Altro uno", "ALTROUNO", day(1))

    response = client.put(url_put(via_put), headers=admin_headers, json={"is_paused": True})
    assert response.status_code == 200
    assert is_paused(session, via_put) is True
    assert stato_campagne(session, via_put) == {"Put uno": (True, 0, 0, 3), "Put due": (True, 0, 0, 0)}
    assert stato_campagne(session, altro) == {"Altro uno": (False, 0, 0, 0)}

    # Negozio non approvato: `is_paused` vero non lo porta in pausa (resta «in attesa»), quindi nulla si archivia.
    non_approvato = new_merchant(session, "Bar Non Approvato")
    add_campaign(session, non_approvato, "Na uno", "NAUNO", day(1))
    response = client.put(url_put(non_approvato), headers=admin_headers, json={"is_paused": True})
    assert response.status_code == 200
    assert stato_campagne(session, non_approvato) == {"Na uno": (False, 0, 0, 0)}

    # ---- (5) atomicità: modifica non valida = nessuna campagna archiviata, negozio non in pausa ----
    atomico = new_merchant(session, "Bar Atomico", is_approved=True)
    add_campaign(session, atomico, "Atom uno", "ATOMUNO", day(1), dm=2)
    add_campaign(session, atomico, "Atom due", "ATOMDUE", day(2))
    response = client.put(url_put(atomico), headers=admin_headers, json={"is_paused": True, "bronze_threshold": 400})
    assert response.status_code == 400
    assert stato_campagne(session, atomico) == {"Atom uno": (False, 2, 0, 0), "Atom due": (False, 0, 0, 0)}
    assert is_paused(session, atomico) is False
