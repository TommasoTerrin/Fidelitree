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
from app.core import crypto
from app.models.models import ZernioSendCounter
from app.services import card_service
from app.services.db_crud import merchant_crud
from tests.conftest import (
    INSTAGRAM_ACCOUNT_ID, INSTAGRAM_HOOK_ID, WEBHOOK_TEST_SECRET, ZERNIO_TEST_KEY, identity_for, login_as,
    make_card,
)


def test_pagina_login(client):
    resp = client.get("/merchant/login")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


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
def test_pagine_merchant_con_identita_non_merchant_303(client, auth_provider, path):
    """Un cookie valido ma di un account non esercente (es. il vecchio cliente): login, non un 403 in JSON."""
    login_as(client, identity_for("sconosciuto@test.it"))
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


def test_settings_mostra_conversione_e_soglie(auth_client, merchant):
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


def test_settings_instagram_collegato_si_chiama_collegato_con_zernio_non_attivo(auth_client, session, merchant):
    """«Attivo» è lo stato del SERVIZIO (approvato, non in pausa): lo stato Instagram si chiama «Collegato con Zernio»."""
    _collega(session, merchant, InstagramStatus.ACTIVE)
    section = _instagram_section(auth_client.get("/merchant/settings").text)

    assert "Collegato con Zernio" in section and "Attivo" not in section
    assert 'data-state="active"' in section  # il valore interno non cambia


def test_settings_instagram_in_attesa_del_dm_non_dice_che_la_funzione_e_attiva(auth_client, session, merchant):
    _collega(session, merchant, InstagramStatus.AWAITING_TEST_DM)
    section = _instagram_section(auth_client.get("/merchant/settings").text)

    assert "il collegamento con Zernio è completo" in section and "è attiva" not in section


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


def test_settings_non_ha_piu_il_qr_del_negozio(auth_client):
    """Via il blocco "QR del negozio" (`/join`) e il suo script: il form delle impostazioni deve restare vivo."""
    text = auth_client.get("/merchant/settings").text
    assert "shop-qr" not in text and "QR del negozio" not in text and "/join" not in text
    assert "qrcode" not in text.lower()
    assert "form.addEventListener('submit'" in text  # lo script non si rompe sul vecchio contenitore del QR


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
    carta = make_card(session, altro, igsid="igsid-altro-cliente")
    assert auth_client.get(f"/merchant/card/{carta.id}/manage").status_code == 404


def test_nessun_riferimento_vecchio_nei_template_merchant():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "app" / "templates" / "merchant"
    for path in root.glob("*.html"):
        text = path.read_text(encoding="utf-8").lower()
        for vecchio in ("ecologi", "tree_threshold", "merchant.mode", "trees_planted"):
            assert vecchio not in text, (path.name, vecchio)


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


def test_pagine_cliente_non_sono_una_pwa(client, card):
    """PWA solo merchant: né manifest né service worker nelle pagine del cliente."""
    token = crypto.card_link_token(card.id, card.link_version)
    for path in (f"/c/{token}", "/c/token-sconosciuto", "/privacy"):
        text = client.get(path).text
        assert 'rel="manifest"' not in text, path
        assert "serviceWorker" not in text, path


def test_download_card_rimossa_e_template_cancellato(client):
    from pathlib import Path
    assert client.get("/download_card").status_code == 404
    template = Path(__file__).resolve().parent.parent / "app" / "templates" / "consumer" / "download.html"
    assert not template.exists()
