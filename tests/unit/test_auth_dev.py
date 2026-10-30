"""Test del provider di autenticazione `dev` e della scelta del provider (niente DB, niente rete)."""

from datetime import timedelta

import pytest
from jose import jwt

from app.core import auth, security
from app.core.auth import AuthError, DevAuthProvider, SupabaseAuthProvider, get_auth_provider
from app.core.clock import utc_now
from app.core.config import settings


@pytest.fixture()
def provider():
    return DevAuthProvider()


def test_sign_up_e_sign_in_con_password_giusta(provider):
    identity = provider.sign_up("a@b.it", "password1")
    token = provider.sign_in_password("a@b.it", "password1")
    verified = provider.verify_token(token)
    assert verified.email == "a@b.it"
    assert verified.user_id == identity.user_id


def test_password_sbagliata_e_utente_inesistente(provider):
    provider.sign_up("a@b.it", "password1")
    with pytest.raises(AuthError):
        provider.sign_in_password("a@b.it", "sbagliata")
    with pytest.raises(AuthError):
        provider.sign_in_password("nessuno@b.it", "password1")


def test_password_dev_vale_per_utenti_non_registrati_in_memoria(provider, monkeypatch):
    monkeypatch.setattr(settings, "DEV_AUTH_PASSWORD", "password-dev")
    token = provider.sign_in_password("Seed@B.it", "password-dev")
    assert provider.verify_token(token).email == "seed@b.it"
    with pytest.raises(AuthError):
        provider.sign_in_password("seed@b.it", "altra-password")


def test_utente_registrato_non_accetta_la_password_dev(provider, monkeypatch):
    monkeypatch.setattr(settings, "DEV_AUTH_PASSWORD", "password-dev")
    provider.sign_up("a@b.it", "password1")
    with pytest.raises(AuthError):
        provider.sign_in_password("a@b.it", "password-dev")


def test_password_dev_vuota_disattiva_il_fallback(provider, monkeypatch):
    monkeypatch.setattr(settings, "DEV_AUTH_PASSWORD", "")
    with pytest.raises(AuthError):
        provider.sign_in_password("seed@b.it", "")


def test_sign_up_email_duplicata(provider):
    provider.sign_up("a@b.it", "password1")
    with pytest.raises(AuthError):
        provider.sign_up("A@B.it ", "altra")


def test_il_provider_non_ha_piu_l_accesso_con_otp(provider):
    assert not hasattr(provider, "request_otp") and not hasattr(provider, "verify_otp")
    assert not hasattr(auth, "DEV_OTP_CODE")


def test_verify_token_spazzatura_e_scaduto(provider):
    assert provider.verify_token("spazzatura") is None
    scaduto = jwt.encode(
        {"sub": "u", "email": "a@b.it", "exp": utc_now() - timedelta(minutes=1)},
        settings.JWT_SECRET_KEY, algorithm=security.ALGORITHM,
    )
    assert provider.verify_token(scaduto) is None


def test_verify_token_senza_sub_o_email(provider):
    incompleto = security.create_jwt_token({"sub": "u"})
    assert provider.verify_token(incompleto) is None


def test_user_id_deterministico_per_email(provider):
    a1 = provider.sign_up("a@b.it", "p1").user_id
    other = DevAuthProvider()
    a2 = other.sign_up("A@b.it", "p2").user_id
    b = other.sign_up("b@b.it", "p2").user_id
    assert a1 == a2
    assert a1 != b


def test_reset_dimentica_gli_utenti(provider):
    provider.sign_up("a@b.it", "password1")
    provider.reset()
    with pytest.raises(AuthError):
        provider.sign_in_password("a@b.it", "password1")


def test_dev_in_produzione_solleva(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "dev")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with pytest.raises(RuntimeError):
        get_auth_provider()


def test_supabase_e_uno_stub(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "supabase")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    p = get_auth_provider()
    assert isinstance(p, SupabaseAuthProvider)
    for call in (
        lambda: p.sign_up("a@b.it", "x"),
        lambda: p.sign_in_password("a@b.it", "x"),
        lambda: p.verify_token("t"),
    ):
        with pytest.raises(NotImplementedError):
            call()


def test_il_provider_e_un_singleton_per_processo(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PROVIDER", "dev")
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    assert get_auth_provider() is get_auth_provider()


def test_security_non_espone_piu_fernet():
    assert not hasattr(security, "encrypt_key")
    assert not hasattr(security, "decrypt_key")
    assert not hasattr(auth, "Fernet")
