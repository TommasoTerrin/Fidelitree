"""
Enumerazioni di dominio condivise da modelli e core puro.

Solo libreria standard: questo modulo non deve dipendere da SQLModel né da
FastAPI, perché lo importano sia i modelli sia il core dei service.
"""

from enum import Enum


class PointTransactionKind(str, Enum):
    """Tipo di movimento di tree points nel registro."""
    SCAN = "scan"              # accredito/addebito del merchant (conta nel pool)
    CONVERSION = "conversion"  # conversione automatica in cashback (non tocca il pool)


class InstagramStatus(str, Enum):
    """Stato del collegamento Instagram (Zernio) di un negozio."""
    NOT_CONNECTED = "not_connected"        # nessuna chiave Zernio collegata
    AWAITING_TEST_DM = "awaiting_test_dm"  # collegato, in attesa del DM di prova
    ACTIVE = "active"                      # il DM di prova è arrivato: la carta funziona
    KEY_INVALID = "key_invalid"            # Zernio ha rifiutato la chiave (401/403)


class WebhookOutcome(str, Enum):
    """Esito dell'elaborazione di un evento webhook Zernio (tabella di dedup)."""
    RECEIVED = "received"              # stato iniziale, prima dell'elaborazione
    SENT = "sent"                      # card inviata
    FALLBACK_SENT = "fallback_sent"    # card rifiutata da Meta: inviato il testo con il link
    IGNORED = "ignored"                # messaggio senza parola chiave / evento non pertinente
    STANDBY = "standby"                # conversazione di un'altra app: nessuna risposta
    SEND_FAILED = "send_failed"        # invio fallito
    OUT_OF_WINDOW = "out_of_window"    # oltre le 24 h dal messaggio del cliente


class Level(str, Enum):
    """Livello raggiunto dal pool mensile di un negozio."""
    NONE = "none"
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
