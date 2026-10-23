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
- **Finestra**: si risponde solo entro 24 ore dal messaggio del cliente (`sentAt`, non l'ora di consegna
  del webhook). Nessun invio proattivo.
- **Quota**: Zernio regala 10.000 invii al mese per team; noi li contiamo e avvisiamo, non blocchiamo.
- **Testo dei clienti**: mai salvato; qui lo si legge solo per riconoscere il trigger.

Il core usa solo Pydantic e stdlib: il tempo si passa come argomento, niente DB né rete. Fonti dei limiti
e del formato dei payload: `.agents/architecture/zernio-notes.md`.
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
