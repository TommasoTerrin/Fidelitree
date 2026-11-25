"""
v0.4.1, ticket 03, AC-11 (atomicità del conteggio delle richieste di una campagna).

Si testa `campaign_service.register_request` (contract §5, §11) senza passare dal webhook. SQLite non prova la
concorrenza vera (quella regge sull'`UPDATE ... RETURNING` di Postgres), ma una sessione separata che incrementa
mentre un'altra tiene in memoria un oggetto `Campaign` ormai vecchio distingue un incremento fatto dal database
(`dm_requests = dm_requests + 1`) da un leggi-modifica-scrivi sull'oggetto in memoria.
"""

from sqlmodel import Session

from app.models.models import Campaign
from app.services import campaign_service
from app.services.campaign_service import RequestChannel


def test_il_totale_richieste_parte_dal_database_e_non_dall_oggetto_in_memoria(session, merchant):
    """
    v0.4.1 AC-11: ogni chiamata ritorna il totale DM + commenti DOPO il proprio incremento, calcolato dal
    database; una richiesta registrata da un'altra sessione dopo che la campagna era stata caricata non si perde.
    I valori attesi (1, 2, 3) sono la sequenza fatta a mano: B porta il totale a 1, la richiesta di A a 2 (con un
    leggi-modifica-scrivi dall'oggetto in memoria, fermo a 0, sarebbe 1 e due richieste sull'ultimo posto
    riceverebbero entrambe la promo), il commento a 3 perché il totale somma i due canali. Una campagna che non
    esiste (eliminata tra il riconoscimento e l'incremento) dà `None`.
    """
    campagna = Campaign(merchant_id=merchant.id, name="Natale", keyword="NATALE", promo_text="Sconto di Natale")
    session.add(campagna)
    session.commit()
    session.refresh(campagna)
    campagna_id = campagna.id
    # L'oggetto della sessione A è caricato e fermo a zero: B non lo aggiornerà.
    assert campagna.dm_requests == 0

    with Session(session.get_bind()) as sessione_b:
        assert campaign_service.register_request(sessione_b, campagna_id, RequestChannel.DM) == 1

    assert campagna.dm_requests == 0  # premessa del test: l'oggetto di A è ormai vecchio

    assert campaign_service.register_request(session, campagna_id, RequestChannel.DM) == 2
    assert campaign_service.register_request(session, campagna_id, RequestChannel.COMMENT) == 3

    assert campaign_service.register_request(session, campagna_id + 1000, RequestChannel.DM) is None
