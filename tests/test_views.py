"""
Test di rendering delle pagine HTML (Jinja2).
"""

import re
import uuid
from datetime import timedelta

import pytest

from app.core.clock import utc_now
from app.core.crypto import encrypt_secret
from app.core.enums import InstagramStatus
from app.models.models import Card, ZernioSendCounter
from app.services import card_service
from app.services.db_crud import customer_crud, merchant_crud
from tests.conftest import (
    INSTAGRAM_ACCOUNT_ID, INSTAGRAM_HOOK_ID, WEBHOOK_TEST_SECRET, ZERNIO_TEST_KEY, identity_for, login_as,
)


def test_pagina_login(client):
    resp = client.get("/merchant/login")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_pagina_card_del_proprietario(client, card, merchant, customer):
    login_as(client, identity_for(customer.email))
    resp = client.get(f"/card/{card.id}")
    assert resp.status_code == 200
    assert merchant.business_name in resp.text
    assert "qrcode" in resp.text  # container del QR code


def test_pagina_card_inesistente(client, customer):
    login_as(client, identity_for(customer.email))
    resp = client.get(f"/card/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_scanner_richiede_login(client):
    resp = client.get("/merchant/scanner", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/merchant/login"


def test_scanner_con_login(auth_client):
    resp = auth_client.get("/merchant/scanner")
    assert resp.status_code == 200
    assert "html5-qrcode" in resp.text


def test_scanner_accetta_solo_l_uuid_della_carta(auth_client):
    text = auth_client.get("/merchant/scanner").text
    assert "QR non riconosciuto" in text
    assert "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}" in text
    assert 'replace("/card/"' not in text and "startsWith(\"http\")" not in text  # niente più URL del vecchio flusso
    assert "/merchant/card/" in text


def test_gestione_card_richiede_login(client, card):
    resp = client.get(f"/merchant/card/{card.id}/manage", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/merchant/login"


def test_gestione_card_con_login(auth_client, card):
    resp = auth_client.get(f"/merchant/card/{card.id}/manage")
    assert resp.status_code == 200
    assert "Cashback" in resp.text


# --- Frontend merchant (ticket 09) ---

def _prepara_pool(session, merchant, card, points, conversion_enabled=False):
    """Scan reale di `points` tree points sulla carta, con la conversione come richiesto."""
    merchant.conversion_enabled = conversion_enabled
    session.add(merchant)
    session.commit()
    card_service.add_tree_points(session, merchant, card.id, points)


def test_pagina_register_pubblica(client):
    resp = client.get("/merchant/register")
    assert resp.status_code == 200
    assert 'type="email"' in resp.text and 'id="email"' in resp.text
    assert "ecologi" not in resp.text.lower()
    assert "phone_number" not in resp.text
    assert "dopo l'approvazione" in resp.text
    # il telefono c'è ma è facoltativo
    [phone_input] = re.findall(r'<input[^>]*id="contact_phone"[^>]*>', resp.text)
    assert "required" not in phone_input


def test_pagina_login_senza_ecologi_ne_telefono(client):
    resp = client.get("/merchant/login")
    assert "ecologi" not in resp.text.lower()
    assert 'type="email"' in resp.text
    assert 'type="tel"' not in resp.text


def test_settings_richiede_login(client):
    resp = client.get("/merchant/settings", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/merchant/login"


# --- Pagine HTML merchant senza sessione: 303 al login, con la dependency vera (nessun override) ---

MERCHANT_PAGES = ("/merchant/scanner", "/merchant/settings", f"/merchant/card/{uuid.uuid4()}/manage")


def _merchant_con_login(client, session, merchant):
    """Collega il merchant di test al provider `dev` e apre la sessione con un cookie vero."""
    from app.core.auth import dev_user_id
    merchant.auth_user_id = dev_user_id(merchant.email)
    session.add(merchant)
    session.commit()
    return login_as(client, identity_for(merchant.email))


@pytest.mark.parametrize("path", MERCHANT_PAGES)
def test_pagine_merchant_con_cookie_non_valido_303(client, auth_provider, path):
    client.cookies.set("access_token", "spazzatura")
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/merchant/login"


@pytest.mark.parametrize("path", MERCHANT_PAGES)
def test_pagine_merchant_con_identita_non_merchant_303(client, auth_provider, customer, path):
    """Il cookie di un vecchio cliente è valido ma non è un esercente: login, non un 403 in JSON."""
    login_as(client, identity_for(customer.email))
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/merchant/login"


def test_pagine_merchant_con_cookie_vero_200(client, session, auth_provider, merchant, card):
    _merchant_con_login(client, session, merchant)
    assert client.get("/merchant/scanner", follow_redirects=False).status_code == 200
    assert client.get("/merchant/settings", follow_redirects=False).status_code == 200
    assert client.get(f"/merchant/card/{card.id}/manage", follow_redirects=False).status_code == 200


def test_gestione_carta_altrui_con_cookie_vero_404(client, session, auth_provider, merchant, card):
    altro = merchant_crud.create_merchant(session, {
        "business_name": "Altro Negozio", "email": "altro@test.it", "is_approved": True,
    })
    _merchant_con_login(client, session, altro)
    assert client.get(f"/merchant/card/{card.id}/manage", follow_redirects=False).status_code == 404


def test_le_api_merchant_senza_cookie_restano_401(client):
    resp = client.get("/api/merchant/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Non autenticato"


def test_settings_mostra_conversione_soglie_e_qr(auth_client, merchant):
    resp = auth_client.get("/merchant/settings")
    assert resp.status_code == 200
    text = resp.text
    assert 'id="conversion_enabled"' in text and "checked" in text
    assert f'value="{merchant.conversion_threshold}"' in text
    assert 'value="2.00"' in text
    assert "Approvato" in text and "In attesa di approvazione" not in text
    # soglie di default 100/300/600
    for livello, valore in (("bronze", 100), ("silver", 300), ("gold", 600)):
        assert f'id="threshold-{livello}">{valore}<' in text
    assert f"/join/{merchant.id}" in text
    assert "qrcode" in text
    lower = text.lower()
    # la sezione Instagram parla della chiave Zernio del merchant: qui contano solo i dettagli interni degli alberi
    assert "monthly" not in lower and not re.search(r"\bcap\b", lower)
    assert "ecologi" not in lower


def test_settings_soglie_con_override_admin(auth_client, session, merchant):
    merchant_crud.update_merchant(session, merchant, {
        "bronze_threshold": 10, "silver_threshold": 20, "gold_threshold": 30,
    })
    text = auth_client.get("/merchant/settings").text
    for livello, valore in (("bronze", 10), ("silver", 20), ("gold", 30)):
        assert f'id="threshold-{livello}">{valore}<' in text


def test_settings_merchant_non_approvato(auth_client, session, merchant):
    merchant_crud.update_merchant(session, merchant, {"is_approved": False})
    text = auth_client.get("/merchant/settings").text
    assert "In attesa di approvazione" in text
    assert "Approvato ✅" not in text


def test_settings_conversione_disattivata_non_spunta_l_interruttore(auth_client, session, merchant):
    merchant_crud.update_merchant(session, merchant, {"conversion_enabled": False})
    text = auth_client.get("/merchant/settings").text
    [checkbox] = re.findall(r'<input[^>]*id="conversion_enabled"[^>]*>', text)
    assert "checked" not in checkbox


# --- sezione Instagram delle impostazioni: uno stato per volta ---

def _instagram_section(text: str) -> str:
    """Solo l'HTML della sezione Instagram (dal tag `<section id="instagram-section"` alla sua chiusura)."""
    start = text.index('<section id="instagram-section"')
    return text[start:text.index("</section>", start)]


def _collega(session, merchant, status, **extra):
    """Porta il merchant di test in uno stato Instagram (chiave e secret cifrati come dopo l'onboarding)."""
    merchant_crud.update_merchant(session, merchant, {
        "zernio_api_key_enc": encrypt_secret(ZERNIO_TEST_KEY),
        "zernio_account_id": INSTAGRAM_ACCOUNT_ID,
        "instagram_username": "bar_demo",
        "webhook_hook_id": INSTAGRAM_HOOK_ID,
        "webhook_secret_enc": encrypt_secret(WEBHOOK_TEST_SECRET),
        "persistent_menu_set": True,
        "instagram_status": status,
        **extra,
    })


def test_settings_instagram_non_collegato_mostra_istruzioni_e_campo_chiave(auth_client):
    section = _instagram_section(auth_client.get("/merchant/settings").text)

    assert 'data-state="not_connected"' in section
    [field] = re.findall(r'<input[^>]*id="zernio-key"[^>]*>', section)
    assert 'type="password"' in field and 'autocomplete="off"' in field
    assert "Zernio" in section and "Business" in section
    assert 'id="account-picker"' in section and "data-autoload" not in section
    assert "Scollega" not in section and "Aggiorna" not in section


def test_settings_instagram_con_chiave_salvata_carica_gli_account(auth_client, session, merchant):
    merchant_crud.update_merchant(session, merchant, {"zernio_api_key_enc": encrypt_secret(ZERNIO_TEST_KEY)})
    section = _instagram_section(auth_client.get("/merchant/settings").text)

    assert 'data-state="not_connected"' in section and "data-autoload" in section
    assert "…ef56" in section


def test_settings_instagram_in_attesa_del_dm_di_prova(auth_client, session, merchant):
    _collega(session, merchant, InstagramStatus.AWAITING_TEST_DM)
    section = _instagram_section(auth_client.get("/merchant/settings").text)

    assert 'data-state="awaiting_test_dm"' in section
    assert "Scrivi CARTA" in section and "un altro profilo" in section
    assert 'id="btn-instagram-refresh"' in section and "Aggiorna" in section
    assert "Scollega" in section  # senza il DM di prova (es. ManyChat) si deve poter uscire
    assert 'id="zernio-key"' not in section


def test_settings_instagram_attivo_mostra_account_chiave_mascherata_e_quota(auth_client, session, merchant):
    _collega(session, merchant, InstagramStatus.ACTIVE)
    session.add(ZernioSendCounter(
        quota_scope=f"account:{INSTAGRAM_ACCOUNT_ID}", period=utc_now().strftime("%Y-%m"), sent=2500,
    ))
    session.commit()
    section = _instagram_section(auth_client.get("/merchant/settings").text)

    assert 'data-state="active"' in section
    assert "@bar_demo" in section and "…ef56" in section
    assert 'id="quota-bar"' in section and "width: 25%" in section and "2500" in section
    assert "Scollega" in section and 'id="btn-instagram-disconnect"' in section
    assert 'id="zernio-key"' not in section and "data-warning" not in section


def test_settings_instagram_chiave_non_valida_banner_rosso_e_nuovo_campo(auth_client, session, merchant):
    _collega(session, merchant, InstagramStatus.KEY_INVALID)
    section = _instagram_section(auth_client.get("/merchant/settings").text)

    assert 'data-state="key_invalid"' in section
    assert 'data-warning="key_invalid"' in section and "bg-red-" in section
    assert "Zernio ha rifiutato la chiave" in section
    assert 'id="zernio-key"' in section and "data-autoload" not in section


def test_settings_instagram_mostra_gli_avvisi(auth_client, session, merchant):
    _collega(
        session, merchant, InstagramStatus.ACTIVE,
        persistent_menu_set=False, standby_detected_at=utc_now() - timedelta(hours=2),
    )
    session.add(ZernioSendCounter(
        quota_scope=f"account:{INSTAGRAM_ACCOUNT_ID}", period=utc_now().strftime("%Y-%m"), sent=8000,
    ))
    session.commit()
    section = _instagram_section(auth_client.get("/merchant/settings").text)

    for code in ("menu", "standby", "quota"):
        assert f'data-warning="{code}"' in section
    assert "ManyChat" in section and "80%" in section


def test_settings_instagram_senza_username_non_scrive_none(auth_client, session, merchant):
    for status in (InstagramStatus.AWAITING_TEST_DM, InstagramStatus.ACTIVE):
        _collega(session, merchant, status, instagram_username=None)
        section = _instagram_section(auth_client.get("/merchant/settings").text)
        assert f'data-state="{status.value}"' in section and "@None" not in section and "@" not in section


def test_settings_instagram_non_espone_segreti_e_scappa_l_username(auth_client, session, merchant):
    _collega(session, merchant, InstagramStatus.ACTIVE, instagram_username="<script>alert(1)</script>")
    text = auth_client.get("/merchant/settings").text

    for secret in (ZERNIO_TEST_KEY, WEBHOOK_TEST_SECRET, INSTAGRAM_HOOK_ID):
        assert secret not in text
    assert "<script>alert(1)</script>" not in text and "&lt;script&gt;" in text


def test_settings_mantiene_il_qr_join_fino_al_ticket_09(auth_client):
    text = auth_client.get("/merchant/settings").text
    assert 'id="shop-qrcode"' in text and "/join/" in text


def test_gestione_card_mostra_pool_del_mese(auth_client, session, merchant, card):
    _prepara_pool(session, merchant, card, 120)  # soglie default 100/300/600 → bronzo
    text = auth_client.get(f"/merchant/card/{card.id}/manage").text
    assert "Pool del negozio" in text
    assert "🥉 Bronzo" in text
    assert "120 punti questo mese" in text
    assert "Mancano 180 punti al livello Argento" in text
    assert "sta piantando 1 albero" in text


def test_gestione_card_senza_livello(auth_client, card):
    text = auth_client.get(f"/merchant/card/{card.id}/manage").text
    assert "Nessun livello" in text
    assert "sta piantando 0 alberi" in text


def test_gestione_card_senza_trees_planted(auth_client, card):
    text = auth_client.get(f"/merchant/card/{card.id}/manage").text.lower()
    assert "trees_planted" not in text
    assert "alberi piantati" not in text
    assert "ecologi" not in text and "tree_threshold" not in text


def test_gestione_card_cashback_anche_con_conversione_disattivata(auth_client, session, merchant, card):
    merchant_crud.update_merchant(session, merchant, {"conversion_enabled": False})
    text = auth_client.get(f"/merchant/card/{card.id}/manage").text
    assert "AGGIUNGI CASHBACK" in text and 'id="cb-input"' in text
    assert f"Ogni {merchant.conversion_threshold} punti" not in text


def test_gestione_card_con_conversione_attiva_mostra_la_regola(auth_client, merchant, card):
    text = auth_client.get(f"/merchant/card/{card.id}/manage").text
    assert f"Ogni {merchant.conversion_threshold} punti → € 2.00 di cashback" in text


def test_gestione_card_di_un_altro_merchant_404(auth_client, session):
    altro = merchant_crud.create_merchant(session, {
        "business_name": "Altro", "email": "altro@test.it", "is_approved": True,
    })
    cliente = customer_crud.create_customer(session, "altro-cliente@test.it")
    carta = Card(merchant_id=altro.id, customer_id=cliente.id)
    session.add(carta)
    session.commit()
    assert auth_client.get(f"/merchant/card/{carta.id}/manage").status_code == 404


def test_nessun_riferimento_vecchio_nei_template_merchant():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "app" / "templates" / "merchant"
    for path in root.glob("*.html"):
        text = path.read_text(encoding="utf-8").lower()
        for vecchio in ("ecologi", "tree_threshold", "merchant.mode", "trees_planted"):
            assert vecchio not in text, (path.name, vecchio)


# --- Frontend cliente e PWA (ticket 10) ---

def _accedi(client, customer):
    login_as(client, identity_for(customer.email))


def test_login_cliente_ha_il_campo_email_e_il_promemoria_dev(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "dev")
    resp = client.get("/customer/login")
    assert resp.status_code == 200
    assert 'type="email"' in resp.text and 'id="email"' in resp.text
    assert 'inputmode="numeric"' in resp.text  # campo del codice a 6 cifre
    assert "codice di sviluppo" in resp.text and "000000" in resp.text


def test_login_cliente_senza_promemoria_fuori_da_dev(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "supabase")
    resp = client.get("/customer/login")
    assert resp.status_code == 200
    assert "codice di sviluppo" not in resp.text and "000000" not in resp.text


def test_login_cliente_riporta_il_next_sicuro(client):
    assert 'data-next="/join/7"' in client.get("/customer/login?next=/join/7").text
    assert 'data-next="/wallet"' in client.get("/customer/login?next=https://evil.example").text


def test_join_anonimo_mostra_negozio_e_link_al_login(client, merchant):
    resp = client.get(f"/join/{merchant.id}")
    assert resp.status_code == 200
    assert merchant.business_name in resp.text
    assert f"Entra nel progetto alberi di {merchant.business_name}" in resp.text
    assert f"/customer/login?next=/join/{merchant.id}" in resp.text
    assert "/api/customer/join/" not in resp.text  # nessuna chiamata di iscrizione se anonimo


def test_join_da_loggato_chiama_l_iscrizione(client, merchant, customer):
    _accedi(client, customer)
    resp = client.get(f"/join/{merchant.id}")
    assert resp.status_code == 200
    assert "/api/customer/join/" in resp.text
    assert "/customer/login?next=" not in resp.text


def test_join_negozio_inesistente_404_amichevole(client):
    resp = client.get("/join/9999")
    assert resp.status_code == 404
    assert "text/html" in resp.headers["content-type"]
    assert "Negozio non trovato" in resp.text


def test_wallet_anonimo_redirect_al_login(client):
    resp = client.get("/wallet", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/customer/login?next=/wallet")


def test_wallet_con_due_carte(client, session, merchant, customer, card):
    altro = merchant_crud.create_merchant(session, {
        "business_name": "Panificio Rosa", "email": "rosa@test.it", "is_approved": True,
    })
    seconda = Card(merchant_id=altro.id, customer_id=customer.id)
    session.add(seconda)
    session.commit()
    session.refresh(seconda)
    _accedi(client, customer)

    resp = client.get("/wallet")
    assert resp.status_code == 200
    assert merchant.business_name in resp.text and "Panificio Rosa" in resp.text
    assert f"/card/{card.id}" in resp.text and f"/card/{seconda.id}" in resp.text
    assert "Inquadra il QR di un negozio" not in resp.text
    assert "/customer/logout" in resp.text


def test_wallet_mostra_livello_e_barra_del_negozio(client, session, merchant, customer, card):
    _prepara_pool(session, merchant, card, 150)
    _accedi(client, customer)
    text = client.get("/wallet").text
    assert "🥉" in text and "Bronzo" in text
    assert "mancano 150 punti al livello Argento" in text


def test_wallet_vuoto_invita_a_inquadrare_il_qr(client, customer):
    _accedi(client, customer)
    resp = client.get("/wallet")
    assert resp.status_code == 200
    assert "Inquadra il QR di un negozio per aggiungere la tua prima carta" in resp.text


def test_carta_con_pool_bronzo(client, session, merchant, customer, card):
    _prepara_pool(session, merchant, card, 150)  # soglie default 100/300/600
    _accedi(client, customer)
    text = client.get(f"/card/{card.id}").text
    assert "Il progetto del negozio" in text
    assert "🥉 Bronzo" in text
    assert "150 punti questo mese" in text
    assert "Ancora 150 punti al livello Argento" in text  # points_to_next = 150
    assert "Insieme questo mese stiamo piantando 1 albero 🌳" in text
    assert "Livello massimo" not in text
    assert "Hai già piantato" not in text


def test_carta_senza_livello(client, card, customer):
    _accedi(client, customer)
    text = client.get(f"/card/{card.id}").text
    assert "Nessun livello" in text
    assert "Ancora 100 punti al livello Bronzo" in text
    assert "stiamo piantando" not in text


def test_carta_con_pool_oro_mostra_livello_massimo(client, session, merchant, customer, card):
    _prepara_pool(session, merchant, card, 700)
    _accedi(client, customer)
    text = client.get(f"/card/{card.id}").text
    assert "🥇 Oro" in text
    assert "Livello massimo raggiunto!" in text
    assert "Insieme questo mese stiamo piantando 5 alberi 🌳" in text
    assert "al livello" not in text  # nessun livello successivo


def test_carta_con_conversione_attiva_mostra_i_punti_mancanti(client, session, merchant, customer, card):
    merchant_crud.update_merchant(session, merchant, {"conversion_threshold": 50})
    _prepara_pool(session, merchant, card, 20, conversion_enabled=True)
    _accedi(client, customer)
    text = client.get(f"/card/{card.id}").text
    assert "Ancora 30 punti per € 2.00 di cashback" in text


def test_carta_con_conversione_disattivata_senza_barra_personale(client, session, merchant, customer, card):
    _prepara_pool(session, merchant, card, 20, conversion_enabled=False)
    _accedi(client, customer)
    text = client.get(f"/card/{card.id}").text
    assert "di cashback" not in text and 'id="conversion-note"' not in text
    assert "Cashback" in text  # il cashback resta sempre visibile


def test_carta_banner_test_solo_per_merchant_di_test(client, session, merchant, customer, card):
    _accedi(client, customer)
    merchant_crud.update_merchant(session, merchant, {"type": "free"})
    assert "Carta di Test" not in client.get(f"/card/{card.id}").text
    merchant_crud.update_merchant(session, merchant, {"type": "test"})
    assert "Carta di Test" in client.get(f"/card/{card.id}").text


def test_manifest_valido(client):
    import json
    resp = client.get("/static/manifest.webmanifest")
    assert resp.status_code == 200
    manifest = json.loads(resp.text)
    assert manifest["name"] == "Fidelitree"
    assert manifest["start_url"] == "/merchant/scanner"
    assert manifest["scope"] == "/merchant/"
    assert manifest["start_url"].startswith(manifest["scope"])
    assert manifest["description"] == "Lo scanner Fidelitree del tuo negozio"
    assert manifest["display"] == "standalone"
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes
    for icon in manifest["icons"]:
        assert client.get(icon["src"]).status_code == 200


def test_service_worker_servito_dalla_radice_con_scope_merchant(client):
    resp = client.get("/sw.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]
    assert resp.headers["service-worker-allowed"] == "/merchant/"
    # nessuna cache delle pagine autenticate né delle API: solo la shell statica
    assert "/api/" not in resp.text and '"/wallet"' not in resp.text and '"/card' not in resp.text


def test_pagine_merchant_includono_manifest_e_service_worker(auth_client, client, card):
    for path in (
        "/merchant/scanner", "/merchant/settings", f"/merchant/card/{card.id}/manage",
        "/merchant/login", "/merchant/register",
    ):
        text = client.get(path).text
        assert 'rel="manifest"' in text, path
        assert 'name="theme-color"' in text, path
        assert "serviceWorker" in text, path
        assert "scope: '/merchant/'" in text, path


def test_pagine_cliente_non_sono_una_pwa(client, merchant, customer, card):
    """PWA solo merchant: né manifest né service worker nelle pagine del cliente (nemmeno nelle vecchie)."""
    _accedi(client, customer)
    for path in ("/wallet", f"/card/{card.id}", f"/join/{merchant.id}", "/customer/login", "/privacy"):
        text = client.get(path).text
        assert 'rel="manifest"' not in text, path
        assert "serviceWorker" not in text, path


def test_download_card_rimossa_e_template_cancellato(client):
    from pathlib import Path
    assert client.get("/download_card").status_code == 404
    template = Path(__file__).resolve().parent.parent / "app" / "templates" / "consumer" / "download.html"
    assert not template.exists()
