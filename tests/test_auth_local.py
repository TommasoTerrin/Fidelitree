"""
Test del provider di autenticazione `local` (password nel nostro DB), del freno ai tentativi di login e del
cambio password. SQLite in-memory: il provider usa la `session` di test (fixture `local_auth`), mai l'engine
dell'app, che punta al DATABASE_URL del .env.
"""

import logging
from datetime import timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jose import jwt
from sqlmodel import select

from app.core import auth, security
from app.core.auth import (
    AuthError, LocalAuthProvider, LoginThrottle, PasswordAdminProvider, get_auth_provider,
)
from app.core.clock import utc_now
from app.core.config import settings
from app.core.errors import ForbiddenError, InvalidInputError, NotFoundError, TooManyAttemptsError
from app.main import app
from app.models.models import AuthCredential, Merchant
from app.services import merchant_service

PASSWORD = "password-segreta-1"
NEW_PASSWORD = "nuova-password-2"
REGISTER = {"business_name": "Bar Sole", "email": "Bar@Sole.it", "password": PASSWORD}


# --- Provider -------------------------------------------------------------------------------------------------

def test_sign_up_e_login(local_auth):
    identity = local_auth.sign_up(" Bar@Sole.it ", PASSWORD)
    assert identity.email == "bar@sole.it"
    token = local_auth.sign_in_password("BAR@sole.it", PASSWORD)
    assert local_auth.verify_token(token) == identity


def test_il_provider_local_gestisce_le_password(local_auth):
    assert isinstance(local_auth, PasswordAdminProvider)
    assert not isinstance(auth.DevAuthProvider(), PasswordAdminProvider)


def test_nel_db_non_c_e_nessuna_password_in_chiaro(local_auth, session):
    local_auth.sign_up("a@b.it", PASSWORD)
    credential = session.exec(select(AuthCredential)).one()
    assert credential.password_hash.startswith("scrypt$") and credential.token_version == 1
    assert "password" not in Merchant.model_fields
    rows = session.connection().exec_driver_sql("SELECT * FROM authcredential").fetchall()
    assert PASSWORD not in repr(rows)


def test_l_hash_non_compare_nel_repr(local_auth, session):
    local_auth.sign_up("a@b.it", PASSWORD)
    credential = session.exec(select(AuthCredential)).one()
    assert credential.password_hash not in repr(credential)
    assert credential.password_hash not in str(credential)


def test_email_duplicata(local_auth, session):
    local_auth.sign_up("a@b.it", PASSWORD)
    with pytest.raises(AuthError):
        local_auth.sign_up(" A@B.it", "altra-password-1")
    assert len(session.exec(select(AuthCredential)).all()) == 1


def test_password_di_lunghezza_non_valida_alla_registrazione(local_auth, session):
    for bad in ("corta", "x" * 129, None):
        with pytest.raises(InvalidInputError):
            local_auth.sign_up("a@b.it", bad)
    assert session.exec(select(AuthCredential)).all() == []


def test_corsa_tra_due_registrazioni_non_perde_l_hash(session, caplog):
    """Se il DB rifiuta l'INSERT (email unica) l'errore SQLAlchemy contiene l'hash: non deve uscire né essere loggato."""

    class _Blind:
        """Sessione che finge di non vedere la riga già presente: il controllo preventivo non scatta e arriva l'IntegrityError."""

        def __init__(self, real):
            self._real = real

        def exec(self, *args, **kwargs):
            class _Empty:
                @staticmethod
                def first():
                    return None
            return _Empty()

        def __getattr__(self, name):
            return getattr(self._real, name)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    existing = LocalAuthProvider(session_factory=lambda: _NullSession(session))
    existing.sign_up("a@b.it", PASSWORD)
    racing = LocalAuthProvider(session_factory=lambda: _Blind(session))
    caplog.set_level(logging.DEBUG)
    with pytest.raises(AuthError) as exc:
        racing.sign_up("a@b.it", "altra-password-1")
    assert exc.value.__cause__ is None and exc.value.__suppress_context__
    assert "altra-password-1" not in caplog.text and "scrypt$" not in caplog.text
    assert len(session.exec(select(AuthCredential)).all()) == 1  # la sessione resta utilizzabile


class _NullSession:
    """Context manager che ritorna la sessione di test senza chiuderla."""

    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *exc):
        return False


def test_stesso_messaggio_per_email_sconosciuta_e_password_errata(local_auth):
    local_auth.sign_up("a@b.it", PASSWORD)
    with pytest.raises(AuthError) as wrong:
        local_auth.sign_in_password("a@b.it", "sbagliata-1234")
    with pytest.raises(AuthError) as unknown:
        local_auth.sign_in_password("nessuno@b.it", PASSWORD)
    assert str(wrong.value) == str(unknown.value) == "Credenziali non valide"


def test_con_email_sconosciuta_si_verifica_comunque_un_hash(local_auth, monkeypatch):
    local_auth.sign_up("a@b.it", PASSWORD)
    calls = []
    real = auth.verify_password
    monkeypatch.setattr(auth, "verify_password", lambda p, h: calls.append(h) or real(p, h))
    with pytest.raises(AuthError):
        local_auth.sign_in_password("nessuno@b.it", PASSWORD)
    assert len(calls) == 1 and calls[0].startswith("scrypt$16384$8$1$")  # stessi parametri degli hash veri


def test_password_troppo_lunga_nel_login_e_credenziali_non_valide(local_auth):
    local_auth.sign_up("a@b.it", PASSWORD)
    with pytest.raises(AuthError, match="Credenziali non valide"):
        local_auth.sign_in_password("a@b.it", "x" * 5000)


def test_verify_token_rifiuta_firma_errata(local_auth):
    local_auth.sign_up("a@b.it", PASSWORD)
    token = local_auth.sign_in_password("a@b.it", PASSWORD)
    payload = jwt.get_unverified_claims(token)
    forged = jwt.encode(payload, "un-altro-segreto", algorithm=security.ALGORITHM)
    assert local_auth.verify_token(forged) is None
    assert local_auth.verify_token("spazzatura") is None


def test_verify_token_rifiuta_scaduto(local_auth):
    identity = local_auth.sign_up("a@b.it", PASSWORD)
    scaduto = jwt.encode(
        {"sub": identity.user_id, "email": "a@b.it", "ver": 1, "exp": utc_now() - timedelta(minutes=1)},
        settings.JWT_SECRET_KEY, algorithm=security.ALGORITHM,
    )
    assert local_auth.verify_token(scaduto) is None


@pytest.mark.parametrize("claims", [
    {"email": "a@b.it", "ver": 1},                              # senza sub
    {"sub": "{uid}", "ver": 1},                                 # senza email
    {"sub": "{uid}", "email": "a@b.it"},                        # senza ver (es. token del provider dev)
    {"sub": "{uid}", "email": "a@b.it", "ver": "1"},            # ver non intero
    {"sub": "{uid}", "email": "a@b.it", "ver": True},           # bool non vale come intero
    {"sub": "{uid}", "email": "a@b.it", "ver": 2},              # ver non attuale
])
def test_verify_token_rifiuta_claim_incompleti_o_non_attuali(local_auth, claims):
    identity = local_auth.sign_up("a@b.it", PASSWORD)
    claims = {k: (identity.user_id if v == "{uid}" else v) for k, v in claims.items()}
    assert local_auth.verify_token(security.create_jwt_token(claims)) is None


def test_verify_token_rifiuta_utente_cancellato(local_auth):
    identity = local_auth.sign_up("a@b.it", PASSWORD)
    token = local_auth.sign_in_password("a@b.it", PASSWORD)
    local_auth.delete_user(identity.user_id)
    assert local_auth.verify_token(token) is None
    local_auth.delete_user(identity.user_id)  # idempotente


def test_set_password_invalida_le_sessioni_e_vale_la_nuova(local_auth, session):
    identity = local_auth.sign_up("a@b.it", PASSWORD)
    old_token = local_auth.sign_in_password("a@b.it", PASSWORD)
    old_hash = session.get(AuthCredential, identity.user_id).password_hash

    local_auth.set_password(identity.user_id, NEW_PASSWORD)

    assert local_auth.verify_token(old_token) is None
    with pytest.raises(AuthError):
        local_auth.sign_in_password("a@b.it", PASSWORD)
    new_token = local_auth.sign_in_password("a@b.it", NEW_PASSWORD)
    assert local_auth.verify_token(new_token).user_id == identity.user_id
    credential = session.get(AuthCredential, identity.user_id)
    assert credential.token_version == 2 and credential.password_hash != old_hash


def test_set_password_errori(local_auth):
    identity = local_auth.sign_up("a@b.it", PASSWORD)
    with pytest.raises(InvalidInputError):
        local_auth.set_password(identity.user_id, "corta")
    with pytest.raises(NotFoundError):
        local_auth.set_password("non-esiste", NEW_PASSWORD)
    assert local_auth.sign_in_password("a@b.it", PASSWORD)  # la password non è cambiata


def test_change_password_con_password_attuale_errata_rifiutata(local_auth, session):
    identity = local_auth.sign_up("a@b.it", PASSWORD)
    with pytest.raises(AuthError):
        local_auth.change_password(identity.user_id, "sbagliata-1234", NEW_PASSWORD)
    with pytest.raises(AuthError):
        local_auth.change_password(identity.user_id, None, NEW_PASSWORD)
    assert session.get(AuthCredential, identity.user_id).token_version == 1
    assert local_auth.sign_in_password("a@b.it", PASSWORD)


def test_change_password_riemette_il_token_e_chiude_le_altre_sessioni(local_auth):
    identity = local_auth.sign_up("a@b.it", PASSWORD)
    other_session = local_auth.sign_in_password("a@b.it", PASSWORD)
    new_token = local_auth.change_password(identity.user_id, PASSWORD, NEW_PASSWORD)
    assert local_auth.verify_token(new_token).user_id == identity.user_id
    assert local_auth.verify_token(other_session) is None
    with pytest.raises(AuthError):
        local_auth.sign_in_password("a@b.it", PASSWORD)
    assert local_auth.sign_in_password("a@b.it", NEW_PASSWORD)


def test_change_password_nuova_non_valida_non_tocca_nulla(local_auth, session):
    identity = local_auth.sign_up("a@b.it", PASSWORD)
    with pytest.raises(InvalidInputError):
        local_auth.change_password(identity.user_id, PASSWORD, "corta")
    assert session.get(AuthCredential, identity.user_id).token_version == 1


# --- Scelta del provider e avvio ------------------------------------------------------------------------------

def _fresh_local_instance(monkeypatch):
    """Toglie (e a fine test ripristina) l'istanza `local` in cache: `get_auth_provider` ne crea una col factory di default, senza aprire il DB."""
    monkeypatch.setitem(auth._instances, "local", None)
    monkeypatch.delitem(auth._instances, "local")


def test_local_in_produzione_e_ammesso_e_dev_no(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    _fresh_local_instance(monkeypatch)
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "local")
    assert isinstance(get_auth_provider(), LocalAuthProvider)
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "dev")
    with pytest.raises(RuntimeError):
        get_auth_provider()


def _memory_engine():
    from sqlalchemy.pool import StaticPool
    from sqlmodel import create_engine
    return create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


def test_l_app_parte_con_local_in_produzione(monkeypatch):
    """Lifespan vero, ma su un engine SQLite in-memory messo al posto di quello dell'app (mai il DB del .env)."""
    import app.main as main
    monkeypatch.setattr(main, "engine", _memory_engine())
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "local")
    _fresh_local_instance(monkeypatch)
    with TestClient(app) as started:
        assert started.get("/health").status_code == 200


def test_l_app_non_parte_con_dev_in_produzione(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "engine", _memory_engine())
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "dev")
    with pytest.raises(RuntimeError, match="AUTH_PROVIDER=dev"):
        with TestClient(app):
            pass


# --- Freno ai tentativi (stato in memoria) ---------------------------------------------------------------------

def test_throttle_blocca_alla_soglia_e_si_scioglie_con_la_finestra():
    throttle, now = LoginThrottle(), utc_now()
    keys = ("email:a@b.it", "ip:1.1.1.1")
    for i in range(4):
        throttle.record_failure(keys, now + timedelta(seconds=i))
    throttle.check(keys, now + timedelta(seconds=4))  # 4 errori: ancora ammesso
    throttle.record_failure(keys, now + timedelta(seconds=4))
    with pytest.raises(TooManyAttemptsError) as exc:
        throttle.check(keys, now + timedelta(seconds=10))
    assert 14 * 60 < exc.value.retry_after <= 15 * 60
    throttle.check(keys, now + timedelta(minutes=15, seconds=5))  # scaduta la finestra


def test_throttle_una_chiave_a_soglia_basta_a_bloccare():
    throttle, now = LoginThrottle(), utc_now()
    for _ in range(5):
        throttle.record_failure(("email:a@b.it", "ip:1.1.1.1"), now)
    with pytest.raises(TooManyAttemptsError):
        throttle.check(("email:a@b.it", "ip:2.2.2.2"), now)  # stessa email, IP nuovo
    with pytest.raises(TooManyAttemptsError):
        throttle.check(("email:altra@b.it", "ip:1.1.1.1"), now)  # stesso IP, email nuova
    throttle.check(("email:altra@b.it", "ip:2.2.2.2"), now)


def test_throttle_clear_azzera_solo_la_chiave_indicata():
    throttle, now = LoginThrottle(), utc_now()
    for _ in range(5):
        throttle.record_failure(("email:a@b.it", "ip:1.1.1.1"), now)
    throttle.clear("email:a@b.it")
    with pytest.raises(TooManyAttemptsError):
        throttle.check(("email:a@b.it", "ip:1.1.1.1"), now)  # l'IP resta a soglia
    throttle.check(("email:a@b.it", "ip:9.9.9.9"), now)


def test_throttle_butta_le_chiavi_scadute_quando_sono_troppe(monkeypatch):
    throttle, now = LoginThrottle(), utc_now()
    monkeypatch.setattr(LoginThrottle, "_PURGE_ABOVE", 3)
    for i in range(3):
        throttle.record_failure((f"email:{i}@b.it",), now - timedelta(hours=1))
    throttle.record_failure(("email:nuovo@b.it",), now)
    assert set(throttle._failures) == {"email:nuovo@b.it"}


# --- Login con il freno (service) ------------------------------------------------------------------------------

@pytest.fixture()
def registered(local_auth, session):
    """Merchant registrato col provider local: ritorna la sua email."""
    data = merchant_service.validate_registration("Bar Sole", "bar@sole.it", PASSWORD)
    merchant_service.register_merchant(session, local_auth, data)
    return "bar@sole.it"


def _login(session, provider, email, password, ip="1.1.1.1", now=None):
    return merchant_service.login_merchant(session, provider, email, password, client_ip=ip, now=now or utc_now())


def test_sesto_tentativo_bloccato_anche_con_la_password_giusta(session, local_auth, registered):
    now = utc_now()
    for i in range(5):
        with pytest.raises(AuthError):
            _login(session, local_auth, registered, "sbagliata-1234", ip=f"10.0.0.{i}", now=now)  # IP sempre diversi
    with pytest.raises(TooManyAttemptsError):
        _login(session, local_auth, registered, PASSWORD, ip="10.0.0.99", now=now)
    # passata la finestra si rientra
    assert _login(session, local_auth, registered, PASSWORD, ip="10.0.0.99", now=now + timedelta(minutes=16))


def test_il_freno_normalizza_l_email(session, local_auth, registered):
    now = utc_now()
    variants = ["BAR@sole.it", " bar@sole.it", "Bar@Sole.it", "bar@SOLE.it", "bar@sole.it "]
    for i, email in enumerate(variants):
        with pytest.raises(AuthError):
            _login(session, local_auth, email, "sbagliata-1234", ip=f"10.0.0.{i}", now=now)
    with pytest.raises(TooManyAttemptsError):
        _login(session, local_auth, "bar@sole.it", PASSWORD, ip="10.0.0.99", now=now)


def test_email_sconosciuta_conta_come_errore(session, local_auth):
    now = utc_now()
    for i in range(5):
        with pytest.raises(AuthError):
            _login(session, local_auth, "nessuno@sole.it", PASSWORD, ip=f"10.0.0.{i}", now=now)
    with pytest.raises(TooManyAttemptsError):
        _login(session, local_auth, "nessuno@sole.it", PASSWORD, ip="10.0.0.99", now=now)


def test_il_successo_azzera_il_contatore_dell_email(session, local_auth, registered):
    now = utc_now()
    for i in range(4):
        with pytest.raises(AuthError):
            _login(session, local_auth, registered, "sbagliata-1234", ip=f"10.0.0.{i}", now=now)
    assert _login(session, local_auth, registered, PASSWORD, ip="10.0.1.1", now=now)
    for i in range(4):  # altri 4 errori: senza l'azzeramento sarebbero 8
        with pytest.raises(AuthError):
            _login(session, local_auth, registered, "sbagliata-1234", ip=f"10.0.2.{i}", now=now)
    assert _login(session, local_auth, registered, PASSWORD, ip="10.0.3.1", now=now)


def test_il_successo_non_azzera_l_ip(session, local_auth, registered):
    """Chi ha un account suo non può svuotare il contatore dell'IP con un accesso riuscito tra un tentativo e l'altro."""
    now = utc_now()
    for i in range(5):
        with pytest.raises(AuthError):
            _login(session, local_auth, f"altro{i}@sole.it", "sbagliata-1234", ip="7.7.7.7", now=now)
    with pytest.raises(TooManyAttemptsError):
        _login(session, local_auth, registered, PASSWORD, ip="7.7.7.7", now=now)


def test_ip_sconosciuto_non_rompe_il_login(session, local_auth, registered):
    assert _login(session, local_auth, registered, PASSWORD, ip=None)


def test_identita_senza_merchant_resta_403_e_non_conta_come_errore(session, local_auth):
    local_auth.sign_up("orfano@sole.it", PASSWORD)
    for _ in range(7):
        with pytest.raises(ForbiddenError):
            _login(session, local_auth, "orfano@sole.it", PASSWORD)


# --- Route end-to-end: ENVIRONMENT=production + AUTH_PROVIDER=local --------------------------------------------

@pytest.fixture()
def prod_client(client, local_auth, monkeypatch):
    """Client https (il cookie è `Secure` in produzione) con provider local e ENVIRONMENT=production."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    return TestClient(app, base_url="https://testserver")


def _register(client, **overrides):
    return client.post("/merchant/register", json={**REGISTER, **overrides})


def _login_form(client, email="bar@sole.it", password=PASSWORD):
    return client.post("/merchant/login", data={"email": email, "password": password}, follow_redirects=False)


def test_registrazione_e_login_end_to_end(prod_client, session):
    resp = _register(prod_client)
    assert resp.status_code == 200 and resp.json()["is_approved"] is False
    set_cookie = resp.headers["set-cookie"].lower()
    assert "access_token=" in set_cookie and "httponly" in set_cookie and "secure" in set_cookie and "samesite=lax" in set_cookie

    merchant = session.get(Merchant, resp.json()["merchant_id"])
    credential = session.exec(select(AuthCredential)).one()
    assert merchant.auth_user_id == credential.user_id and merchant.email == credential.email == "bar@sole.it"

    assert prod_client.get("/api/merchant/me").json()["email"] == "bar@sole.it"
    assert prod_client.get("/merchant/scanner").status_code == 200

    prod_client.cookies.clear()
    assert prod_client.get("/merchant/scanner", follow_redirects=False).status_code == 303
    login = _login_form(prod_client, email=" BAR@sole.it")
    assert login.status_code == 303 and login.headers["location"] == "/merchant/scanner"
    assert prod_client.get("/api/merchant/me").status_code == 200


def test_login_credenziali_errate_stesso_messaggio(prod_client):
    _register(prod_client)
    wrong = _login_form(prod_client, password="sbagliata-1234")
    unknown = _login_form(prod_client, email="nessuno@sole.it")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Credenziali non valide"}


def test_registrazione_email_gia_usata_e_dati_non_validi(prod_client, session, merchant):
    assert _register(prod_client).status_code == 200
    assert _register(prod_client, business_name="Altro").status_code == 409
    assert _register(prod_client, email=merchant.email).status_code == 409  # merchant creato dall'admin: invariato
    assert _register(prod_client, email="nuovo@sole.it", password="corta").status_code == 400
    assert _register(prod_client, email="nuovo@sole.it", password="x" * 129).status_code == 400
    assert len(session.exec(select(AuthCredential)).all()) == 1


def test_sesto_login_sbagliato_da_429_con_attesa(prod_client):
    _register(prod_client)
    prod_client.cookies.clear()
    for _ in range(5):
        assert _login_form(prod_client, password="sbagliata-1234").status_code == 401
    blocked = _login_form(prod_client, password=PASSWORD)  # anche la password giusta
    assert blocked.status_code == 429
    assert "Troppi tentativi" in blocked.json()["detail"]
    assert 1 <= int(blocked.headers["retry-after"]) <= 15 * 60
    assert PASSWORD not in blocked.text


def test_429_per_ip_con_email_sempre_diverse(prod_client):
    for i in range(5):
        assert _login_form(prod_client, email=f"nessuno{i}@sole.it").status_code == 401
    assert _login_form(prod_client, email="ancora-un-altro@sole.it").status_code == 429


def test_il_freno_vale_anche_con_il_provider_dev(client, auth_provider):
    for _ in range(5):
        assert client.post("/merchant/login", data={"email": "x@y.it", "password": "p"}).status_code == 401
    assert client.post("/merchant/login", data={"email": "x@y.it", "password": "p"}).status_code == 429


def _cookie(client) -> str:
    return client.cookies.get("access_token")


def test_cambio_password_end_to_end(prod_client):
    _register(prod_client)
    old_cookie = _cookie(prod_client)

    resp = prod_client.post("/api/merchant/me/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert resp.status_code == 200 and resp.json() == {"status": "success"}
    assert PASSWORD not in resp.text and NEW_PASSWORD not in resp.text
    assert "access_token=" in resp.headers["set-cookie"]

    # il cookie riemesso funziona, quello vecchio no
    assert prod_client.get("/api/merchant/me").status_code == 200
    stale = TestClient(app, base_url="https://testserver", cookies={"access_token": old_cookie})
    assert stale.get("/api/merchant/me").status_code == 401
    assert stale.get("/merchant/scanner", follow_redirects=False).status_code == 303

    # e vale la nuova password
    prod_client.cookies.clear()
    assert _login_form(prod_client, password=PASSWORD).status_code == 401
    assert _login_form(prod_client, password=NEW_PASSWORD).status_code == 303


def test_cambio_password_errori(prod_client, session):
    _register(prod_client)
    version = session.exec(select(AuthCredential)).one().token_version
    url = "/api/merchant/me/password"

    short = prod_client.post(url, json={"current_password": PASSWORD, "new_password": "corta"})
    long = prod_client.post(url, json={"current_password": PASSWORD, "new_password": "x" * 129})
    missing = prod_client.post(url, json={"current_password": PASSWORD})
    assert short.status_code == long.status_code == missing.status_code == 400

    wrong = prod_client.post(url, json={"current_password": "sbagliata-1234", "new_password": NEW_PASSWORD})
    assert wrong.status_code == 401
    assert "set-cookie" not in wrong.headers

    for resp in (short, long, missing, wrong):
        assert PASSWORD not in resp.text and NEW_PASSWORD not in resp.text and "sbagliata-1234" not in resp.text
        assert "scrypt$" not in resp.text

    session.expire_all()
    assert session.exec(select(AuthCredential)).one().token_version == version
    assert prod_client.get("/api/merchant/me").status_code == 200  # la sessione è ancora valida


def test_cambio_password_richiede_la_sessione(prod_client):
    resp = prod_client.post("/api/merchant/me/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert resp.status_code == 401


def test_cambio_password_non_disponibile_col_provider_dev(auth_client):
    resp = auth_client.post("/api/merchant/me/password", json={"current_password": "x", "new_password": NEW_PASSWORD})
    assert resp.status_code == 400
    assert NEW_PASSWORD not in resp.text


def test_nessun_422_rimanda_indietro_la_password(prod_client):
    """Un campo mancante o del tipo sbagliato è un 400 del service: il 422 di FastAPI includerebbe il corpo."""
    for body in ({"password": PASSWORD}, {"password": PASSWORD, "email": 5, "business_name": ["x"]}):
        resp = prod_client.post("/merchant/register", json=body)
        assert resp.status_code == 400
        assert PASSWORD not in resp.text


def test_la_pagina_impostazioni_mostra_il_cambio_password_con_local(prod_client):
    _register(prod_client)
    assert 'id="password-form"' in prod_client.get("/merchant/settings").text


def test_la_pagina_impostazioni_non_lo_mostra_col_provider_dev(auth_client):
    assert 'id="password-form"' not in auth_client.get("/merchant/settings").text


def test_nessun_segreto_nei_log(prod_client, caplog):
    caplog.set_level(logging.DEBUG)
    _register(prod_client)
    old_cookie = _cookie(prod_client)
    prod_client.cookies.clear()
    _login_form(prod_client, password="sbagliata-1234")
    _login_form(prod_client)
    prod_client.post("/api/merchant/me/password", json={"current_password": "sbagliata-1234", "new_password": NEW_PASSWORD})
    prod_client.post("/api/merchant/me/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    for _ in range(6):
        _login_form(prod_client, password="sbagliata-1234")  # fino al 429
    for secret in (PASSWORD, NEW_PASSWORD, "sbagliata-1234", "scrypt$", old_cookie, _cookie(prod_client) or "token-assente"):
        assert secret not in caplog.text


def test_registrazione_fallita_a_meta_non_lascia_credenziali_orfane(prod_client, session, monkeypatch):
    def boom(*args, **kwargs):
        raise HTTPException(status_code=500, detail="Errore interno")

    with monkeypatch.context() as patched:
        patched.setattr(merchant_service.merchant_crud, "create_merchant", boom)
        assert _register(prod_client).status_code == 500
    assert session.exec(select(AuthCredential)).all() == []
    assert _register(prod_client).status_code == 200  # l'email non è rimasta bloccata


def test_cancellando_il_merchant_si_libera_l_email(prod_client, session, admin_headers):
    merchant_id = _register(prod_client).json()["merchant_id"]
    assert len(session.exec(select(AuthCredential)).all()) == 1

    assert prod_client.delete(f"/api/merchant/{merchant_id}", headers=admin_headers).status_code == 200
    assert session.exec(select(AuthCredential)).all() == []
    assert prod_client.delete(f"/api/merchant/{merchant_id}", headers=admin_headers).status_code == 404

    prod_client.cookies.clear()
    assert _register(prod_client).status_code == 200  # la stessa email si registra di nuovo
