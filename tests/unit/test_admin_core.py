"""
Core puro della dashboard admin: confronto della chiave, controllo dell'origine, token di sessione admin,
transizioni di stato, password temporanea e riga della lista. Nessun DB, nessuna rete, nessun mock.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.auth import LOGIN_MAX_FAILURES, admin_key_matches, validate_password
from app.core.enums import InstagramStatus, ServiceState
from app.core.errors import ConflictError, TooManyAttemptsError
from app.core.security import (
    ADMIN_SESSION_HOURS, create_admin_session_token, create_jwt_token, decode_jwt_token, is_admin_session_token,
    request_origin_allowed,
)
from app.services.merchant_service import (
    TEMP_PASSWORD_ALPHABET, TEMP_PASSWORD_LENGTH, AdminAction, admin_login_failure_message, admin_row,
    apply_admin_action, generate_temporary_password,
)


# --- admin_key_matches ---

def test_chiave_giusta_e_sbagliata():
    assert admin_key_matches("chiave-segreta", "chiave-segreta") is True
    assert admin_key_matches("chiave-segreta ", "chiave-segreta") is False
    assert admin_key_matches("altra", "chiave-segreta") is False


def test_chiave_configurata_vuota_non_fa_entrare_nessuno():
    """Fallisce chiuso: con `ADMIN_SECRET_KEY` vuota nemmeno una password vuota è ammessa."""
    assert admin_key_matches("", "") is False
    assert admin_key_matches("qualunque", "") is False


@pytest.mark.parametrize("provided", [None, 123, b"chiave-segreta", ["chiave-segreta"]])
def test_chiave_presentata_non_testuale_vale_falso(provided):
    assert admin_key_matches(provided, "chiave-segreta") is False


def test_chiave_con_caratteri_non_ascii_e_surrogati():
    assert admin_key_matches("pässword-è", "pässword-è") is True
    assert admin_key_matches("\ud800", "chiave") is False  # surrogato isolato: non si può codificare


# --- request_origin_allowed ---

@pytest.mark.parametrize("origin, referer, host, expected", [
    ("https://app.example", None, "app.example", True),
    ("http://app.example", None, "app.example", True),                 # lo schema non conta (proxy)
    ("HTTPS://APP.EXAMPLE", None, "app.example", True),
    (None, "https://app.example/admin", "app.example", True),          # senza Origin vale il Referer
    ("http://127.0.0.1:8001", None, "127.0.0.1:8001", True),
    ("https://evil.example", None, "app.example", False),
    ("https://app.example.evil.example", None, "app.example", False),
    ("https://app.example:8443", None, "app.example", False),          # porta diversa = origine diversa
    ("https://evil.example", "https://app.example/admin", "app.example", False),  # Origin ha la precedenza
    ("null", None, "app.example", False),                              # `Referrer-Policy: no-referrer`
    ("null", "https://app.example/admin", "app.example", False),
    (None, None, "app.example", False),
    ("", "", "app.example", False),
    ("https://app.example", None, None, False),
    ("https://app.example", None, "", False),
    ("non un url", None, "app.example", False),
    ("http://[::1", None, "app.example", False),                        # URL malformato: mai un'eccezione
])
def test_request_origin_allowed(origin, referer, host, expected):
    assert request_origin_allowed(origin, referer, host) is expected


# --- token di sessione admin ---

def test_token_admin_valido_e_scade_in_dodici_ore():
    token = create_admin_session_token()
    payload = decode_jwt_token(token)

    assert is_admin_session_token(token) is True
    assert payload["role"] == "admin" and "sub" not in payload and "email" not in payload
    remaining = datetime.fromtimestamp(payload["exp"], timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(hours=ADMIN_SESSION_HOURS - 1) < remaining <= timedelta(hours=ADMIN_SESSION_HOURS)


def test_token_admin_scaduto_manomesso_o_senza_ruolo_non_vale():
    expired = create_jwt_token({"role": "admin"}, expires_delta=timedelta(seconds=-5))
    merchant_like = create_jwt_token({"sub": "u1", "email": "a@b.it", "ver": 1})  # stessa chiave, niente `role`
    other_role = create_jwt_token({"role": "merchant"})
    good = create_admin_session_token()

    assert is_admin_session_token(expired) is False
    assert is_admin_session_token(merchant_like) is False
    assert is_admin_session_token(other_role) is False
    assert is_admin_session_token(good[:-3] + ("AAA" if not good.endswith("AAA") else "BBB")) is False
    assert is_admin_session_token("spazzatura") is False
    assert is_admin_session_token("") is False and is_admin_session_token(None) is False


def test_create_jwt_token_senza_scadenza_resta_a_sette_giorni():
    payload = decode_jwt_token(create_jwt_token({"sub": "x"}))
    remaining = datetime.fromtimestamp(payload["exp"], timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(days=6, hours=23) < remaining <= timedelta(days=7)


# --- messaggi del freno ---

def test_errore_429_di_default_invita_al_reset_e_quello_admin_no():
    assert "chiedi al founder di reimpostare la password" in str(TooManyAttemptsError(120))
    admin = str(TooManyAttemptsError(120, "oppure accedi con l'header X-Admin-Key"))
    assert "founder" not in admin and "X-Admin-Key" in admin and "2 minuti" in admin
    assert str(TooManyAttemptsError(30, "")).endswith("riprova tra 1 minuto")


def test_messaggio_di_login_admin_avvisa_dal_terzo_errore():
    assert admin_login_failure_message(1) == admin_login_failure_message(2) == "Password non valida"
    assert "Attenzione" in admin_login_failure_message(3) and "15 minuti" in admin_login_failure_message(3)
    assert "Accesso sospeso" in admin_login_failure_message(LOGIN_MAX_FAILURES)
    assert all("founder" not in admin_login_failure_message(n) for n in range(1, 8))


# --- transizioni di stato ---

@pytest.mark.parametrize("action, is_approved, is_paused, expected", [
    (AdminAction.APPROVE, False, False, (True, False)),   # avvia
    (AdminAction.APPROVE, False, True, (True, False)),    # un flag di pausa su un negozio in attesa non conta
    (AdminAction.APPROVE, True, True, (True, False)),     # approve toglie la pausa
    (AdminAction.APPROVE, True, False, (True, False)),    # già attivo: nessun cambio
    (AdminAction.PAUSE, True, False, (True, True)),
    (AdminAction.PAUSE, True, True, (True, True)),        # già in pausa: nessun cambio
    (AdminAction.RESUME, True, True, (True, False)),
    (AdminAction.RESUME, True, False, (True, False)),     # già attivo: nessun cambio
])
def test_apply_admin_action(action, is_approved, is_paused, expected):
    assert apply_admin_action(action, is_approved, is_paused) == expected


@pytest.mark.parametrize("action", [AdminAction.PAUSE, AdminAction.RESUME])
def test_pausa_e_riattivazione_di_un_negozio_in_attesa_sono_un_conflitto(action):
    with pytest.raises(ConflictError, match="in attesa"):
        apply_admin_action(action, False, False)


# --- password temporanea ---

def test_password_temporanea_ha_12_caratteri_dell_alfabeto_senza_ambigui():
    for _ in range(50):
        password = generate_temporary_password()
        assert len(password) == TEMP_PASSWORD_LENGTH == 12
        assert set(password) <= set(TEMP_PASSWORD_ALPHABET)
        assert validate_password(password) == password
    assert not set("0O1lI") & set(TEMP_PASSWORD_ALPHABET)


def test_password_temporanea_e_deterministica_con_choice_iniettata():
    assert generate_temporary_password(lambda alphabet: alphabet[0]) == "A" * 12
    seen = iter(range(100))
    assert generate_temporary_password(lambda alphabet: alphabet[next(seen) % len(alphabet)]) == TEMP_PASSWORD_ALPHABET[:12]


def test_password_temporanee_diverse_a_ogni_chiamata():
    assert len({generate_temporary_password() for _ in range(20)}) == 20


# --- riga della lista ---

def _merchant(**overrides):
    base = dict(
        id=7, business_name="Bar <b>Sole</b>", email="bar@sole.it", contact_phone="+393331234567",
        created_at=datetime(2026, 10, 27, 9, 30), is_approved=True, is_paused=False,
        instagram_status=InstagramStatus.ACTIVE, instagram_username="bar_sole", auth_user_id="uid-1",
        # campi che NON devono arrivare nella riga
        zernio_api_key_enc="CIFRATA", webhook_secret_enc="SEGRETO", webhook_hook_id="hook-opaco",
    )
    return SimpleNamespace(**{**base, **overrides})


def test_riga_admin_contiene_solo_i_campi_previsti_e_nessun_segreto():
    row = admin_row(_merchant(), cards_count=3, month_points=42)

    assert set(row.model_dump()) == {
        "id", "business_name", "email", "contact_phone", "created_at", "service_state", "instagram_status",
        "instagram_username", "cards_count", "month_points", "can_reset_password",
    }
    dumped = repr(row.model_dump(mode="json"))
    assert all(secret not in dumped for secret in ("CIFRATA", "SEGRETO", "hook-opaco", "uid-1"))
    assert (row.cards_count, row.month_points, row.can_reset_password) == (3, 42, True)
    assert row.business_name == "Bar <b>Sole</b>"  # il dato non si altera: l'escape è della pagina


def test_riga_admin_data_senza_fuso_vale_utc():
    assert admin_row(_merchant(), 0, 0).created_at == datetime(2026, 10, 27, 9, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize("is_approved, is_paused, state", [
    (False, False, ServiceState.PENDING),
    (False, True, ServiceState.PENDING),   # la pausa conta solo se approvato
    (True, False, ServiceState.ACTIVE),
    (True, True, ServiceState.PAUSED),
])
def test_riga_admin_stato_del_servizio(is_approved, is_paused, state):
    assert admin_row(_merchant(is_approved=is_approved, is_paused=is_paused), 0, 0).service_state is state


def test_riga_admin_senza_auth_user_id_non_puo_reimpostare_la_password():
    assert admin_row(_merchant(auth_user_id=None), 0, 0).can_reset_password is False
