"""
Test del core puro dei testi dei DM di `campaign_service` (nessun DB, nessun mock).
v0.4.1, ticket 01, AC-27 (prima fetta: testo della promo, «offerte terminate», limite dei 1000 caratteri).
"""

import pytest

from app.core.errors import InvalidInputError, MessageTooLongError
from app.core.text import INSTAGRAM_TEXT_MAX
from app.services.campaign_service import (build_exhausted_text, build_promo_text, campaign_reply_text,
                                           is_within_limit)


def test_testo_promo_ha_la_riga_fissa_e_con_850_caratteri_sta_sotto_il_limite():
    """
    AC-27: il DM della promo è il testo della campagna, una riga vuota e la riga fissa con la parola della carta;
    il testo «offerte terminate» è la frase fissa del contract. Con una promo di 850 caratteri e "CARTA" il DM
    completo resta sotto INSTAGRAM_TEXT_MAX: 850 più la riga fissa (circa 140 caratteri) lascia margine, ed è
    proprio il tetto di 850 a garantirlo. I valori attesi sono letterali scritti a mano dal contract §4
    (apostrofo ASCII, lettere accentate), non ricostruiti con le costanti del codice.
    """
    # Testo esatto, byte per byte.
    atteso = ("Sconto 10%\n\n"
              "Per utilizzare questa offerta devi avere la nostra carta fedeltà. "
              "Se non l'hai ricevuta o non la ritrovi nella chat scrivi CARTA.")
    assert build_promo_text("Sconto 10%", "CARTA") == atteso

    # Testo delle offerte terminate, letterale.
    assert build_exhausted_text() == (
        "Le offerte disponibili sono terminate. Per essere informato più velocemente la prossima volta "
        "attiva la campanella delle notifiche al profilo!!")

    # Promo al massimo (850): il DM completo ci sta.
    lungo = build_promo_text("a" * 850, "CARTA")
    assert lungo.startswith("a" * 850 + "\n\n")
    assert len(lungo) < INSTAGRAM_TEXT_MAX


def test_errori_dei_testi_e_scelta_tra_promo_e_offerte_terminate_al_limite():
    """
    AC-27 (seconda fetta): una promo vuota o di soli spazi dà InvalidInputError; una promo di 1000 caratteri, che
    con la riga fissa supera INSTAGRAM_TEXT_MAX, dà MessageTooLongError e non un testo troncato. La risposta alla
    richiesta è la promo finché total_requests <= request_limit (anche a parità: l'ultima richiesta ammessa è la
    n-esima) e il testo «offerte terminate» dalla successiva; senza limite è sempre la promo. I testi attesi sono
    letterali del contract §4 e i confini di is_within_limit sono numeri scritti a mano.
    """
    # Promo vuota o di soli spazi: input non valido.
    for vuota in ("", "   ", "\n\t "):
        with pytest.raises(InvalidInputError):
            build_promo_text(vuota, "CARTA")

    # Promo oltre il tetto: il DM completo supera il limite e viene rifiutato.
    with pytest.raises(MessageTooLongError):
        build_promo_text("a" * 1000, "CARTA")

    # Confini di is_within_limit.
    assert is_within_limit(5, None) is True
    assert is_within_limit(5, 5) is True
    assert is_within_limit(6, 5) is False

    promo_atteso = ("Sconto 10%\n\n"
                    "Per utilizzare questa offerta devi avere la nostra carta fedeltà. "
                    "Se non l'hai ricevuta o non la ritrovi nella chat scrivi CARTA.")
    terminate_atteso = ("Le offerte disponibili sono terminate. Per essere informato più velocemente la prossima "
                        "volta attiva la campanella delle notifiche al profilo!!")

    # Sul limite (uguale) e senza limite: la promo.
    assert campaign_reply_text("Sconto 10%", 5, 5, "CARTA") == promo_atteso
    assert campaign_reply_text("Sconto 10%", 1000, None, "CARTA") == promo_atteso
    # Oltre il limite: offerte terminate.
    assert campaign_reply_text("Sconto 10%", 6, 5, "CARTA") == terminate_atteso
