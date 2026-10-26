"""
Test della pagina carta del cliente (`GET /c/<token>`), della sua 404 amichevole e di `/privacy`.

Le carte nascono dal flusso vero (webhook firmato + Zernio finto) e il link si legge dalla card inviata,
come farebbe il cliente. Nessuna rete.
"""

import uuid
from datetime import timedelta

import pytest
from sqlmodel import select

from app.core import crypto
from app.core.clock import utc_now
from app.core.errors import NotFoundError
from app.models.models import Card
from app.services import card_service, instagram_service
from app.services.db_crud import merchant_crud
from tests.conftest import TEST_PUBLIC_BASE_URL, signed_webhook

CONVERSATION = "conv-pagina-carta"
SHOP_NAME = "Bar Demo"


def _dm(event_id: str, sender: str) -> dict:
    """Webhook `message.received` con la parola chiave, da un follower, di un minuto fa."""
    sent_at = (utc_now() - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    return {
        "id": event_id,
        "event": "message.received",
        "message": {
            "id": "m-1", "direction": "incoming", "text": "carta", "sentAt": sent_at,
            "sender": {"id": sender, "instagramProfile": {"isFollower": True}},
        },
        "conversation": {"id": CONVERSATION},
        "account": {"accountId": "acc-1"},
        "metadata": {},
    }


def _request_card(client, session, merchant, zernio_mock, sender="igsid-cliente-1", event_id="evt-card-1"):
    """Il cliente scrive CARTA: ritorna `(carta, token)` con il token preso dal link della card inviata."""
    assert signed_webhook(client, merchant, _dm(event_id, sender)).status_code == 200
    link = zernio_mock.bodies()[-1]["template"]["elements"][0]["buttons"][0]["url"]
    prefix = f"{TEST_PUBLIC_BASE_URL}/c/"
    assert link.startswith(prefix)
    token = link[len(prefix):]
    session.expire_all()
    card = session.exec(
        select(Card).where(Card.merchant_id == merchant.id, Card.igsid_hash == crypto.igsid_blind_index(sender))
    ).one()
    return card, token


# --- get_card_by_link_token (shell) ---

def test_get_card_by_link_token_trova_la_carta(client, session, instagram_merchant, zernio_mock):
    card, token = _request_card(client, session, instagram_merchant, zernio_mock)
    assert instagram_service.get_card_by_link_token(session, token).id == card.id


@pytest.mark.parametrize("token", ["", "inventato", "x" * 500, "è-non-ascii"])
def test_get_card_by_link_token_sconosciuto_solleva_not_found(session, instagram_merchant, token):
    with pytest.raises(NotFoundError):
        instagram_service.get_card_by_link_token(session, token)


def test_get_card_by_link_token_non_cita_ne_il_token_ne_la_carta(session, instagram_merchant):
    with pytest.raises(NotFoundError) as excinfo:
        instagram_service.get_card_by_link_token(session, "token-segreto-xyz")
    assert "token-segreto-xyz" not in str(excinfo.value)


def test_versione_aumentata_senza_ricalcolare_l_hash_il_vecchio_token_non_vale(
    client, session, instagram_merchant, zernio_mock,
):
    """Il confronto è col token ricalcolato da id e versione: la revoca vale anche con l'hash vecchio nel DB."""
    card, token = _request_card(client, session, instagram_merchant, zernio_mock)
    card.link_version += 1  # hash lasciato com'era
    session.add(card)
    session.commit()
    with pytest.raises(NotFoundError):
        instagram_service.get_card_by_link_token(session, token)


def test_il_confronto_usa_il_tempo_costante(client, session, instagram_merchant, zernio_mock, monkeypatch):
    card, token = _request_card(client, session, instagram_merchant, zernio_mock)
    seen = []
    real = crypto.constant_time_equals

    def spy(a, b):
        seen.append((a, b))
        return real(a, b)

    monkeypatch.setattr(crypto, "constant_time_equals", spy)
    instagram_service.get_card_by_link_token(session, token)
    assert seen, "il token va confrontato con constant_time_equals"


# --- pagina carta ---

def test_pagina_carta_dal_link_del_webhook(client, session, instagram_merchant, zernio_mock):
    card, token = _request_card(client, session, instagram_merchant, zernio_mock)
    card_service.add_tree_points(session, instagram_merchant, card.id, 150)
    session.expire_all()
    cashback_cents = session.get(Card, card.id).cashback_cents

    resp = client.get(f"/c/{token}")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    text = resp.text
    assert SHOP_NAME in text
    assert "🥉 Bronzo" in text and "150 punti questo mese" in text   # livello del pool
    assert "Ancora 150 punti al livello Argento" in text and "Insieme questo mese stiamo piantando 1 albero 🌳" in text
    assert f"€ {cashback_cents / 100:.2f}" in text                      # cashback
    assert "I tuoi Tree Points" in text and f"🌳 {session.get(Card, card.id).tree_points}" in text


def test_il_qr_contiene_l_id_della_carta_e_mai_il_token(client, session, instagram_merchant, zernio_mock):
    card, token = _request_card(client, session, instagram_merchant, zernio_mock)
    text = client.get(f"/c/{token}").text
    assert f'text: "{card.id}"' in text
    assert token not in text
    assert "/c/" not in text.split("new QRCode(")[1]  # il QR non è l'URL della pagina


def test_la_pagina_carta_non_e_una_pwa(client, session, instagram_merchant, zernio_mock):
    _, token = _request_card(client, session, instagram_merchant, zernio_mock)
    text = client.get(f"/c/{token}").text
    assert 'rel="manifest"' not in text
    assert "serviceWorker" not in text
    assert "/wallet" not in text and "Le tue carte" not in text


def test_la_pagina_carta_linka_la_privacy(client, session, instagram_merchant, zernio_mock):
    _, token = _request_card(client, session, instagram_merchant, zernio_mock)
    assert 'href="/privacy"' in client.get(f"/c/{token}").text


def test_la_pagina_carta_non_si_mette_in_cache_e_non_manda_il_referer(
    client, session, instagram_merchant, zernio_mock,
):
    """Il saldo cambia a ogni scan e l'URL contiene il segreto."""
    _, token = _request_card(client, session, instagram_merchant, zernio_mock)
    headers = client.get(f"/c/{token}").headers
    assert "no-store" in headers["cache-control"]
    assert headers["referrer-policy"] == "no-referrer"


def test_banner_di_test_solo_per_negozi_di_test(client, session, instagram_merchant, zernio_mock):
    _, token = _request_card(client, session, instagram_merchant, zernio_mock)
    merchant_crud.update_merchant(session, instagram_merchant, {"type": "free"})
    assert "Carta di Test" not in client.get(f"/c/{token}").text
    merchant_crud.update_merchant(session, instagram_merchant, {"type": "test"})
    assert "Carta di Test" in client.get(f"/c/{token}").text


def test_conversione_attiva_mostra_i_punti_mancanti(client, session, instagram_merchant, zernio_mock):
    card, token = _request_card(client, session, instagram_merchant, zernio_mock)
    merchant_crud.update_merchant(
        session, instagram_merchant, {"conversion_enabled": True, "conversion_threshold": 50},
    )
    card_service.add_tree_points(session, instagram_merchant, card.id, 20)
    assert "Ancora 30 punti per € 2.00 di cashback" in client.get(f"/c/{token}").text


def test_conversione_disattivata_senza_barra_personale(client, session, instagram_merchant, zernio_mock):
    card, token = _request_card(client, session, instagram_merchant, zernio_mock)
    merchant_crud.update_merchant(session, instagram_merchant, {"conversion_enabled": False})
    card_service.add_tree_points(session, instagram_merchant, card.id, 20)
    text = client.get(f"/c/{token}").text
    assert "di cashback" not in text and 'id="conversion-note"' not in text
    assert "Cashback" in text  # il cashback resta sempre visibile


def test_pagina_carta_senza_livello(client, session, instagram_merchant, zernio_mock):
    _, token = _request_card(client, session, instagram_merchant, zernio_mock)
    text = client.get(f"/c/{token}").text
    assert "Nessun livello" in text
    assert "Ancora 100 punti al livello Bronzo" in text  # soglie di default 100/300/600
    assert "stiamo piantando" not in text


def test_pagina_carta_con_pool_oro_mostra_il_livello_massimo(client, session, instagram_merchant, zernio_mock):
    card, token = _request_card(client, session, instagram_merchant, zernio_mock)
    merchant_crud.update_merchant(session, instagram_merchant, {"conversion_enabled": False})
    card_service.add_tree_points(session, instagram_merchant, card.id, 700)
    text = client.get(f"/c/{token}").text
    assert "🥇 Oro" in text
    assert "Livello massimo raggiunto!" in text
    assert "Insieme questo mese stiamo piantando 5 alberi 🌳" in text
    assert "al livello" not in text  # nessun livello successivo


# --- 404 amichevole, revoca, isolamento ---

def test_token_inventato_404_amichevole(client, instagram_merchant):
    resp = client.get("/c/token-inventato")
    assert resp.status_code == 404
    assert "text/html" in resp.headers["content-type"]
    assert "Link non valido o scaduto" in resp.text
    assert "scrivi CARTA al negozio su Instagram per riceverne uno nuovo" in resp.text
    assert 'rel="manifest"' not in resp.text


def test_il_404_non_dice_se_la_carta_esiste(client, session, instagram_merchant, zernio_mock):
    """Token inventato e token revocato di una carta vera: stessa risposta, byte per byte."""
    card, token = _request_card(client, session, instagram_merchant, zernio_mock)
    card.link_version += 1
    card.link_token_hash = crypto.token_hash(crypto.card_link_token(card.id, card.link_version))
    session.add(card)
    session.commit()

    revocato = client.get(f"/c/{token}")
    inventato = client.get("/c/" + "a" * len(token))
    assert revocato.status_code == inventato.status_code == 404
    assert revocato.text == inventato.text
    assert token not in revocato.text


def test_link_revocato_il_vecchio_token_404_e_il_nuovo_200(client, session, instagram_merchant, zernio_mock):
    card, old_token = _request_card(client, session, instagram_merchant, zernio_mock)
    card.link_version += 1
    new_token = crypto.card_link_token(card.id, card.link_version)
    card.link_token_hash = crypto.token_hash(new_token)
    session.add(card)
    session.commit()

    assert client.get(f"/c/{old_token}").status_code == 404
    assert client.get(f"/c/{new_token}").status_code == 200


def test_ogni_token_mostra_solo_la_propria_carta(client, session, instagram_merchant, zernio_mock):
    """Due negozi, due clienti: il token di una carta non mostra mai l'altra."""
    from tests.test_webhook import _other_merchant

    altro = _other_merchant(session, hook_id="hook-2", account_id="acc-2", name="Forno Demo")
    card_a, token_a = _request_card(client, session, instagram_merchant, zernio_mock, "igsid-a", "evt-a")
    payload_b = _dm("evt-b", "igsid-b")
    payload_b["account"]["accountId"] = "acc-2"
    assert signed_webhook(client, altro, payload_b).status_code == 200
    token_b = zernio_mock.bodies()[-1]["template"]["elements"][0]["buttons"][0]["url"].rsplit("/c/", 1)[1]
    card_service.add_tree_points(session, instagram_merchant, card_a.id, 40)

    page_a, page_b = client.get(f"/c/{token_a}").text, client.get(f"/c/{token_b}").text
    assert SHOP_NAME in page_a and "Forno Demo" not in page_a
    assert "Forno Demo" in page_b and SHOP_NAME not in page_b
    assert "40 punti questo mese" in page_a and "40 punti" not in page_b


def test_l_uuid_della_carta_non_apre_la_pagina(client, session, instagram_merchant, zernio_mock):
    """Il QR (= id della carta) fotografato al banco non vale come link."""
    card, _ = _request_card(client, session, instagram_merchant, zernio_mock)
    assert client.get(f"/c/{card.id}").status_code == 404


# --- scan dal QR (id della carta) ---

def test_gestione_dal_qr_solo_per_il_merchant_della_carta(
    client, session, instagram_merchant, zernio_mock, merchant,
):
    card, _ = _request_card(client, session, instagram_merchant, zernio_mock)
    from app.core.dependencies import get_optional_merchant
    from app.main import app

    app.dependency_overrides[get_optional_merchant] = lambda: instagram_merchant
    assert client.get(f"/merchant/card/{card.id}/manage").status_code == 200
    app.dependency_overrides[get_optional_merchant] = lambda: merchant  # un altro negozio
    assert client.get(f"/merchant/card/{card.id}/manage").status_code == 404
    assert client.get(f"/merchant/card/{uuid.uuid4()}/manage").status_code == 404


def test_scan_di_una_carta_instagram_aggiorna_saldo_registro_e_pool(
    client, session, instagram_merchant, zernio_mock, merchant,
):
    from app.core.dependencies import get_current_merchant
    from app.main import app
    from app.models.models import MerchantPool, PointTransaction

    card, token = _request_card(client, session, instagram_merchant, zernio_mock)
    merchant_crud.update_merchant(session, instagram_merchant, {"conversion_enabled": False})
    app.dependency_overrides[get_current_merchant] = lambda: instagram_merchant

    resp = client.post(f"/api/merchant/add-tree-points/{card.id}", json={"tree_points": 25})

    assert resp.status_code == 200
    session.expire_all()
    assert session.get(Card, card.id).tree_points == 25
    assert [t.delta for t in session.exec(select(PointTransaction)).all()] == [25]
    assert sum(p.points for p in session.exec(select(MerchantPool)).all()) == 25
    assert "25 punti questo mese" in client.get(f"/c/{token}").text


# --- /privacy ---

def test_privacy_e_pubblica_e_completa(client):
    resp = client.get("/privacy")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    text = resp.text
    assert "Zernio" in text and "Meta" in text
    assert "cancellazione" in text.lower()
    assert "Garante" in text
    assert 'rel="manifest"' not in text


def test_privacy_non_mostra_la_nota_di_bozza(client):
    """La nota «da far verificare» sta in un commento Jinja: non arriva nemmeno nel sorgente della pagina."""
    assert "bozza" not in client.get("/privacy").text.lower()
