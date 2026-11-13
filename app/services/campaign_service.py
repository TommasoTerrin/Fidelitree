"""
Campagne promozionali del negozio: validazione, confronto delle parole chiave e testi dei DM.

La sezione «Core puro» usa solo libreria standard e Pydantic: nessun I/O, nessun orologio.
"""

from collections.abc import Iterable
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel

from app.core.enums import ServiceState
from app.core.errors import InvalidInputError, MessageTooLongError
from app.core.money import euro_to_cents
from app.core.text import INSTAGRAM_TEXT_MAX, normalize_text

# --- Core puro ---

# Limiti di lunghezza (in caratteri) dei campi di una campagna (contract §1).
NAME_MIN, NAME_MAX = 3, 40
KEYWORD_MIN, KEYWORD_MAX = 3, 30  # sulla forma scritta (dopo lo strip)
PROMO_TEXT_MIN, PROMO_TEXT_MAX = 1, 850
VALUE_MIN_CENTS, VALUE_MAX_CENTS = 0, 5000


class CampaignStatus(str, Enum):
    """Stato di una campagna: non è una colonna, si deriva da archiviazione e stato del negozio (R3)."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    STOPPED = "stopped"  # negozio in attesa o in pausa


class CampaignInput(BaseModel):
    """Dati di una campagna già validati (contract §4)."""

    name: str
    keyword: str
    promo_text: str
    value_cents: int
    request_limit: int | None


class CampaignKey(BaseModel):
    """Quanto serve al confronto delle parole chiave: id e parola come salvata (contract §4)."""

    id: int
    keyword: str  # forma scritta, mai normalizzata


def keyword_conflict(
    keyword: str,
    card_keyword: str,
    others: Iterable[CampaignKey],
    exclude_id: int | None = None,
) -> str | None:
    """
    Dice se la parola chiave è libera (AC-03): `None` se libera, altrimenti il motivo.

    Il confronto avviene sulla forma normalizzata. `"riservata"` se coincide con la parola della
    carta; `"in uso"` se coincide con quella di una campagna di `others` con `id != exclude_id`.
    `others` contiene solo le campagne non archiviate del negozio: lo filtra il chiamante.
    """
    normalized = normalize_text(keyword)
    if normalized == normalize_text(card_keyword):
        return "riservata"
    for other in others:
        if other.id != exclude_id and normalize_text(other.keyword) == normalized:
            return "in uso"
    return None


def match_campaign(text: str | None, campaigns: Iterable[CampaignKey]) -> int | None:
    """
    Riconosce la campagna richiesta da un testo (AC-09): id della prima, nell'ordine dato, la cui
    parola normalizzata coincide con il testo normalizzato.

    Testo assente o vuoto dopo la normalizzazione dà `None`. Il chiamante passa solo le non archiviate.
    """
    normalized = normalize_text(text or "")
    if not normalized:
        return None
    for campaign in campaigns:
        if normalize_text(campaign.keyword) == normalized:
            return campaign.id
    return None


def validate_campaign_input(raw: object) -> CampaignInput:
    """
    Valida il corpo grezzo di una campagna (AC-03). Per ora controlla `name` e `keyword`.

    `name`: stringa, strip, 3-40 caratteri. `keyword`: stringa, strip, nessuno spazio all'interno,
    3-30 caratteri e non vuota dopo `normalize_text`; si salva la forma scritta, mai normalizzata.
    Il messaggio d'errore cita campo e regola, mai il valore inviato.
    """
    if not isinstance(raw, dict):
        raise InvalidInputError("Corpo della richiesta: deve essere un oggetto.")

    name = raw.get("name")
    if not isinstance(name, str):
        raise InvalidInputError("Nome: deve essere una stringa.")
    name = name.strip()
    if not NAME_MIN <= len(name) <= NAME_MAX:
        raise InvalidInputError(f"Nome: deve avere da {NAME_MIN} a {NAME_MAX} caratteri.")

    keyword = raw.get("keyword")
    if not isinstance(keyword, str):
        raise InvalidInputError("Parola chiave: deve essere una stringa.")
    keyword = keyword.strip()
    if any(ch.isspace() for ch in keyword):
        raise InvalidInputError("Parola chiave: non può contenere spazi.")
    if not KEYWORD_MIN <= len(keyword) <= KEYWORD_MAX:
        raise InvalidInputError(
            f"Parola chiave: deve avere da {KEYWORD_MIN} a {KEYWORD_MAX} caratteri."
        )
    if not normalize_text(keyword):
        raise InvalidInputError("Parola chiave: deve contenere almeno una lettera o una cifra.")

    promo_text = raw.get("promo_text")
    if not isinstance(promo_text, str):
        raise InvalidInputError("Testo della promo: deve essere una stringa.")
    promo_text = promo_text.strip()
    if not PROMO_TEXT_MIN <= len(promo_text) <= PROMO_TEXT_MAX:
        raise InvalidInputError(
            f"Testo della promo: deve avere da {PROMO_TEXT_MIN} a {PROMO_TEXT_MAX} caratteri."
        )

    value_cents = _parse_value_cents(raw.get("value_eur"))

    return CampaignInput(
        name=name,
        keyword=keyword,
        promo_text=promo_text,
        value_cents=value_cents,
        request_limit=_parse_request_limit(raw.get("request_limit")),
    )


# Testi dei DM, byte per byte come nel contract (R7, AC-27). L'apostrofo di «l'hai» è l'ASCII.
PROMO_FOOTER = (
    "Per utilizzare questa offerta devi avere la nostra carta fedeltà. "
    "Se non l'hai ricevuta o non la ritrovi nella chat scrivi {keyword}."
)
EXHAUSTED_TEXT = (
    "Le offerte disponibili sono terminate. Per essere informato più velocemente la prossima volta "
    "attiva la campanella delle notifiche al profilo!!"
)


def is_within_limit(total_requests: int, request_limit: int | None) -> bool:
    """
    Dice se la richiesta rientra nel limite della campagna (contract §4).

    Senza limite (`None`) è sempre vero; altrimenti `total_requests` (DM + commenti, già
    incrementato dalla richiesta in corso) deve essere al massimo `request_limit`.
    """
    return request_limit is None or total_requests <= request_limit


def campaign_status(is_archived: bool, merchant_state: ServiceState) -> CampaignStatus:
    """
    Deriva lo stato della campagna (R3): `ARCHIVED` se archiviata; altrimenti `ACTIVE` con negozio
    attivo e `STOPPED` con negozio in attesa o in pausa.
    """
    if is_archived:
        return CampaignStatus.ARCHIVED
    if merchant_state is ServiceState.ACTIVE:
        return CampaignStatus.ACTIVE
    return CampaignStatus.STOPPED


class RequestChannel(str, Enum):
    """Canale da cui arriva la richiesta di una campagna (contract §4)."""

    DM = "dm"  # DM e risposte alle storie
    COMMENT = "comment"


class CampaignRow(BaseModel):
    """Riga di una campagna per `/admin`: campi salvati, contatori e stato derivato (contract §4)."""

    id: int
    merchant_id: int
    name: str
    keyword: str
    promo_text: str
    value_cents: int
    request_limit: int | None
    is_archived: bool
    status: CampaignStatus
    dm_requests: int
    comment_requests: int
    uses: int
    created_at: datetime


class ScannerCampaign(BaseModel):
    """Campagna per lo scanner: id, nome, valore e etichetta del bottone (contract §4, AC-21)."""

    id: int
    name: str
    value_cents: int
    label: str


def campaign_row(campaign, merchant_state: ServiceState) -> CampaignRow:
    """
    Costruisce la riga della campagna con lo stato derivato dal negozio (R3).

    `created_at` senza fuso è letto come UTC (invariante dei timestamp UTC aware); se ha già un fuso
    resta com'è. Funzione pura: non tocca il DB.
    """
    created_at = campaign.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return CampaignRow(
        id=campaign.id,
        merchant_id=campaign.merchant_id,
        name=campaign.name,
        keyword=campaign.keyword,
        promo_text=campaign.promo_text,
        value_cents=campaign.value_cents,
        request_limit=campaign.request_limit,
        is_archived=campaign.is_archived,
        status=campaign_status(campaign.is_archived, merchant_state),
        dm_requests=campaign.dm_requests,
        comment_requests=campaign.comment_requests,
        uses=campaign.uses,
        created_at=created_at,
    )


def pause_begins(before: ServiceState, after: ServiceState) -> bool:
    """Dice se la pausa inizia ora (AC-08): vero solo se `after` è `PAUSED` e `before` no."""
    return after is ServiceState.PAUSED and before is not ServiceState.PAUSED


def scanner_label(name: str, value_cents: int) -> str:
    """
    Etichetta del bottone dello scanner (AC-21): «Applica {name}», con «(+X,XX €)» se il valore è positivo.

    L'importo ha sempre due decimali e la virgola (250 diventa «2,50»).
    """
    if value_cents > 0:
        euro = f"{value_cents // 100},{value_cents % 100:02d}"
        return f"Applica {name} (+{euro} €)"
    return f"Applica {name}"


def build_promo_text(promo_text: str, card_keyword: str) -> str:
    """
    Compone il DM della promo: testo del negozio, riga vuota e riga fissa sulla carta (AC-27).

    `InvalidInputError` se la promo è vuota dopo lo strip; `MessageTooLongError` se il totale supera
    `INSTAGRAM_TEXT_MAX`, perché Instagram rifiuterebbe il messaggio.
    """
    promo_text = promo_text.strip()
    if not promo_text:
        raise InvalidInputError("Testo della promo: non può essere vuoto.")
    text = f"{promo_text}\n\n" + PROMO_FOOTER.format(keyword=card_keyword)
    if len(text) > INSTAGRAM_TEXT_MAX:
        raise MessageTooLongError("Testo della promo: il messaggio completo supera il limite di Instagram.")
    return text


def build_exhausted_text() -> str:
    """Restituisce il DM «offerte terminate» inviato oltre il limite della campagna (AC-27)."""
    return EXHAUSTED_TEXT


def campaign_reply_text(
    promo_text: str, total_requests: int, request_limit: int | None, card_keyword: str
) -> str:
    """
    Sceglie il DM di risposta: la promo se la richiesta rientra nel limite, altrimenti il testo
    delle offerte terminate (contract §4).
    """
    if is_within_limit(total_requests, request_limit):
        return build_promo_text(promo_text, card_keyword)
    return build_exhausted_text()


def _parse_request_limit(value: object) -> int | None:
    """
    Converte il limite di richieste della campagna (AC-03, decisione 12).

    Assente, `None` o stringa vuota valgono «nessun limite» (`None`). Sono ammessi `int` (non `bool`),
    `float` senza parte decimale e stringhe di sole cifre; il limite deve essere almeno 1.
    Qualunque altro tipo o valore solleva `InvalidInputError`; il messaggio non riporta mai il valore inviato.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    message = "Limite di richieste: deve essere un numero intero di almeno 1."
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise InvalidInputError(message)
    if isinstance(value, str):
        text = value.strip()
        # Solo cifre ASCII: `isdigit` da solo accetterebbe anche cifre unicode non convertibili.
        if not (text.isascii() and text.isdigit()):
            raise InvalidInputError(message)
        number = int(text)
    elif isinstance(value, float):
        # NaN e infiniti non sono interi: is_integer() li scarta senza sollevare eccezioni.
        if not value.is_integer():
            raise InvalidInputError(message)
        number = int(value)
    else:
        number = value
    if number < 1:
        raise InvalidInputError(message)
    return number


def _parse_value_cents(value: object) -> int:
    """
    Converte il valore in euro della campagna in centesimi interi (AC-03, decisione 12).

    Assente, `None` o stringa vuota valgono 0. Sono ammessi `int`/`float` (non `bool`) e stringhe
    numeriche con virgola o punto decimale. Valori non numerici o non finiti e importi fuori da
    0-5000 centesimi sollevano `InvalidInputError`; il messaggio non riporta mai il valore inviato.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return 0
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise InvalidInputError("Valore: deve essere un numero in euro.")
    if isinstance(value, str):
        try:
            number = float(value.strip().replace(",", "."))
        except ValueError:
            raise InvalidInputError("Valore: deve essere un numero in euro.") from None
    else:
        number = value
    try:
        cents = euro_to_cents(number)
    except (ValueError, OverflowError):
        raise InvalidInputError("Valore: deve essere un numero finito.") from None
    if not VALUE_MIN_CENTS <= cents <= VALUE_MAX_CENTS:
        raise InvalidInputError(
            f"Valore: deve essere tra {VALUE_MIN_CENTS / 100:.0f} e {VALUE_MAX_CENTS / 100:.0f} euro."
        )
    return cents
