"""
Testo dei messaggi Instagram: normalizzazione per i confronti e limite di lunghezza.

Modulo del core puro: solo libreria standard, nessun I/O. Lo usano `instagram_service`
(riconoscimento della parola chiave `CARTA`) e `campaign_service` (parole chiave delle campagne).
"""

import re
import unicodedata
from typing import Optional

# Caratteri (len() di Python) ammessi in un DM di testo o in una risposta privata.
INSTAGRAM_TEXT_MAX = 1000


def normalize_text(text: Optional[str]) -> str:
    """
    Normalizza il testo di un messaggio per il confronto con la parola chiave: NFKD senza segni
    diacritici, `casefold`, solo lettere, cifre e spazi (punteggiatura ed emoji cadono), spazi compattati.
    `None` o stringa vuota → stringa vuota.
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()
    letters = "".join(ch if ch.isalnum() else " " for ch in stripped)
    return re.sub(r"\s+", " ", letters).strip()
