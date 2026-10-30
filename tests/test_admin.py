"""
Dashboard admin `/admin` (ticket 13): accesso con `ADMIN_SECRET_KEY`, lista dei merchant, azioni di stato e reset
della password. SQLite in-memory: nessun test apre l'engine dell'app né fa chiamate di rete. Il provider `local`
usa la sessione di test (fixture `local_auth`).
"""

import logging
import re
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import select

from app.core.auth import LOGIN_MAX_FAILURES, login_throttle
from app.core.clock import utc_now
from app.core.config import settings
from app.core.dependencies import ADMIN_COOKIE
from app.core.enums import InstagramStatus
from app.core.security import create_admin_session_token, create_jwt_token
from app.main import app
from app.models.models import AuthCredential, Card, Merchant
from app.services import card_service, merchant_service
from app.services.db_crud import merchant_crud
from tests.conftest import (
    INSTAGRAM_ACCOUNT_ID, INSTAGRAM_HOOK_ID, WEBHOOK_TEST_SECRET, ZERNIO_TEST_KEY, make_card,
)

ORIGIN = {"Origin": "http://testserver"}  # host del TestClient
PASSWORD = "password-segreta-1"
ACTIONS = ("approve", "pause", "resume", "reset-password")


# --- helper ---

def admin_login(client, password=None, headers=None):
    """POST del form di login admin (con l'`Origin` giusto, salvo `headers`), senza seguire il redirect."""
    return client.post(
        "/admin/login", data={"password": settings.ADMIN_SECRET_KEY if password is None else password},
        headers=ORIGIN if headers is None else headers, follow_redirects=False,
    )


def post_action(client, merchant_id, action, headers=ORIGIN):
    """POST di un'azione della dashboard."""
    return client.post(f"/admin/api/merchants/{merchant_id}/{action}", headers=headers)


def new_merchant(session, name="Bar Sole", email=None, **fields):
    """
    Merchant di test; di default in attesa (non approvato). `created_at` non è tra i campi che `create_merchant`
    accetta (lo mette il modello): se serve una data precisa si imposta dopo.
    """
    email = email or f"{re.sub(r'[^a-z]', '', name.lower())}@test.it"
    created_at = fields.pop("created_at", None)
    merchant = merchant_crud.create_merchant(session, {"business_name": name, "email": email, **fields})
    if created_at is not None:
        merchant.created_at = created_at
        session.add(merchant)
        session.commit()
        session.refresh(merchant)
    return merchant


def get_row(client, merchant_id):
    """La riga di un merchant dalla lista (con la sessione admin del client)."""
    rows = client.get("/admin/api/merchants").json()["merchants"]
    return next(r for r in rows if r["id"] == merchant_id)


@pytest.fixture()
def admin_client(client):
    """Client con la sessione admin già aperta (cookie `admin_session`)."""
    assert admin_login(client).status_code == 303
    return client


def set_cookie_headers(response) -> list[str]:
    return response.headers.get_list("set-cookie")


# --- accesso: login ---

def test_login_giusto_imposta_il_cookie_e_rimanda_alla_dashboard(client):
    response = admin_login(client)

    assert response.status_code == 303 and response.headers["location"] == "/admin"
    [cookie] = set_cookie_headers(response)
    assert cookie.startswith(f"{ADMIN_COOKIE}=")
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Path=/admin" in cookie and "Max-Age=43200" in cookie   # 12 ore, solo sotto /admin
    assert "Secure" not in cookie                                 # solo con ENVIRONMENT=production
    assert settings.ADMIN_SECRET_KEY not in cookie                # il cookie è un JWT, non la chiave


def test_cookie_secure_in_produzione(client, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    [cookie] = set_cookie_headers(admin_login(client))
    assert "Secure" in cookie


def test_login_con_password_sbagliata_da_401_senza_cookie(client):
    response = admin_login(client, "password-sbagliata")

    assert response.status_code == 401 and response.json() == {"detail": "Password non valida"}
    assert set_cookie_headers(response) == []
    assert client.get("/admin/api/merchants").status_code == 401


def test_login_senza_il_campo_password_e_un_errore_401_non_un_422(client):
    response = client.post("/admin/login", data={}, headers=ORIGIN, follow_redirects=False)
    assert response.status_code == 401


def test_sesto_tentativo_di_login_e_429_anche_con_la_password_giusta(client):
    for attempt in range(1, LOGIN_MAX_FAILURES + 1):
        response = admin_login(client, f"sbagliata-{attempt}")
        assert response.status_code == 401
        if attempt == 3:
            assert "Attenzione" in response.json()["detail"]
        if attempt == LOGIN_MAX_FAILURES:
            assert "Accesso sospeso" in response.json()["detail"]

    blocked = admin_login(client)  # password giusta, ma l'accesso è sospeso

    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert set_cookie_headers(blocked) == []
    assert "X-Admin-Key" in blocked.json()["detail"] and "founder" not in blocked.json()["detail"]


def test_il_freno_si_scioglie_dopo_la_finestra(client, monkeypatch):
    for attempt in range(LOGIN_MAX_FAILURES):
        admin_login(client, f"sbagliata-{attempt}")
    assert admin_login(client).status_code == 429

    later = utc_now() + timedelta(minutes=16)
    monkeypatch.setattr("app.routes.admin.utc_now", lambda: later)

    assert admin_login(client).status_code == 303


def test_un_accesso_riuscito_azzera_il_contatore(client):
    for attempt in range(LOGIN_MAX_FAILURES - 1):
        assert admin_login(client, f"sbagliata-{attempt}").status_code == 401
    assert admin_login(client).status_code == 303

    for attempt in range(LOGIN_MAX_FAILURES):  # altri 5 errori ammessi: nessun 429 prima del sesto
        assert admin_login(client, f"altra-{attempt}").status_code == 401


def test_il_freno_admin_non_blocca_il_login_dei_merchant_e_viceversa(client, auth_provider):
    for attempt in range(LOGIN_MAX_FAILURES):
        admin_login(client, f"sbagliata-{attempt}")
    for _ in range(LOGIN_MAX_FAILURES):
        client.post("/merchant/login", data={"email": "x@y.it", "password": "no"}, follow_redirects=False)

    assert admin_login(client).status_code == 429
    assert client.post("/merchant/login", data={"email": "x@y.it", "password": "no"}, follow_redirects=False).status_code == 429
    login_throttle.clear("admin")
    assert admin_login(client).status_code == 303  # azzerato quello admin, l'altro resta bloccato
    assert client.post("/merchant/login", data={"email": "x@y.it", "password": "no"}, follow_redirects=False).status_code == 429


def test_chiave_admin_vuota_non_fa_entrare_nessuno(client, monkeypatch):
    """`.env.example` lascia `ADMIN_SECRET_KEY=` vuota: una password vuota o un header vuoto non devono bastare."""
    monkeypatch.setattr(settings, "ADMIN_SECRET_KEY", "")

    assert admin_login(client, "").status_code == 401
    assert client.get("/admin/api/merchants", headers={"X-Admin-Key": ""}).status_code == 401
    assert client.get("/admin", headers={"X-Admin-Key": ""}, follow_redirects=False).status_code == 303


def test_vecchia_api_admin_con_chiave_vuota_o_errata_resta_chiusa(client, monkeypatch, admin_headers):
    """`require_admin_key` usa `admin_key_matches`: con chiave vuota un header vuoto non apre `/api/merchant/*`."""
    assert client.get("/api/merchant/", headers={"X-Admin-Key": "sbagliata"}).status_code == 403
    assert client.get("/api/merchant/", headers={"X-Admin-Key": ""}).status_code == 403

    monkeypatch.setattr(settings, "ADMIN_SECRET_KEY", "")
    assert client.get("/api/merchant/", headers={"X-Admin-Key": ""}).status_code == 403
    assert client.get("/api/merchant/").status_code == 403


def test_login_con_origine_estranea_o_assente_e_403(client):
    for headers in ({"Origin": "https://evil.example"}, {"Origin": "null"}, {}, {"Referer": "https://evil.example/x"}):
        response = admin_login(client, headers=headers)
        assert response.status_code == 403 and set_cookie_headers(response) == []
    assert admin_login(client, headers={"Referer": "http://testserver/admin/login"}).status_code == 303


def test_l_origine_si_controlla_prima_del_freno(client):
    """Un POST cross-site non consuma i tentativi di login."""
    for _ in range(10):
        assert admin_login(client, "sbagliata", headers={"Origin": "https://evil.example"}).status_code == 403
    assert admin_login(client).status_code == 303


def test_la_password_non_finisce_nei_log(client, caplog):
    caplog.set_level(logging.DEBUG)
    admin_login(client, "tentativo-sbagliato-xyz")
    admin_login(client)

    assert "tentativo-sbagliato-xyz" not in caplog.text and settings.ADMIN_SECRET_KEY not in caplog.text


# --- accesso: sessione, header, logout ---

def test_pagine_html_senza_sessione_rimandano_al_login(client):
    response = client.get("/admin", follow_redirects=False)

    assert response.status_code == 303 and response.headers["location"] == "/admin/login"


def test_api_senza_sessione_rispondono_401(client, session):
    merchant = new_merchant(session)

    assert client.get("/admin/api/merchants").status_code == 401
    for action in ACTIONS:
        assert post_action(client, merchant.id, action).status_code == 401
        assert post_action(client, 99999, action).status_code == 401   # l'autenticazione viene prima del 404


def test_cookie_manomesso_scaduto_o_di_un_merchant_non_vale(client, session):
    merchant = new_merchant(session)
    valid = create_admin_session_token()
    bad_cookies = {
        "manomesso": valid[:-4] + ("AAAA" if not valid.endswith("AAAA") else "BBBB"),
        "scaduto": create_jwt_token({"role": "admin"}, expires_delta=timedelta(seconds=-10)),
        "spazzatura": "non-un-jwt",
        # stessa chiave di firma ma sessione di un merchant: senza `role=admin` non vale
        "token merchant": create_jwt_token({"sub": "uid-1", "email": "a@b.it", "ver": 1}),
    }
    for label, value in bad_cookies.items():
        client.cookies.clear()
        client.cookies.set(ADMIN_COOKIE, value, path="/admin")
        assert client.get("/admin", follow_redirects=False).status_code == 303, label
        assert client.get("/admin/api/merchants").status_code == 401, label
        assert post_action(client, merchant.id, "approve").status_code == 401, label
    assert session.get(Merchant, merchant.id).is_approved is False


def test_la_sessione_admin_non_vale_come_sessione_merchant(admin_client):
    token = create_admin_session_token()
    admin_client.cookies.set("access_token", token)

    assert admin_client.get("/api/merchant/me").status_code == 401
    assert admin_client.get("/merchant/scanner", follow_redirects=False).status_code == 303


def test_header_admin_key_valido_accettato_errato_rifiutato(client, session, admin_headers):
    merchant = new_merchant(session)

    assert client.get("/admin/api/merchants", headers=admin_headers).status_code == 200
    assert client.get("/admin", headers=admin_headers, follow_redirects=False).status_code == 200
    assert client.get("/admin/api/merchants", headers={"X-Admin-Key": "sbagliata"}).status_code == 401
    assert client.get("/admin/api/merchants", headers={"X-Admin-Key": ""}).status_code == 401
    # per i POST con header corretto non serve l'Origin (curl, script)
    assert post_action(client, merchant.id, "approve", headers=admin_headers).status_code == 200
    assert post_action(client, merchant.id, "approve", headers={"X-Admin-Key": "sbagliata", **ORIGIN}).status_code == 401


def test_header_errato_e_rifiutato_anche_con_un_cookie_valido(admin_client, session):
    merchant = new_merchant(session)

    response = post_action(admin_client, merchant.id, "approve", headers={"X-Admin-Key": "sbagliata", **ORIGIN})

    assert response.status_code == 401
    assert admin_client.get("/admin/api/merchants", headers={"X-Admin-Key": "sbagliata"}).status_code == 401
    assert session.get(Merchant, merchant.id).is_approved is False


def test_la_vecchia_api_admin_resta_com_era(client, session, admin_headers):
    """`require_admin_key` (403 senza header, stesso esito di prima) protegge ancora `/api/merchant/*`; il cookie della dashboard non la apre."""
    assert admin_login(client).status_code == 303
    assert client.get("/api/merchant/").status_code == 403
    assert client.get("/api/merchant/", headers=admin_headers).status_code == 200


def test_logout_cancella_il_cookie_con_lo_stesso_path(admin_client):
    response = admin_client.get("/admin/logout", follow_redirects=False)

    assert response.status_code == 303 and response.headers["location"] == "/admin/login"
    [cookie] = set_cookie_headers(response)
    assert cookie.startswith(f"{ADMIN_COOKIE}=") and "Path=/admin" in cookie and "Max-Age=0" in cookie
    assert admin_client.get("/admin/api/merchants").status_code == 401


def test_pagina_di_login_200_e_con_sessione_valida_rimanda_alla_dashboard(client):
    page = client.get("/admin/login")
    assert page.status_code == 200 and 'name="password"' in page.text and 'action="/admin/login"' in page.text

    admin_login(client)
    redirect = client.get("/admin/login", follow_redirects=False)
    assert redirect.status_code == 303 and redirect.headers["location"] == "/admin"


def test_risposte_admin_senza_cache_e_non_indicizzabili(admin_client, session):
    merchant = new_merchant(session)
    responses = [
        admin_client.get("/admin/login", follow_redirects=False),
        admin_client.get("/admin"),
        admin_client.get("/admin/api/merchants"),
        post_action(admin_client, merchant.id, "approve"),
        post_action(admin_client, merchant.id, "pause"),
    ]
    for response in responses:
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["X-Robots-Tag"] == "noindex"
        # `no-referrer` farebbe mandare `Origin: null` ai POST e il controllo CSRF li rifiuterebbe tutti
        assert response.headers["Referrer-Policy"] == "same-origin"


# --- CSRF: Origin sui POST con sessione a cookie ---

def test_post_con_cookie_richiede_un_origin_del_nostro_host(admin_client, session):
    merchant = new_merchant(session)
    rejected = (
        {"Origin": "https://evil.example"}, {"Origin": "null"}, {}, {"Referer": "https://evil.example/admin"},
        {"Origin": "http://testserver.evil.example"},
    )
    for headers in rejected:
        for action in ACTIONS:
            assert post_action(admin_client, merchant.id, action, headers=headers).status_code == 403, (headers, action)
    assert session.get(Merchant, merchant.id).is_approved is False and not session.exec(select(AuthCredential)).all()

    assert post_action(admin_client, merchant.id, "approve", headers={"Referer": "http://testserver/admin"}).status_code == 200
    assert post_action(admin_client, merchant.id, "pause", headers=ORIGIN).status_code == 200


# --- lista ---

def test_lista_vuota(admin_client):
    assert admin_client.get("/admin/api/merchants").json() == {"merchants": []}


def test_lista_dai_piu_recenti_con_stato_del_servizio(admin_client, session):
    now = utc_now()
    pending = new_merchant(session, "Pending", created_at=now - timedelta(days=3))
    active = new_merchant(session, "Attivo", is_approved=True, created_at=now - timedelta(days=1))
    paused = new_merchant(session, "Pausa", is_approved=True, is_paused=True, created_at=now - timedelta(days=2))
    # un flag di pausa su un negozio non approvato non conta: resta «in attesa»
    ghost = new_merchant(session, "Fantasma", is_paused=True, created_at=now - timedelta(days=4))

    rows = admin_client.get("/admin/api/merchants").json()["merchants"]

    assert [r["id"] for r in rows] == [active.id, paused.id, pending.id, ghost.id]
    assert [r["service_state"] for r in rows] == ["active", "paused", "pending", "pending"]
    assert rows[0]["business_name"] == "Attivo" and rows[0]["email"] == active.email
    assert rows[0]["contact_phone"] is None and rows[0]["created_at"]


def test_lista_a_parita_di_iscrizione_vince_l_id_piu_alto(admin_client, session):
    same = utc_now() - timedelta(hours=1)
    first = new_merchant(session, "Primo", created_at=same)
    second = new_merchant(session, "Secondo", created_at=same)

    ids = [r["id"] for r in admin_client.get("/admin/api/merchants").json()["merchants"]]

    assert ids == [second.id, first.id]


def test_lista_con_instagram_collegato_mostra_stato_carte_e_punti_del_mese(admin_client, session, instagram_merchant):
    now = utc_now()
    first, second = make_card(session, instagram_merchant, "igsid-a"), make_card(session, instagram_merchant, "igsid-b")
    card_service.add_tree_points(session, instagram_merchant, first.id, 7, now=now)
    card_service.add_tree_points(session, instagram_merchant, second.id, 5, now=now)
    card_service.add_tree_points(session, instagram_merchant, first.id, 11, now=now - timedelta(days=40))  # mese scorso
    other = new_merchant(session, "Senza carte", is_approved=True)

    row = get_row(admin_client, instagram_merchant.id)

    assert row["instagram_status"] == "active" and row["instagram_username"] == "bar_demo"
    assert row["cards_count"] == 2 and row["month_points"] == 12     # 7 + 5, i punti del mese scorso non contano
    assert row["service_state"] == "active" and row["business_name"] == "Bar Demo"
    empty = get_row(admin_client, other.id)
    assert (empty["cards_count"], empty["month_points"], empty["instagram_status"]) == (0, 0, "not_connected")


@pytest.mark.parametrize("status", list(InstagramStatus))
def test_lista_riporta_ogni_stato_instagram(admin_client, session, status):
    merchant = new_merchant(session)
    merchant_crud.update_merchant(session, merchant, {"instagram_status": status})

    assert get_row(admin_client, merchant.id)["instagram_status"] == status.value


def test_lista_non_contiene_segreti(admin_client, session, instagram_merchant, local_auth):
    """Controlla i VALORI veri (chiave cifrata, secret, hook_id, hash, id del provider), non solo i nomi dei campi."""
    identity = local_auth.sign_up("bar@test.it", PASSWORD)
    instagram_merchant.auth_user_id = identity.user_id
    session.add(instagram_merchant)
    session.commit()
    make_card(session, instagram_merchant)
    credential = session.exec(select(AuthCredential)).one()
    forbidden = [
        instagram_merchant.zernio_api_key_enc, instagram_merchant.webhook_secret_enc, instagram_merchant.webhook_hook_id,
        ZERNIO_TEST_KEY, WEBHOOK_TEST_SECRET, INSTAGRAM_HOOK_ID, INSTAGRAM_ACCOUNT_ID, "prof-1",
        credential.password_hash, credential.user_id, PASSWORD, settings.ADMIN_SECRET_KEY, settings.JWT_SECRET_KEY,
        settings.ENCRYPTION_KEY,
    ]

    response = admin_client.get("/admin/api/merchants")

    assert response.status_code == 200
    for secret in forbidden:
        assert secret not in response.text
    [row] = response.json()["merchants"]
    assert set(row) == {
        "id", "business_name", "email", "contact_phone", "created_at", "service_state", "instagram_status",
        "instagram_username", "cards_count", "month_points", "can_reset_password",
    }
    assert row["can_reset_password"] is True


def test_lista_al_massimo_200_righe_le_piu_recenti(admin_client, session):
    base = utc_now() - timedelta(days=30)
    session.add_all(
        Merchant(business_name=f"Negozio {i}", email=f"m{i}@test.it", created_at=base + timedelta(minutes=i))
        for i in range(205)
    )
    session.commit()

    rows = admin_client.get("/admin/api/merchants").json()["merchants"]

    assert len(rows) == 200
    assert rows[0]["business_name"] == "Negozio 204" and rows[-1]["business_name"] == "Negozio 5"


def test_lista_usa_poche_query_non_una_per_merchant(admin_client, session):
    for i in range(30):
        merchant = new_merchant(session, f"Negozio {i}", email=f"n{i}@test.it", is_approved=True)
        make_card(session, merchant, igsid=f"igsid-{i}")
    statements = []
    engine = session.get_bind()
    listener = lambda conn, cursor, statement, *args: statements.append(statement)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        assert len(admin_client.get("/admin/api/merchants").json()["merchants"]) == 30
    finally:
        event.remove(engine, "before_cursor_execute", listener)

    assert len(statements) <= 4  # merchant, carte raggruppate, pool raggruppati


# --- pagina HTML ---

def test_dashboard_html_e_privo_di_innerhtml_e_non_rende_dati_lato_server(admin_client, session):
    """I nomi li scrivono i merchant: la pagina li inserisce solo con `textContent` e il server non li stampa nell'HTML."""
    new_merchant(session, "<img src=x onerror=alert(1)>", email="xss@test.it")

    page = admin_client.get("/admin")

    assert page.status_code == 200 and "text/html" in page.headers["Content-Type"]
    assert "alert(1)" not in page.text and "xss@test.it" not in page.text
    source = (Path("app/templates/admin/dashboard.html")).read_text(encoding="utf-8")
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "| safe", "|safe"):
        assert forbidden not in source, forbidden
    assert settings.ADMIN_SECRET_KEY not in page.text and settings.JWT_SECRET_KEY not in page.text


def test_dashboard_html_ha_filtri_ricerca_e_azioni(admin_client):
    text = admin_client.get("/admin").text

    assert 'id="search"' in text and 'id="state-filter"' in text
    for value in ('value="pending"', 'value="active"', 'value="paused"'):
        assert value in text
    for label in ("In attesa", "Attivo", "In pausa", "Avvia", "Metti in pausa", "Riattiva", "Reimposta password", "Copia"):
        assert label in text
    assert "Collegato con Zernio" in text                       # non «Attivo»: accanto allo stato del servizio confonderebbe
    assert "/admin/api/merchants" in text and "reset-password" in text
    assert 'id="reset-password"' in text and 'id="btn-copy-password"' in text


# --- azioni di stato ---

def test_approve_avvia_il_negozio_e_toglie_la_pausa(admin_client, session):
    pending = new_merchant(session, "Nuovo")
    paused = new_merchant(session, "Ferma", is_approved=True, is_paused=True)

    for merchant in (pending, paused):
        response = post_action(admin_client, merchant.id, "approve")
        assert response.status_code == 200
        assert response.json()["service_state"] == "active" and response.json()["id"] == merchant.id
        session.refresh(merchant)
        assert (merchant.is_approved, merchant.is_paused) == (True, False)


def test_pause_e_resume_cambiano_i_flag(admin_client, session):
    merchant = new_merchant(session, is_approved=True)

    paused = post_action(admin_client, merchant.id, "pause")
    assert paused.status_code == 200 and paused.json()["service_state"] == "paused"
    session.refresh(merchant)
    assert (merchant.is_approved, merchant.is_paused) == (True, True)

    resumed = post_action(admin_client, merchant.id, "resume")
    assert resumed.json()["service_state"] == "active"
    session.refresh(merchant)
    assert (merchant.is_approved, merchant.is_paused) == (True, False)
    assert get_row(admin_client, merchant.id)["service_state"] == "active"


def test_pausa_e_riattivazione_di_un_negozio_in_attesa_sono_409(admin_client, session):
    merchant = new_merchant(session)

    for action in ("pause", "resume"):
        response = post_action(admin_client, merchant.id, action)
        assert response.status_code == 409 and "in attesa" in response.json()["detail"]
    session.refresh(merchant)
    assert (merchant.is_approved, merchant.is_paused) == (False, False)


def test_azioni_ripetute_sono_idempotenti(admin_client, session):
    merchant = new_merchant(session, is_approved=True)

    for action, expected in (("approve", "active"), ("resume", "active"), ("pause", "paused"), ("pause", "paused"),
                             ("approve", "active"), ("approve", "active")):
        response = post_action(admin_client, merchant.id, action)
        assert response.status_code == 200 and response.json()["service_state"] == expected


def test_id_inesistente_e_404_per_ogni_azione(admin_client):
    for action in ACTIONS:
        response = post_action(admin_client, 99999, action)
        assert response.status_code == 404 and response.json() == {"detail": "Merchant non trovato"}


def test_le_azioni_non_toccano_altro(admin_client, session):
    merchant = new_merchant(session, "Bar Rosso", contact_phone="+393331234567", bronze_threshold=10, silver_threshold=20, gold_threshold=30)
    before = merchant.model_dump()

    post_action(admin_client, merchant.id, "approve")
    post_action(admin_client, merchant.id, "pause")
    post_action(admin_client, merchant.id, "resume")

    session.refresh(merchant)
    after = merchant.model_dump()
    changed = {k for k in before if before[k] != after[k]}
    assert changed <= {"is_approved", "is_paused"}


def test_la_dashboard_non_ha_azioni_di_creazione_o_eliminazione(admin_client, session):
    merchant = new_merchant(session)

    assert admin_client.post("/admin/api/merchants", headers=ORIGIN, json={}).status_code in (404, 405)
    assert admin_client.delete(f"/admin/api/merchants/{merchant.id}", headers=ORIGIN).status_code in (404, 405)
    assert admin_client.put(f"/admin/api/merchants/{merchant.id}", headers=ORIGIN, json={}).status_code in (404, 405)
    assert session.get(Merchant, merchant.id) is not None


def test_end_to_end_gli_stati_governano_lo_scanner(auth_client, session, merchant, card):
    """Approva / pausa / riattiva dalla dashboard cambiano ciò che lo scanner ammette (comportamento del ticket 12)."""
    merchant_crud.update_merchant(session, merchant, {"is_approved": False})
    scan = lambda points: auth_client.post(f"/api/merchant/add-tree-points/{card.id}", json={"tree_points": points})  # noqa: E731
    assert admin_login(auth_client).status_code == 303

    assert scan(5).status_code == 403                                    # in attesa: nessuna aggiunta
    assert post_action(auth_client, merchant.id, "approve").status_code == 200
    assert scan(5).status_code == 200                                    # attivo
    assert post_action(auth_client, merchant.id, "pause").status_code == 200
    assert scan(5).status_code == 403                                    # in pausa: nessuna aggiunta...
    assert scan(-2).status_code == 200                                   # ...ma si può togliere
    assert auth_client.get("/merchant/scanner").text.count("Servizio in pausa") >= 1
    assert post_action(auth_client, merchant.id, "resume").status_code == 200
    assert scan(5).status_code == 200
    assert post_action(auth_client, merchant.id, "pause").status_code == 200
    assert post_action(auth_client, merchant.id, "approve").status_code == 200   # approve toglie la pausa
    assert scan(5).status_code == 200
    assert session.get(Card, card.id).tree_points == 13                   # 5 - 2 + 5 + 5


def test_api_admin_approve_toglie_la_pausa_ed_espone_is_paused(client, session, admin_headers):
    merchant = new_merchant(session, is_approved=True, is_paused=True)

    read = client.get(f"/api/merchant/{merchant.id}", headers=admin_headers)
    assert read.json()["is_paused"] is True
    approved = client.post(f"/api/merchant/{merchant.id}/approve", headers=admin_headers)
    assert approved.status_code == 200 and approved.json()["is_approved"] is True and approved.json()["is_paused"] is False

    updated = client.put(f"/api/merchant/{merchant.id}", headers=admin_headers, json={"is_paused": True})
    assert updated.status_code == 200 and updated.json()["is_paused"] is True
    assert client.post("/api/merchant/99999/approve", headers=admin_headers).status_code == 404


# --- reset della password ---

@pytest.fixture()
def registered(session, local_auth):
    """Merchant registrato col provider `local` (come da `/merchant/register`), con il suo token di sessione."""
    data = merchant_service.validate_registration("Bar Sole", "bar@sole.it", PASSWORD)
    merchant, token = merchant_service.register_merchant(session, local_auth, data)
    return merchant, token


def merchant_login(client, password):
    return client.post("/merchant/login", data={"email": "bar@sole.it", "password": password}, follow_redirects=False)


def test_reset_password_la_temporanea_permette_il_login_la_vecchia_no(admin_client, registered):
    merchant, old_token = registered
    merchant_client = TestClient(app)
    merchant_client.cookies.set("access_token", old_token)
    assert merchant_client.get("/api/merchant/me").status_code == 200

    response = post_action(admin_client, merchant.id, "reset-password")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"merchant_id", "temporary_password"} and body["merchant_id"] == merchant.id
    temporary = body["temporary_password"]
    assert len(temporary) == 12 and temporary != PASSWORD
    assert merchant_login(TestClient(app), PASSWORD).status_code == 401   # la vecchia non vale più
    assert merchant_login(TestClient(app), temporary).status_code == 303  # la temporanea sì
    assert merchant_client.get("/api/merchant/me").status_code == 401     # la sessione aperta è decaduta


def test_reset_password_la_temporanea_compare_solo_nella_risposta(admin_client, registered, session, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    merchant, _ = registered

    response = post_action(admin_client, merchant.id, "reset-password")
    temporary = response.json()["temporary_password"]

    credential = session.exec(select(AuthCredential)).one()
    assert credential.password_hash.startswith("scrypt$") and temporary not in credential.password_hash
    rows = session.connection().exec_driver_sql("SELECT * FROM authcredential").fetchall()
    merchant_rows = session.connection().exec_driver_sql("SELECT * FROM merchant").fetchall()
    assert temporary not in repr(rows) and temporary not in repr(merchant_rows)
    assert temporary not in caplog.text
    captured = capsys.readouterr()
    assert temporary not in captured.out + captured.err
    # un secondo accesso alla lista non la riporta
    assert temporary not in admin_client.get("/admin/api/merchants").text
    assert response.headers["Cache-Control"] == "no-store"


def test_reset_password_ogni_reset_da_una_password_diversa_e_annulla_la_precedente(admin_client, registered):
    merchant, _ = registered
    first = post_action(admin_client, merchant.id, "reset-password").json()["temporary_password"]
    second = post_action(admin_client, merchant.id, "reset-password").json()["temporary_password"]

    assert first != second
    assert merchant_login(TestClient(app), first).status_code == 401
    assert merchant_login(TestClient(app), second).status_code == 303


def test_reset_password_sblocca_il_merchant_fermato_dal_freno(admin_client, registered):
    """Il 429 del merchant dice «chiedi al founder il reset»: dopo il reset la password temporanea deve funzionare subito."""
    merchant, _ = registered
    other = TestClient(app)
    for _ in range(LOGIN_MAX_FAILURES):
        assert merchant_login(other, "sbagliata").status_code == 401
    assert merchant_login(other, PASSWORD).status_code == 429

    temporary = post_action(admin_client, merchant.id, "reset-password").json()["temporary_password"]

    assert merchant_login(other, temporary).status_code == 303


def test_reset_password_senza_credenziale_e_409(admin_client, session, local_auth):
    no_auth = new_merchant(session, "Creato da admin")                               # nessun auth_user_id
    orphan = new_merchant(session, "Orfano", auth_user_id="uid-senza-credenziale")   # id senza riga AuthCredential

    for merchant in (no_auth, orphan):
        response = post_action(admin_client, merchant.id, "reset-password")
        assert response.status_code == 409 and "credenziale" in response.json()["detail"]
    assert not session.exec(select(AuthCredential)).all()


def test_reset_password_con_provider_senza_password_e_400(admin_client, session, monkeypatch, auth_provider):
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "dev")
    merchant = new_merchant(session, auth_user_id="uid-dev")

    response = post_action(admin_client, merchant.id, "reset-password")

    assert response.status_code == 400 and "provider" in response.json()["detail"]


def test_reset_password_di_un_id_inesistente_e_404(admin_client, local_auth):
    assert post_action(admin_client, 99999, "reset-password").status_code == 404


def test_reset_password_richiede_origin_e_sessione(client, registered):
    merchant, _ = registered

    assert post_action(client, merchant.id, "reset-password").status_code == 401
    assert admin_login(client).status_code == 303
    assert post_action(client, merchant.id, "reset-password", headers={}).status_code == 403
    assert post_action(client, merchant.id, "reset-password", headers={"Origin": "https://evil.example"}).status_code == 403
    assert merchant_login(TestClient(app), PASSWORD).status_code == 303  # la password non è cambiata


def test_il_repr_della_risposta_di_reset_non_mostra_la_password():
    from app.schemas.merchant import AdminResetPasswordResponse
    response = AdminResetPasswordResponse(merchant_id=1, temporary_password="Segreta12345")
    assert "Segreta12345" not in repr(response) and "Segreta12345" not in str(response)
