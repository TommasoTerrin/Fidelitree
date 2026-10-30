"""Test del core puro dell'autenticazione: hash scrypt, regole sulla password, freno ai tentativi (niente DB, niente mock)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core import auth
from app.core.auth import (
    LOGIN_FAILURE_WINDOW, LOGIN_MAX_FAILURES, MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, hash_password,
    login_failure_message, login_retry_after, login_throttle_key, recent_failures, validate_password, verify_password,
)
from app.core.errors import InvalidInputError, TooManyAttemptsError

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


# --- Hash e verifica ---

def test_hash_ha_formato_autodescrittivo():
    parts = hash_password("password123").split("$")
    assert parts[0] == "scrypt"
    assert [int(x) for x in parts[1:4]] == [auth.SCRYPT_N, auth.SCRYPT_R, auth.SCRYPT_P]
    assert len(parts) == 6


def test_password_giusta_e_sbagliata():
    stored = hash_password("password123")
    assert verify_password("password123", stored) is True
    assert verify_password("password124", stored) is False
    assert verify_password("", stored) is False


def test_salt_diverso_a_ogni_hash():
    assert hash_password("password123") != hash_password("password123")


def test_salt_esplicito_rende_l_hash_deterministico():
    salt = b"0123456789abcdef"
    assert hash_password("password123", salt) == hash_password("password123", salt)


def test_la_password_in_chiaro_non_e_nell_hash():
    assert "password123" not in hash_password("password123")


@pytest.mark.parametrize("malformed", [
    "", "boh", "scrypt$16384$8$1$solo-cinque-parti", "bcrypt$16384$8$1$AAAA$AAAA",
    "scrypt$x$8$1$AAAA$AAAA", "scrypt$16384$8$1$!!!$AAAA", "scrypt$16384$8$1$AAAA$",
    "scrypt$3$8$1$AAAA$AAAA",            # n non potenza di due
    "scrypt$1099511627776$8$1$AAAA$AAAA",  # n assurdo: oltre il tetto, nessuna allocazione
    "scrypt$16384$8$99999$AAAA$AAAA",
])
def test_formato_malformato_vale_false_senza_eccezioni(malformed):
    assert verify_password("password123", malformed) is False


def test_la_verifica_usa_i_parametri_salvati():
    """Un hash con parametri diversi da quelli correnti si verifica lo stesso (cambiare le costanti non rompe i vecchi hash)."""
    import base64
    salt = b"0123456789abcdef"
    derived = auth._scrypt("password123", salt, 2 ** 10, 8, 1, 32)
    stored = "$".join(("scrypt", "1024", "8", "1", base64.b64encode(salt).decode(), base64.b64encode(derived).decode()))
    assert verify_password("password123", stored) is True
    assert verify_password("altra-password", stored) is False


def test_verifica_in_tempo_costante():
    import inspect
    assert "compare_digest" in inspect.getsource(verify_password)


def test_password_con_surrogato_isolato_non_solleva_nella_verifica():
    assert verify_password("\ud800" * 8, hash_password("password123")) is False


# --- Lunghezza della password ---

def test_lunghezza_valida_ai_bordi():
    assert validate_password("a" * MIN_PASSWORD_LENGTH) == "a" * MIN_PASSWORD_LENGTH
    assert validate_password("a" * MAX_PASSWORD_LENGTH) == "a" * MAX_PASSWORD_LENGTH
    assert validate_password("  spazi  ") == "  spazi  "  # gli spazi contano, nessun strip


@pytest.mark.parametrize("bad", ["", "corta", "a" * (MIN_PASSWORD_LENGTH - 1), "a" * (MAX_PASSWORD_LENGTH + 1), None, 12345678, ["x"] * 9])
def test_lunghezza_non_valida(bad):
    with pytest.raises(InvalidInputError):
        validate_password(bad)


def test_il_messaggio_non_riporta_la_password():
    secret = "x" * (MAX_PASSWORD_LENGTH + 1)
    with pytest.raises(InvalidInputError) as exc:
        validate_password(secret)
    assert secret not in str(exc.value)


def test_surrogato_isolato_rifiutato_con_errore_di_dominio():
    with pytest.raises(InvalidInputError):
        validate_password("\ud800" * 8)


# --- Freno ai tentativi ---

def _fails(*seconds_ago):
    return [NOW - timedelta(seconds=s) for s in seconds_ago]


def test_sotto_soglia_il_tentativo_e_ammesso():
    assert login_retry_after(_fails(10, 20, 30, 40), NOW) is None
    assert LOGIN_MAX_FAILURES == 5


def test_alla_soglia_scatta_con_l_attesa_giusta():
    wait = login_retry_after(_fails(0, 10, 20, 30, 40), NOW)
    assert wait == LOGIN_FAILURE_WINDOW - timedelta(seconds=40)  # scade prima il più vecchio (40 s fa)


def test_oltre_soglia_l_attesa_e_quella_che_riporta_sotto():
    # con 6 errori, scaduto il più vecchio (50 s fa) se ne restano 5: si è ancora a soglia, serve che scada anche il successivo (40 s fa)
    wait = login_retry_after(_fails(0, 10, 20, 30, 40, 50), NOW)
    assert wait == LOGIN_FAILURE_WINDOW - timedelta(seconds=40)


def test_gli_errori_fuori_finestra_non_contano():
    old = LOGIN_FAILURE_WINDOW.total_seconds() + 1
    assert login_retry_after(_fails(old, old, old, old, old, 5), NOW) is None
    assert recent_failures(_fails(old, 5), NOW) == _fails(5)


def test_il_confine_della_finestra_e_esatto():
    edge = LOGIN_FAILURE_WINDOW.total_seconds()
    assert login_retry_after(_fails(edge, 1, 2, 3, 4), NOW) is None  # un errore di esattamente 15 minuti fa è scaduto
    assert login_retry_after(_fails(edge - 1, 1, 2, 3, 4), NOW) == timedelta(seconds=1)


def test_nessun_errore():
    assert login_retry_after([], NOW) is None


def test_chiave_normalizzata_come_il_provider():
    assert login_throttle_key("  Bar@Sole.IT ") == "email:bar@sole.it"


@pytest.mark.parametrize("failures, warned", [(1, False), (2, False), (3, True), (4, True), (5, False)])  # al 5°: «sospeso»
def test_avviso_solo_tra_il_terzo_e_il_quarto_errore(failures, warned):
    message = login_failure_message(failures)
    assert message.startswith("Credenziali non valide")
    assert ("Attenzione" in message) is warned
    if warned:
        assert "5 errori" in message and "15 minuti" in message


def test_errore_troppi_tentativi_porta_l_attesa_e_non_il_valore():
    err = TooManyAttemptsError(61)
    assert err.retry_after == 61
    assert "2 minuti" in str(err)
    assert "1 minuto" in str(TooManyAttemptsError(30))
