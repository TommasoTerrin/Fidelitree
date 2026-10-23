"""
Test unit di app/core/crypto.py: cifratura, indice cieco, token del link.
Nessun DB e nessuna rete: le chiavi sono passate come argomento.
"""

import base64
import re

import pytest

from app.core import crypto
from app.core.crypto import (
    SecretDecryptionError,
    card_link_token,
    constant_time_equals,
    decrypt_secret,
    encrypt_secret,
    igsid_blind_index,
    mask_secret,
    token_hash,
    validate_keys,
)

KEY = base64.urlsafe_b64encode(b"A" * 32).decode()
OTHER_KEY = base64.urlsafe_b64encode(b"B" * 32).decode()
SECRET = "sk_segretissima_1234"


def enc(plaintext: str = SECRET, key: str = KEY, key_id: str = "1") -> str:
    return encrypt_secret(plaintext, key=key, key_id=key_id)


# --- Cifratura, casi base ---

def test_cifra_e_decifra_round_trip():
    assert decrypt_secret(enc(), keys={"1": KEY}) == SECRET


def test_due_cifrature_dello_stesso_testo_sono_diverse():
    assert enc() != enc()


def test_risultato_inizia_con_id_chiave():
    assert enc(key_id="7").startswith("7:")
    assert enc().startswith("1:")


def test_il_cifrato_non_contiene_il_testo_in_chiaro():
    assert SECRET not in enc()


def test_default_dalle_settings():
    """Senza argomenti usa ENCRYPTION_KEY e ENCRYPTION_KEY_ID delle settings (chiavi del conftest)."""
    assert decrypt_secret(encrypt_secret(SECRET)) == SECRET


# --- Cifratura, errori ---

def _assert_error_without_secret(stored: str, keys: dict[str, str]):
    with pytest.raises(SecretDecryptionError) as exc:
        decrypt_secret(stored, keys=keys)
    assert SECRET not in str(exc.value)
    assert stored not in str(exc.value)


def test_byte_alterato_solleva_errore():
    key_id, payload = enc().split(":", 1)
    raw = bytearray(base64.urlsafe_b64decode(payload))
    raw[-1] ^= 0x01
    tampered = f"{key_id}:{base64.urlsafe_b64encode(bytes(raw)).decode()}"
    _assert_error_without_secret(tampered, {"1": KEY})


def test_id_chiave_sconosciuto_solleva_errore():
    _assert_error_without_secret(enc(key_id="9"), {"1": KEY})


def test_chiave_sbagliata_solleva_errore():
    _assert_error_without_secret(enc(), {"1": OTHER_KEY})


def test_stringa_senza_due_punti_solleva_errore():
    _assert_error_without_secret("senzaseparatore", {"1": KEY})


def test_base64_non_valido_solleva_errore():
    _assert_error_without_secret("1:%%%non-base64%%%", {"1": KEY})


def test_payload_troppo_corto_solleva_errore():
    short = base64.urlsafe_b64encode(b"corto").decode()
    _assert_error_without_secret(f"1:{short}", {"1": KEY})


def test_chiave_di_cifratura_non_valida_non_stampa_il_dato():
    with pytest.raises(ValueError) as exc:
        encrypt_secret(SECRET, key="troppo-corta", key_id="1")
    assert SECRET not in str(exc.value)


# --- Indice cieco ---

def test_indice_cieco_deterministico_e_hex_64():
    a = igsid_blind_index("17841400000000000", key="k1")
    assert a == igsid_blind_index("17841400000000000", key="k1")
    assert re.fullmatch(r"[0-9a-f]{64}", a)


def test_indice_cieco_cambia_con_igsid_e_con_chiave():
    base = igsid_blind_index("111", key="k1")
    assert base != igsid_blind_index("222", key="k1")
    assert base != igsid_blind_index("111", key="k2")


def test_indice_cieco_non_contiene_igsid():
    assert "17841400000000000" not in igsid_blind_index("17841400000000000", key="k1")


def test_indice_cieco_default_dalle_settings():
    assert igsid_blind_index("111") == igsid_blind_index("111")


# --- Token del link ---

def test_token_deterministico_per_carta_e_versione():
    assert card_link_token(5, 1, key="k") == card_link_token(5, 1, key="k")


def test_token_cambia_con_versione_carta_e_chiave():
    base = card_link_token(5, 1, key="k")
    assert base != card_link_token(5, 2, key="k")
    assert base != card_link_token(6, 1, key="k")
    assert base != card_link_token(5, 1, key="altra")


def test_token_e_base64url_senza_padding_di_43_caratteri():
    token = card_link_token(5, 1, key="k")
    assert "=" not in token
    assert re.fullmatch(r"[A-Za-z0-9_-]{43,}", token)


def test_token_hash_e_sha256_hex_diverso_dal_token():
    token = card_link_token(5, 1, key="k")
    h = token_hash(token)
    assert h != token
    assert re.fullmatch(r"[0-9a-f]{64}", h)
    assert h == token_hash(token)


def test_token_default_dalle_settings():
    assert card_link_token(1, 1) == card_link_token(1, 1)


# --- mask_secret ---

def test_mask_secret_mostra_solo_le_ultime_4():
    assert mask_secret("sk_abcdef1234") == "…1234"


def test_mask_secret_vuota():
    assert mask_secret("") == "(vuota)"


def test_mask_secret_corta_non_rivela_tutto():
    assert mask_secret("ab") == "…"
    assert mask_secret("abcd") == "…"
    assert mask_secret("abcde") == "…bcde"


# --- constant_time_equals ---

def test_constant_time_equals():
    assert constant_time_equals("abc", "abc")
    assert not constant_time_equals("abc", "abd")
    assert not constant_time_equals("abc", "abcd")
    assert constant_time_equals("è", "è")  # non-ASCII: compare_digest su str lo rifiuterebbe


# --- validate_keys ---

LONG = "x" * 32


def test_validate_keys_con_chiavi_valide_non_solleva():
    validate_keys(encryption_key=KEY, igsid_key=LONG, link_key=LONG)


def test_validate_keys_con_le_settings_del_conftest():
    validate_keys()


@pytest.mark.parametrize("bad", ["corta", "%%%non-base64%%%", base64.urlsafe_b64encode(b"A" * 16).decode()])
def test_validate_keys_encryption_key_non_valida(bad):
    with pytest.raises(RuntimeError) as exc:
        validate_keys(encryption_key=bad, igsid_key=LONG, link_key=LONG)
    assert bad not in str(exc.value)


def test_validate_keys_chiavi_hmac_corte():
    with pytest.raises(RuntimeError):
        validate_keys(encryption_key=KEY, igsid_key="corta", link_key=LONG)
    with pytest.raises(RuntimeError):
        validate_keys(encryption_key=KEY, igsid_key=LONG, link_key="corta")
