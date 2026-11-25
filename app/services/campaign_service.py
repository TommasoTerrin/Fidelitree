"""
Campagne promozionali del negozio: validazione, confronto delle parole chiave e testi dei DM.

La sezione «Core puro» usa solo libreria standard e Pydantic: nessun I/O, nessun orologio.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel

from app.core.enums import ServiceState
from app.core.errors import ConflictError, InvalidInputError, MessageTooLongError, NotFoundError
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


# --- Shell ---

# Gli import della shell stanno qui sotto, non in cima: il core puro sopra dipende solo da stdlib e Pydantic.
from sqlmodel import Session  # noqa: E402

from app.core.clock import utc_now  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.models.models import Campaign, Card, Merchant  # noqa: E402
from app.services import card_service  # noqa: E402
from app.services.db_crud import campaign_crud, card_crud  # noqa: E402


@dataclass
class ApplyResult:
    """Esito di un'applicazione: la carta ricaricata dopo gli UPDATE e i centesimi accreditati (contract §5)."""

    card: Card
    applied_cents: int


def list_campaigns(session: Session, merchant: Merchant) -> list[CampaignRow]:
    """
    Campagne del negozio per `/admin` (AC-01), nell'ordine D11 deciso dal crud.

    Lo stato di ogni riga si deriva da quello del negozio (R3), calcolato una volta sola.
    """
    state = card_service.merchant_state(merchant)
    return [campaign_row(c, state) for c in campaign_crud.list_campaigns_by_merchant(session, merchant.id)]


def scanner_campaigns(session: Session, merchant: Merchant) -> list[ScannerCampaign]:
    """
    Campagne non archiviate del negozio per i bottoni dello scanner (AC-21, AC-23).

    Ordine: `created_at` decrescente, poi `id` decrescente. Lista vuota se non ce ne sono: in quel caso
    la pagina non mostra il blocco. L'etichetta si compone con `scanner_label` (core puro).
    """
    campaigns = sorted(
        campaign_crud.list_active_campaigns_by_merchant(session, merchant.id),
        key=lambda c: (c.created_at, c.id),
        reverse=True,
    )
    return [
        ScannerCampaign(
            id=c.id, name=c.name, value_cents=c.value_cents, label=scanner_label(c.name, c.value_cents)
        )
        for c in campaigns
    ]


def apply_campaign(
    session: Session, merchant: Merchant, card_id: uuid.UUID, campaign_id: int
) -> ApplyResult:
    """
    Applica una campagna a una carta del negozio (AC-23, AC-24, AC-25, AC-26).

    Ordine dei controlli: carta non del negozio (404), campagna non del negozio (404), negozio non
    attivo con importo attuale positivo (403, prima di scrivere). Una campagna archiviata si applica
    (AC-25). Si accredita il `value_cents` ATTUALE della campagna e si conta un utilizzo, con un solo
    commit; con valore 0 conta solo l'utilizzo. Nessun movimento di tree points, pool o `PointTransaction`.
    """
    card = card_crud.get_card_by_id(session, card_id)
    if card is None or card.merchant_id != merchant.id:
        raise NotFoundError("Card non valida per questo merchant")
    campaign = get_campaign_for_merchant(session, merchant.id, campaign_id)
    value_cents = campaign.value_cents
    card_service.check_balance_change(card_service.merchant_state(merchant), value_cents)
    campaign_crud.apply_to_card(session, card.id, campaign.id, value_cents)
    session.refresh(card)  # ricarica la carta dopo gli UPDATE atomici
    return ApplyResult(card=card, applied_cents=value_cents)


def create_campaign(
    session: Session, merchant: Merchant, raw: object, now: datetime | None = None
) -> CampaignRow:
    """
    Crea una campagna del negozio (AC-02, AC-03). Ordine dei controlli: validazione (400), poi
    conflitto di parola chiave con le non archiviate del negozio e con quella della carta (409).

    Se un controllo fallisce non si scrive nulla. La campagna nasce non archiviata, con i contatori
    a 0 e `created_at = now` (UTC aware; senza `now` si usa `utc_now()`, come dice il contract §5). La parola della carta si legge
    qui, nella shell, e arriva al core come argomento.
    """
    data = validate_campaign_input(raw)
    others = [
        CampaignKey(id=c.id, keyword=c.keyword)
        for c in campaign_crud.list_active_campaigns_by_merchant(session, merchant.id)
    ]
    reason = keyword_conflict(data.keyword, settings.INSTAGRAM_CARD_KEYWORD, others)
    if reason is not None:
        raise ConflictError(f"Parola chiave: {reason}.")
    campaign = campaign_crud.create_campaign(
        session,
        merchant.id,
        data.name,
        data.keyword,
        data.promo_text,
        data.value_cents,
        data.request_limit,
        now or utc_now(),
    )
    return campaign_row(campaign, card_service.merchant_state(merchant))


def get_campaign_for_merchant(session: Session, merchant_id: int, campaign_id: int) -> Campaign:
    """
    Campagna del negozio per id. `NotFoundError` con lo stesso messaggio se non esiste o se è di
    un altro negozio, così l'esistenza di campagne altrui non si deduce dalla risposta.
    """
    campaign = campaign_crud.get_campaign(session, campaign_id)
    if campaign is None or campaign.merchant_id != merchant_id:
        raise NotFoundError("Campagna non trovata.")
    return campaign


def _keyword_conflict_for(session: Session, campaign, keyword: str, check_in_use: bool) -> str | None:
    """
    Motivo di conflitto della parola chiave per una campagna esistente, `None` se libera (AC-03).

    Si esclude la campagna stessa. `"riservata"` vale sempre; `"in uso"` solo se `check_in_use`
    (campagna destinata a essere non archiviata), perché le archiviate non occupano parole.
    """
    others = []
    if check_in_use:
        others = [
            CampaignKey(id=c.id, keyword=c.keyword)
            for c in campaign_crud.list_active_campaigns_by_merchant(session, campaign.merchant_id)
        ]
    return keyword_conflict(keyword, settings.INSTAGRAM_CARD_KEYWORD, others, exclude_id=campaign.id)


def update_campaign(
    session: Session, merchant: Merchant, campaign_id: int, raw: object
) -> CampaignRow:
    """
    Modifica una campagna del negozio (AC-04). Ordine dei controlli: 404 campagna non del negozio,
    400 validazione, 409 parola chiave.

    Sostituisce tutti i campi modificabili. Il conflitto «riservata» vale sempre; «in uso» solo se
    la campagna non è archiviata, escludendo se stessa. Se un controllo fallisce non si scrive nulla;
    contatori, `is_archived` e `created_at` restano invariati.
    """
    campaign = get_campaign_for_merchant(session, merchant.id, campaign_id)
    data = validate_campaign_input(raw)
    reason = _keyword_conflict_for(session, campaign, data.keyword, not campaign.is_archived)
    if reason is not None:
        raise ConflictError(f"Parola chiave: {reason}.")
    campaign = campaign_crud.update_campaign_fields(
        session, campaign, data.name, data.keyword, data.promo_text, data.value_cents, data.request_limit
    )
    return campaign_row(campaign, card_service.merchant_state(merchant))


def archive_on_pause(session: Session, merchant_id: int, before: ServiceState, after: ServiceState) -> int:
    """
    Archivia le campagne non archiviate del negozio se la pausa inizia ora (AC-08, `pause_begins`).

    Ritorna quante ne ha archiviate (0 se la pausa non inizia). NON fa commit: l'archiviazione e il cambio
    di stato del negozio vanno nello stesso commit (contract §5, §8). «Avvia» e «Riattiva» non ripristinano nulla.
    """
    if not pause_begins(before, after):
        return 0
    return campaign_crud.archive_active_campaigns_by_merchant(session, merchant_id)


def archive_campaign(session: Session, merchant: Merchant, campaign_id: int) -> CampaignRow:
    """Archivia una campagna del negozio (AC-05); idempotente: se è già archiviata non cambia nulla."""
    campaign = get_campaign_for_merchant(session, merchant.id, campaign_id)
    if not campaign.is_archived:
        campaign = campaign_crud.set_campaign_archived(session, campaign, True)
    return campaign_row(campaign, card_service.merchant_state(merchant))


def delete_campaign(session: Session, merchant: Merchant, campaign_id: int) -> None:
    """
    Elimina definitivamente una campagna del negozio, contatori compresi (contract §5).

    `NotFoundError` se non esiste o è di un altro negozio, quindi anche al secondo «Elimina». La sua
    parola chiave torna libera perché la riga sparisce.
    """
    campaign = get_campaign_for_merchant(session, merchant.id, campaign_id)
    campaign_crud.delete_campaign(session, campaign)


def restore_campaign(session: Session, merchant: Merchant, campaign_id: int) -> CampaignRow:
    """
    Ripristina una campagna archiviata (AC-06). Se è già non archiviata non cambia nulla; altrimenti
    la sua parola chiave non deve confliggere con la carta né con le non archiviate (esclusa se
    stessa), altrimenti `ConflictError` e la campagna resta archiviata.
    """
    campaign = get_campaign_for_merchant(session, merchant.id, campaign_id)
    if campaign.is_archived:
        reason = _keyword_conflict_for(session, campaign, campaign.keyword, True)
        if reason is not None:
            raise ConflictError(f"Parola chiave: {reason}.")
        campaign = campaign_crud.set_campaign_archived(session, campaign, False)
    return campaign_row(campaign, card_service.merchant_state(merchant))


class CampaignReply(BaseModel):
    """Risposta da inviare a chi ha scritto la parola di una campagna (contract §5)."""

    campaign_id: int
    text: str
    exhausted: bool  # vero se il testo è «offerte terminate»


def register_request(session: Session, campaign_id: int, channel: RequestChannel) -> int | None:
    """
    Conta una richiesta della campagna (AC-12) e ritorna il totale DM + commenti dopo l'incremento.

    Un solo `UPDATE ... RETURNING` atomico seguito da commit (via crud): il totale non si legge dall'oggetto
    in memoria, quindi richieste concorrenti ricevono totali distinti. `None` se la campagna è sparita.
    """
    return campaign_crud.increment_request_counter(session, campaign_id, channel.value)


def handle_campaign_request(
    session: Session, merchant: Merchant, text: str | None, channel: RequestChannel
) -> CampaignReply | None:
    """
    Riconosce la parola di una campagna non archiviata e prepara la risposta (AC-11, AC-12, AC-17).

    Tra le non archiviate (created_at decrescente) cerca la parola con `match_campaign`; nessuna → `None`.
    Negozio non ACTIVE → `None` e nessun conteggio. Altrimenti si conta la richiesta (`None` se la campagna
    è stata eliminata nel frattempo) e si sceglie il testo in base al totale. Un `MessageTooLongError` si
    propaga: la richiesta resta contata. Non si logga nulla del testo del cliente.
    """
    campaigns = sorted(
        campaign_crud.list_active_campaigns_by_merchant(session, merchant.id),
        key=lambda c: (c.created_at, c.id),
        reverse=True,
    )
    campaign_id = match_campaign(text, [CampaignKey(id=c.id, keyword=c.keyword) for c in campaigns])
    if campaign_id is None:
        return None
    if card_service.merchant_state(merchant) is not ServiceState.ACTIVE:
        return None
    total = register_request(session, campaign_id, channel)
    if total is None:
        return None
    campaign = next(c for c in campaigns if c.id == campaign_id)
    reply = campaign_reply_text(campaign.promo_text, total, campaign.request_limit, settings.INSTAGRAM_CARD_KEYWORD)
    return CampaignReply(
        campaign_id=campaign_id, text=reply, exhausted=not is_within_limit(total, campaign.request_limit)
    )
