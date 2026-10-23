"""
Carta fedeltà via DM Instagram (Zernio): regole del flusso dei messaggi.

Regole di business
------------------
- **Trigger**: il cliente scrive la parola chiave unica di piattaforma (`INSTAGRAM_CARD_KEYWORD`,
  default `CARTA`) oppure tocca la voce "🌳 La mia carta" del menu persistente (postback con payload
  fisso). Maiuscole, accenti, punteggiatura ed emoji sono ignorati; la corrispondenza è esatta dopo la
  normalizzazione ("carta" vale, "vorrei la carta" no). Gli altri messaggi sono ignorati in silenzio.
- **Risposta**: una sola card (generic template) con titolo = nome del negozio, sottotitolo fisso e un
  bottone "Apri la carta". Nessun dato dinamico nel messaggio. Unico ripiego: un testo fisso con il link.
- **Carta solo a chi segue** (2026-10-23): `isFollower` falso → nessuna carta, solo un testo fisso di invito a
  seguire il profilo; `null`/assente → card (da rivedere nel collaudo finale).
- **Finestra**: si risponde solo entro 24 ore dal messaggio del cliente (`sentAt`, non l'ora di consegna
  del webhook). Nessun invio proattivo.
- **Quota**: Zernio regala 10.000 invii al mese per team; noi li contiamo e avvisiamo, non blocchiamo.
- **Testo dei clienti**: mai salvato; qui lo si legge solo per riconoscere il trigger.

Il core usa solo Pydantic e stdlib: il tempo si passa come argomento, niente DB né rete. La shell
(`get_or_create_card`, `card_link_url`, `handle_webhook`) legge il webhook, salva la carta e invia tramite
`zernio_service`. Fonti dei limiti e del formato dei payload: `.agents/architecture/zernio-notes.md`.
"""

import hashlib
import hmac
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from app.core.errors import InvalidInputError, MessageTooLongError

# --- Core puro ---

CARD_POSTBACK_PAYLOAD = "FIDELITREE_CARD"   # payload fisso del bottone del menu persistente
MENU_ITEM_TITLE = "🌳 La mia carta"
CARD_SUBTITLE = "La tua carta fedeltà: punti, cashback e alberi 🌳"
CARD_BUTTON_TITLE = "Apri la carta"
REPLY_WINDOW = timedelta(hours=24)  # finestra standard di Meta, dal messaggio del cliente

# Limiti di caratteri (fonti: Meta generic template e spec Zernio `sendInboxMessage`, vedi zernio-notes)
CARD_TITLE_MAX = 80
CARD_SUBTITLE_MAX = 80
CARD_BUTTON_TITLE_MAX = 20
FALLBACK_TEXT_MAX = 640  # minimo documentato per il testo con bottoni su Instagram

_MESSAGE_RECEIVED = "message.received"
_SOURCE_TEXT = "dm_text"
_SOURCE_POSTBACK = "dm_postback"
_DIRECTION_INCOMING = "incoming"


class InboundMessage(BaseModel):
    """Messaggio del cliente già normalizzato; `source` distingue l'origine (oggi solo DM)."""

    event_id: str
    source: str  # "dm_text" | "dm_postback"; in futuro commenti e risposte alle storie
    account_id: str
    conversation_id: str
    sender_id: str
    direction: str  # "incoming" | "outgoing"
    text: Optional[str] = None
    postback_payload: Optional[str] = None
    sent_at: datetime  # aware
    standby: bool = False
    is_follower: Optional[bool] = None  # il cliente segue il negozio? `None` = dato non disponibile


def _required(container: object, *path: str) -> object:
    """Scende lungo `path` in dizionari annidati; `InvalidInputError` se manca un anello o il valore è vuoto."""
    value = container
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    if value is None or value == "":
        raise InvalidInputError(f"Payload del webhook incompleto: manca {'.'.join(path)}")
    return value


def _parse_sent_at(raw: object) -> datetime:
    """Legge `sentAt` (ISO 8601, anche con `Z`); se è senza fuso si assume UTC."""
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        raise InvalidInputError("Payload del webhook non valido: message.sentAt illeggibile") from None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def parse_message_received(payload: dict, event_id: str) -> Optional[InboundMessage]:
    """
    Legge il payload di un evento webhook Zernio. Ritorna `None` se l'evento non è `message.received`.
    Solleva `InvalidInputError` se mancano `account.accountId`, `conversation.id`, `message.sender.id`
    o `message.sentAt`. Un `metadata.postbackPayload` rende il messaggio `dm_postback`;
    `metadata.standby` (default `False`) segnala che un'altra app possiede la conversazione.
    `message.sender.instagramProfile.isFollower` vale solo se è un booleano vero: assente, `null` o di un
    altro tipo → `is_follower = None`.
    """
    if payload.get("event") != _MESSAGE_RECEIVED:
        return None
    account_id = _required(payload, "account", "accountId")
    conversation_id = _required(payload, "conversation", "id")
    sender_id = _required(payload, "message", "sender", "id")
    sent_at = _parse_sent_at(_required(payload, "message", "sentAt"))

    message = payload.get("message") or {}
    metadata = payload.get("metadata") or {}
    postback = metadata.get("postbackPayload") or None
    profile = (message.get("sender") or {}).get("instagramProfile")
    is_follower = profile.get("isFollower") if isinstance(profile, dict) else None
    return InboundMessage(
        event_id=event_id,
        source=_SOURCE_POSTBACK if postback else _SOURCE_TEXT,
        account_id=str(account_id),
        conversation_id=str(conversation_id),
        sender_id=str(sender_id),
        direction=message.get("direction") or _DIRECTION_INCOMING,
        text=message.get("text"),
        postback_payload=postback,
        sent_at=sent_at,
        standby=bool(metadata.get("standby", False)),
        is_follower=is_follower if isinstance(is_follower, bool) else None,
    )


def verify_signature(secret: str, raw_body: bytes, signature: Optional[str]) -> bool:
    """
    Verifica `X-Zernio-Signature`: HMAC-SHA256 esadecimale del corpo grezzo con il secret del negozio.
    Il confronto è in tempo costante. Firma assente o vuota → `False`.
    """
    if not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode("ascii"), signature.strip().lower().encode("utf-8"))


def normalize_text(text: Optional[str]) -> str:
    """
    Normalizza il testo di un messaggio per il confronto con la parola chiave: NFKD senza segni
    diacritici, `casefold`, solo lettere, cifre e spazi (punteggiatura ed emoji cadono), spazi compattati.
    `None` → stringa vuota.
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()
    letters = "".join(ch if ch.isalnum() else " " for ch in stripped)
    return re.sub(r"\s+", " ", letters).strip()


class Trigger(str, Enum):
    """Che cosa ha chiesto il cliente."""
    CARD_REQUEST = "card_request"


def detect_trigger(msg: InboundMessage, keyword: str) -> Optional[Trigger]:
    """
    Riconosce la richiesta della carta: postback del menu con il payload fisso, oppure testo uguale
    alla parola chiave dopo la normalizzazione. I messaggi `outgoing` non scatenano mai nulla;
    una parola chiave che normalizzata è vuota non corrisponde a niente.
    """
    if msg.direction != _DIRECTION_INCOMING:
        return None
    if msg.source == _SOURCE_POSTBACK:
        return Trigger.CARD_REQUEST if msg.postback_payload == CARD_POSTBACK_PAYLOAD else None
    wanted = normalize_text(keyword)
    return Trigger.CARD_REQUEST if wanted and normalize_text(msg.text) == wanted else None


class CardMessage(BaseModel):
    """Card (generic template) da inviare: un elemento, un bottone URL."""

    title: str
    subtitle: str
    button_title: str
    button_url: str


def _check_length(field: str, value: str, limit: int) -> None:
    """`MessageTooLongError` se `value` supera `limit`; il messaggio cita campo, limite e lunghezza, mai il valore."""
    if len(value) > limit:
        raise MessageTooLongError(f"Il campo «{field}» è troppo lungo: {len(value)} caratteri, massimo {limit}")


def _check_card_url(card_url: str) -> None:
    """Il link della carta deve essere `https://`. Il messaggio d'errore non riporta l'URL (contiene il token)."""
    if not card_url.startswith("https://"):
        raise InvalidInputError("Il link della carta deve iniziare con https://")


def build_card_message(business_name: str, card_url: str) -> CardMessage:
    """
    Costruisce la card: titolo = nome del negozio, sottotitolo e bottone fissi, link invariato.
    Solleva `InvalidInputError` per nome vuoto o URL non https, `MessageTooLongError` se un campo
    supera il limite (titolo/sottotitolo 80, bottone 20).
    """
    title = (business_name or "").strip()
    if not title:
        raise InvalidInputError("Il nome del negozio è obbligatorio")
    _check_card_url(card_url)
    _check_length("title", title, CARD_TITLE_MAX)
    _check_length("subtitle", CARD_SUBTITLE, CARD_SUBTITLE_MAX)
    _check_length("button_title", CARD_BUTTON_TITLE, CARD_BUTTON_TITLE_MAX)
    return CardMessage(
        title=title, subtitle=CARD_SUBTITLE, button_title=CARD_BUTTON_TITLE, button_url=card_url,
    )


def build_fallback_text(business_name: str, card_url: str) -> str:
    """
    Testo fisso di ripiego `"La tua carta fedeltà di <negozio>: <link>"`, usato solo se Meta rifiuta la
    card. Stessi controlli di `build_card_message`; limite complessivo di 640 caratteri.
    """
    name = (business_name or "").strip()
    if not name:
        raise InvalidInputError("Il nome del negozio è obbligatorio")
    _check_card_url(card_url)
    text = f"La tua carta fedeltà di {name}: {card_url}"
    _check_length("text", text, FALLBACK_TEXT_MAX)
    return text


def build_follow_prompt_text(business_name: str, instagram_username: Optional[str], keyword: str) -> str:
    """
    Testo fisso di invito per chi non segue il negozio (nessuna carta, nessun link):
    `"Per avere la carta fedeltà di <negozio> segui @<handle> su Instagram, poi riscrivi <PAROLA>."`.
    Senza handle (vuoto, solo spazi o solo `@`) si cita il nome del negozio. `keyword` è la parola chiave
    di piattaforma: il core non legge le settings, la passa la shell. Solleva `InvalidInputError` per nome
    vuoto e `MessageTooLongError` oltre i 640 caratteri.
    """
    name = (business_name or "").strip()
    if not name:
        raise InvalidInputError("Il nome del negozio è obbligatorio")
    handle = (instagram_username or "").strip().lstrip("@").strip()
    target = f"@{handle} su Instagram" if handle else f"il profilo Instagram di {name}"
    text = f"Per avere la carta fedeltà di {name} segui {target}, poi riscrivi {keyword}."
    _check_length("text", text, FALLBACK_TEXT_MAX)
    return text


def can_reply(last_inbound_at: datetime, now: datetime) -> bool:
    """`True` solo se dal messaggio del cliente sono passate meno di 24 ore (24 h esatte → `False`)."""
    return now - last_inbound_at < REPLY_WINDOW


class QuotaStatus(BaseModel):
    """Stato della quota mensile di invii Zernio, per pannello e log."""

    sent: int
    limit: int
    percent: int  # arrotondato per difetto; 0 se il limite non è positivo
    warning: bool  # raggiunta la soglia di avviso
    exhausted: bool  # raggiunto il limite


def quota_status(sent: int, limit: int, warn_percent: int) -> QuotaStatus:
    """
    Stato della quota: `warning` se `sent` ≥ `warn_percent`% di `limit`, `exhausted` se `sent` ≥ `limit`.
    Con `limit` ≤ 0 non si divide: percentuale 0 e nessuno stato (la quota non è configurata).
    Non blocca nulla: oltre il limite è Zernio a fermare gli invii.
    """
    if limit <= 0:
        return QuotaStatus(sent=sent, limit=limit, percent=0, warning=False, exhausted=False)
    return QuotaStatus(
        sent=sent,
        limit=limit,
        percent=sent * 100 // limit,
        warning=sent * 100 >= warn_percent * limit,
        exhausted=sent >= limit,
    )


# --- Shell ---
#
# Gli import della shell stanno qui, come in `customer_service`: `zernio_service` importa `CardMessage`
# dal core di questo modulo, quindi il core deve essere già definito quando lo si importa.

import json  # noqa: E402
import logging  # noqa: E402

import httpx  # noqa: E402
from sqlalchemy import delete, update  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.core import crypto  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.enums import InstagramStatus, WebhookOutcome  # noqa: E402
from app.core.errors import InvalidSignatureError, NotFoundError  # noqa: E402
from app.models.models import Card, Merchant, ProcessedWebhookEvent, ZernioSendCounter  # noqa: E402
from app.services import zernio_service  # noqa: E402
from app.services.db_crud import card_crud, merchant_crud  # noqa: E402

logger = logging.getLogger(__name__)

EVENT_RETENTION = timedelta(days=7)  # i retry di Zernio durano ~51 h: 7 giorni bastano per la dedup


def get_or_create_card(session: Session, merchant: Merchant, igsid: str) -> tuple[Card, bool]:
    """
    Carta del cliente (identificato dall'IGSID) presso il negozio; la crea al primo messaggio. Ritorna
    `(carta, creata)`. Si cerca per `(merchant_id, indice cieco dell'IGSID)`: l'IGSID non si salva. Alla
    creazione si salva anche l'hash del token del link (il token si ricalcola, non si salva). Richieste
    simultanee non producono doppioni: si riusa la carta creata dall'altra (come `join_merchant`).
    """
    igsid_hash = crypto.igsid_blind_index(igsid)
    card = card_crud.get_card_by_igsid_hash(session, merchant.id, igsid_hash)
    if card:
        return card, False

    new_card = Card(merchant_id=merchant.id, igsid_hash=igsid_hash)
    new_card.link_token_hash = crypto.token_hash(crypto.card_link_token(new_card.id, new_card.link_version))
    try:
        return card_crud.add_card(session, new_card), True
    except IntegrityError:
        # un'altra richiesta ha creato la stessa carta nel frattempo: si riusa quella
        session.rollback()
        card = card_crud.get_card_by_igsid_hash(session, merchant.id, igsid_hash)
        if card is None:
            raise
        return card, False


def card_link_url(card: Card) -> str:
    """Link segreto della carta: `<PUBLIC_BASE_URL>/c/<token>`, con il token ricalcolato da id e versione."""
    token = crypto.card_link_token(card.id, card.link_version)
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/c/{token}"


def _mark_standby(session: Session, merchant: Merchant, now: datetime) -> None:
    """Registra che un'altra app possiede la conversazione (avviso nel pannello del merchant)."""
    merchant.standby_detected_at = now
    session.add(merchant)
    session.commit()


def _increment_send_counter(session: Session, quota_scope: str, period: str) -> int:
    """
    Conta un invio riuscito nel mese: crea la riga se manca, poi UPDATE atomico (come `_increment_pool`).
    Ritorna il nuovo totale. La riga si crea in una transazione propria: se un'altra richiesta l'ha
    creata nel frattempo basta ignorare il conflitto.
    """
    if session.get(ZernioSendCounter, (quota_scope, period)) is None:
        try:
            session.add(ZernioSendCounter(quota_scope=quota_scope, period=period, sent=0))
            session.commit()
        except IntegrityError:
            session.rollback()
    session.execute(
        update(ZernioSendCounter)
        .where(ZernioSendCounter.quota_scope == quota_scope, ZernioSendCounter.period == period)
        .values(sent=ZernioSendCounter.sent + 1)
    )
    session.commit()
    return session.exec(
        select(ZernioSendCounter.sent).where(
            ZernioSendCounter.quota_scope == quota_scope, ZernioSendCounter.period == period,
        )
    ).one()


def _record_send(
    session: Session, merchant: Merchant, creds: "zernio_service.ZernioCredentials", now: datetime,
) -> None:
    """
    Bookkeeping di un invio riuscito (card, ripiego o invito a seguire): contatore del mese per l'ambito di
    quota, avviso nel log al superamento della soglia (nessun blocco nostro: oltre il limite è Zernio a
    fermare gli invii) e `AWAITING_TEST_DM` → `ACTIVE`.
    """
    period = now.astimezone(timezone.utc).strftime("%Y-%m")
    sent = _increment_send_counter(session, creds.quota_scope, period)
    limit, warn = settings.ZERNIO_MONTHLY_SEND_LIMIT, settings.ZERNIO_SEND_WARN_PERCENT
    status = quota_status(sent, limit, warn)
    if status.warning and not quota_status(sent - 1, limit, warn).warning:
        logger.warning("Quota Zernio: il negozio %s ha raggiunto il %s%% degli invii mensili", merchant.id, status.percent)
    if merchant.instagram_status == InstagramStatus.AWAITING_TEST_DM:
        merchant.instagram_status = InstagramStatus.ACTIVE
        session.add(merchant)
        session.commit()


def _handle_send_error(
    session: Session, merchant: Merchant, error: "zernio_service.ZernioError", event_id: str, now: datetime,
) -> WebhookOutcome:
    """
    Esito di un invio fallito, uguale per card, ripiego e invito: chiave rifiutata → `KEY_INVALID`
    (pannello del merchant) e `SEND_FAILED`; conversazione di un'altra app → come lo standby; ogni altro
    errore → `SEND_FAILED`. Nessun nuovo tentativo. Si logga solo tipo dell'errore, negozio ed evento.
    """
    logger.warning("Webhook: invio non riuscito (%s) negozio=%s evento=%s", error.kind.value, merchant.id, event_id)
    if error.kind == zernio_service.ZernioErrorKind.AUTH:
        merchant.instagram_status = InstagramStatus.KEY_INVALID
        session.add(merchant)
        session.commit()
        return WebhookOutcome.SEND_FAILED
    if error.kind == zernio_service.ZernioErrorKind.NOT_THREAD_OWNER:
        _mark_standby(session, merchant, now)
        return WebhookOutcome.STANDBY
    return WebhookOutcome.SEND_FAILED


async def _send_fallback_text(
    session: Session, http: httpx.AsyncClient, merchant: Merchant, creds: "zernio_service.ZernioCredentials",
    msg: InboundMessage, card_url: str, now: datetime,
) -> WebhookOutcome:
    """Meta ha rifiutato la card: testo fisso con il link (`<evento>:text` come chiave di idempotenza)."""
    try:
        text = build_fallback_text(merchant.business_name, card_url)
    except InvalidInputError:
        logger.warning("Webhook: testo di ripiego non costruibile negozio=%s evento=%s", merchant.id, msg.event_id)
        return WebhookOutcome.SEND_FAILED
    try:
        await zernio_service.send_text(http, creds, msg.conversation_id, text, f"{msg.event_id}:text")
    except zernio_service.ZernioError as error:
        return _handle_send_error(session, merchant, error, msg.event_id, now)
    _record_send(session, merchant, creds, now)
    return WebhookOutcome.FALLBACK_SENT


async def _invite_to_follow(
    session: Session, http: httpx.AsyncClient, merchant: Merchant, creds: "zernio_service.ZernioCredentials",
    msg: InboundMessage, now: datetime,
) -> WebhookOutcome:
    """
    Chi non segue il negozio non ha la carta (decisione 2026-10-23): niente riga `Card`, solo un testo fisso
    di invito a seguire il profilo e a riscrivere la parola chiave. Vale anche qui la finestra di 24 ore.
    """
    if not can_reply(msg.sent_at, now):
        return WebhookOutcome.OUT_OF_WINDOW
    try:
        text = build_follow_prompt_text(
            merchant.business_name, merchant.instagram_username, settings.INSTAGRAM_CARD_KEYWORD,
        )
    except InvalidInputError:
        logger.warning("Webhook: invito a seguire non costruibile negozio=%s evento=%s", merchant.id, msg.event_id)
        return WebhookOutcome.SEND_FAILED
    try:
        await zernio_service.send_text(http, creds, msg.conversation_id, text, f"{msg.event_id}:follow")
    except zernio_service.ZernioError as error:
        return _handle_send_error(session, merchant, error, msg.event_id, now)
    _record_send(session, merchant, creds, now)
    return WebhookOutcome.FOLLOW_REQUESTED


async def _reply_with_card(
    session: Session, http: httpx.AsyncClient, merchant: Merchant, creds: "zernio_service.ZernioCredentials",
    msg: InboundMessage, now: datetime,
) -> WebhookOutcome:
    """
    Crea o ritrova la carta, aggiorna conversazione e `last_inbound_at` e risponde con la card; se Meta la
    rifiuta a un non follower (2/1545133) ripiega sul testo con il link. Fuori dalle 24 ore la carta si
    aggiorna ma non si invia nulla.
    """
    card, _ = get_or_create_card(session, merchant, msg.sender_id)
    card.zernio_conversation_id = msg.conversation_id
    card.last_inbound_at = msg.sent_at
    session.add(card)
    session.commit()
    if not can_reply(msg.sent_at, now):
        return WebhookOutcome.OUT_OF_WINDOW

    card_url = card_link_url(card)
    try:
        card_message = build_card_message(merchant.business_name, card_url)
    except InvalidInputError:
        # es. PUBLIC_BASE_URL non https o nome del negozio oltre 80 caratteri: il messaggio non cita né link né nome
        logger.warning("Webhook: card non costruibile negozio=%s evento=%s", merchant.id, msg.event_id)
        return WebhookOutcome.SEND_FAILED
    try:
        await zernio_service.send_card(http, creds, msg.conversation_id, card_message, msg.event_id)
    except zernio_service.ZernioError as error:
        if error.kind == zernio_service.ZernioErrorKind.NOT_FOLLOWER:
            return await _send_fallback_text(session, http, merchant, creds, msg, card_url, now)
        return _handle_send_error(session, merchant, error, msg.event_id, now)
    _record_send(session, merchant, creds, now)
    return WebhookOutcome.SENT


async def _process_message(
    session: Session, http: httpx.AsyncClient, merchant: Merchant, creds: "zernio_service.ZernioCredentials",
    payload: dict, event_id: str, now: datetime,
) -> WebhookOutcome:
    """Dal payload già verificato e registrato all'esito (passi 6-16 di `handle_webhook`)."""
    try:
        msg = parse_message_received(payload, event_id)
    except InvalidInputError:
        logger.warning("Webhook: payload incompleto negozio=%s evento=%s", merchant.id, event_id)
        return WebhookOutcome.IGNORED
    if msg is None or msg.account_id != merchant.zernio_account_id or msg.direction != _DIRECTION_INCOMING:
        return WebhookOutcome.IGNORED
    if msg.standby:
        _mark_standby(session, merchant, now)
        return WebhookOutcome.STANDBY
    if detect_trigger(msg, settings.INSTAGRAM_CARD_KEYWORD) is None:
        return WebhookOutcome.IGNORED
    if msg.is_follower is False:  # `None` (dato non disponibile) → card: da rivedere nel collaudo finale
        return await _invite_to_follow(session, http, merchant, creds, msg, now)
    return await _reply_with_card(session, http, merchant, creds, msg, now)


async def handle_webhook(
    session: Session,
    http: httpx.AsyncClient,
    hook_id: str,
    raw_body: bytes,
    signature: Optional[str],
    event_id: Optional[str],
    now: datetime,
) -> WebhookOutcome:
    """
    Elabora un webhook Zernio `message.received` in modo sincrono e idempotente; ritorna l'esito (la route
    risponde 200 per ogni esito). Ordine: negozio dal `hook_id` → firma con il secret del negozio → JSON →
    riga dell'evento inserita **per prima** (un duplicato esce subito) → pulizia degli eventi oltre 7 giorni
    → messaggio, standby, trigger, `isFollower`, carta, invio. Se manca l'header `X-Zernio-Event-Id` si usa
    `payload.id`; senza nessuno dei due l'evento non si elabora.
    Solleva `NotFoundError` (`hook_id` sconosciuto o negozio senza chiave/account) e `InvalidSignatureError`
    (firma assente o errata, o secret mancante). Una riga rimasta `RECEIVED` indica un'elaborazione
    interrotta: il retry di Zernio non la ripete, per non rischiare un doppio invio.
    I log contengono solo id del negozio, id dell'evento ed esito: mai IGSID, token, link, chiavi o testo.
    """
    merchant = merchant_crud.get_merchant_by_webhook_hook_id(session, hook_id) if hook_id else None
    if merchant is None:
        raise NotFoundError("Webhook non trovato")
    merchant_id = merchant.id
    try:
        creds = zernio_service.zernio_credentials_for(merchant)
    except zernio_service.ZernioError:
        raise NotFoundError("Webhook non trovato") from None
    if creds.webhook_secret is None or not verify_signature(creds.webhook_secret.get_secret_value(), raw_body, signature):
        raise InvalidSignatureError("Firma del webhook non valida")

    try:
        payload = json.loads(raw_body)
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        logger.warning("Webhook: corpo non valido negozio=%s", merchant_id)
        return WebhookOutcome.IGNORED
    event_id = (event_id or "").strip() or str(payload.get("id") or "").strip()
    if not event_id:
        logger.warning("Webhook: evento senza id negozio=%s", merchant_id)
        return WebhookOutcome.IGNORED

    session.add(ProcessedWebhookEvent(
        event_id=event_id, merchant_id=merchant_id, received_at=now, outcome=WebhookOutcome.RECEIVED,
    ))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        logger.info("Webhook: evento già visto negozio=%s evento=%s", merchant_id, event_id)
        return WebhookOutcome.IGNORED
    session.execute(delete(ProcessedWebhookEvent).where(ProcessedWebhookEvent.received_at < now - EVENT_RETENTION))
    session.commit()

    outcome = await _process_message(session, http, merchant, creds, payload, event_id, now)

    event = session.get(ProcessedWebhookEvent, event_id)
    if event is not None:
        event.outcome = outcome
        session.add(event)
        session.commit()
    logger.info("Webhook: negozio=%s evento=%s esito=%s", merchant_id, event_id, outcome.value)
    return outcome
