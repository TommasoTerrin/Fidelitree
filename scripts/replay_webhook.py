"""
Collaudo locale del webhook: costruisce un evento `message.received` realistico, lo firma con il secret del
negozio (dal DB del `.env`, via `zernio_credentials_for`) e lo invia al server in esecuzione.

ATTENZIONE: il server proverà un invio VERO a Zernio sulla conversazione indicata (`--conversation-id`).
Lo script non parla mai con Zernio: manda solo il webhook al nostro server.

Utilizzo (dalla root del progetto, con il server avviato):
    python -m scripts.replay_webhook --merchant-id N --conversation-id ID
        [--text CARTA | --postback | --comment TESTO] [--sender-id finto-igsid] [--standby] [--follower si|no]
        [--post-id ID] [--comment-id ID] [--hours-ago H] [--event-id ID] [--url http://127.0.0.1:8001]

`--comment TESTO` manda invece un evento `comment.received` firmato (esclude `--text` e `--postback`): in quel caso
`--conversation-id` non serve, e `--post-id` / `--comment-id` (valori finti di default) indicano il post e il
commento a cui il server risponderà in privato. `--conversation-id` resta obbligatorio per i DM.

`--follower` imposta `instagramProfile.isFollower` (se omesso il campo manca: il server lo tratta come
"dato non disponibile"). `--event-id` fissa l'id dell'evento (`X-Zernio-Event-Id`): lanciato due volte con lo
stesso valore simula un retry di Zernio e il server deve fare un solo invio (default: un UUID nuovo a ogni
esecuzione). Stampa status HTTP ed esito letto dalla riga dell'evento nel DB; non stampa mai
secret, id della conversazione né id del webhook. Codici di uscita: 0 ok, 1 errore.
"""

import argparse
import hashlib
import hmac
import json
import sys
import uuid
from datetime import timedelta
from typing import Optional

import httpx
from sqlmodel import Session

from app.core.clock import utc_now
from app.core.config import settings
from app.core.errors import DomainError
from app.models.models import Merchant, ProcessedWebhookEvent
from app.services import instagram_service, zernio_service
from app.services.zernio_service import ZernioError

DEFAULT_SENDER_ID = "finto-igsid"
DEFAULT_POST_ID = "finto-post-id"
DEFAULT_COMMENT_ID = "finto-comment-id"
REQUEST_TIMEOUT = 15.0  # secondi: il server può impiegare fino a ~4 s per invio verso Zernio


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.replay_webhook",
        description=(
            "Invia al server un evento message.received firmato. Il server farà un invio VERO a Zernio "
            "sulla conversazione indicata."
        ),
    )
    parser.add_argument("--merchant-id", type=int, required=True)
    parser.add_argument(
        "--conversation-id",
        help="conversation.id di Zernio dove il server risponderà (obbligatorio per i DM, non con --comment)",
    )
    kind = parser.add_mutually_exclusive_group()
    kind.add_argument("--text", help=f"testo del messaggio (default: {settings.INSTAGRAM_CARD_KEYWORD})")
    kind.add_argument("--postback", action="store_true", help="simula il tocco sulla voce di menu 'La mia carta'")
    kind.add_argument("--comment", help="invia un evento comment.received con questo testo di commento")
    parser.add_argument("--post-id", default=DEFAULT_POST_ID, help=f"platformPostId finto (default: {DEFAULT_POST_ID})")
    parser.add_argument(
        "--comment-id", default=DEFAULT_COMMENT_ID, help=f"id finto del commento (default: {DEFAULT_COMMENT_ID})",
    )
    parser.add_argument("--sender-id", default=DEFAULT_SENDER_ID, help=f"IGSID finto (default: {DEFAULT_SENDER_ID})")
    parser.add_argument("--standby", action="store_true", help="metadata.standby = true (un'altra app possiede la chat)")
    parser.add_argument("--follower", choices=["si", "no"], help="instagramProfile.isFollower (default: assente)")
    parser.add_argument("--hours-ago", type=float, default=0.0, help="sentAt = adesso meno H ore (default: 0)")
    parser.add_argument(
        "--event-id", help="id dell'evento: riusarlo simula un retry di Zernio (default: un UUID nuovo a ogni esecuzione)",
    )
    parser.add_argument(
        "--url", default=f"http://{settings.APP_HOST}:{settings.APP_PORT}",
        help="base URL del server (default: da APP_HOST e APP_PORT)",
    )
    return parser


def build_payload(args: argparse.Namespace, account_id: str, event_id: str) -> dict:
    """
    Payload `message.received` nel formato di `zernio-notes.md`, con i valori scelti dalla riga di comando.
    Con `--comment` ritorna invece un `comment.received` (contract v0.4.1 §9 e §11): `account.accountId` del
    negozio, `comment.id`, `comment.platformPostId` e `comment.text`, cioè i soli campi letti dal parser.
    """
    if args.comment is not None:
        return {
            "id": event_id,
            "event": "comment.received",
            "account": {"accountId": account_id},
            "comment": {"id": args.comment_id, "platformPostId": args.post_id, "text": args.comment},
        }
    sent_at = (utc_now() - timedelta(hours=args.hours_ago)).isoformat().replace("+00:00", "Z")
    sender: dict = {"id": args.sender_id, "name": "Cliente di prova", "username": "cliente_prova"}
    if args.follower:
        sender["instagramProfile"] = {"isFollower": args.follower == "si"}
    metadata: dict = {}
    if args.postback:
        metadata["postbackPayload"] = instagram_service.CARD_POSTBACK_PAYLOAD
    if args.standby:
        metadata["standby"] = True
    return {
        "id": event_id,
        "event": "message.received",
        "message": {
            "id": f"replay-{event_id}",
            "conversationId": args.conversation_id,
            "platform": "instagram",
            "direction": "incoming",
            "text": None if args.postback else (args.text or settings.INSTAGRAM_CARD_KEYWORD),
            "attachments": [],
            "sender": sender,
            "sentAt": sent_at,
        },
        "conversation": {"id": args.conversation_id, "platformConversationId": args.sender_id, "status": "active"},
        "account": {"id": account_id, "accountId": account_id, "platform": "instagram"},
        "metadata": metadata,
        "timestamp": sent_at,
        "test": False,
    }


def _run(args: argparse.Namespace, session: Session, http: httpx.Client) -> int:
    """Costruisce, firma e invia l'evento; stampa status ed esito. Solleva `ZernioError`/`DomainError`."""
    merchant = session.get(Merchant, args.merchant_id)
    if merchant is None:
        raise DomainError(f"Merchant {args.merchant_id} non trovato")
    if not merchant.webhook_hook_id:
        raise DomainError("Il negozio non ha un webhook configurato (manca webhook_hook_id)")
    creds = zernio_service.zernio_credentials_for(merchant)
    if creds.webhook_secret is None or not creds.account_id:
        raise DomainError("Il negozio non ha il secret del webhook o l'account Zernio")

    event_id = args.event_id or str(uuid.uuid4())
    raw = json.dumps(build_payload(args, creds.account_id, event_id)).encode("utf-8")
    signature = hmac.new(creds.webhook_secret.get_secret_value().encode("utf-8"), raw, hashlib.sha256).hexdigest()
    url = f"{args.url.rstrip('/')}/webhooks/zernio/{merchant.webhook_hook_id}"

    print(f"Negozio id {merchant.id}")  # niente nome: potrebbe contenere emoji che la console Windows non stampa
    print("ATTENZIONE: il server proverà un invio VERO a Zernio sulla conversazione indicata.")
    response = http.post(url, content=raw, headers={
        "Content-Type": "application/json", "X-Zernio-Signature": signature, "X-Zernio-Event-Id": event_id,
    })
    print(f"HTTP {response.status_code}")
    if not response.is_success:
        return 1

    session.expire_all()
    event = session.get(ProcessedWebhookEvent, event_id)
    if event is None:
        print("esito: (evento non trovato nel DB: il server usa un altro database?)")
    else:
        print(f"esito: {event.outcome.value}")
    return 0


def main(
    argv: Optional[list[str]] = None,
    session: Optional[Session] = None,
    http: Optional[httpx.Client] = None,
) -> int:
    """
    Esegue il comando e ritorna il codice di uscita. `session` e `http` si iniettano nei test; di default
    si apre una sessione sul DB del `.env` (import tardivo dell'app: `--help` non la avvia) e un client httpx.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    # Il DM ha bisogno della conversazione dove rispondere; il commento no (la risposta privata usa post e commento).
    if args.comment is None and not args.conversation_id:
        parser.error("--conversation-id è obbligatorio se non si usa --comment")
    try:
        if session is None:
            from app.main import engine  # import tardivo: evita di avviare l'app per --help
            with Session(engine) as own_session:
                return _run_with_http(args, own_session, http)
        return _run_with_http(args, session, http)
    except ZernioError as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        return 1
    except DomainError as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        return 1
    except httpx.HTTPError as e:
        print(f"ERRORE: server non raggiungibile ({type(e).__name__})", file=sys.stderr)
        return 1


def _run_with_http(args: argparse.Namespace, session: Session, http: Optional[httpx.Client]) -> int:
    """`_run` con il client dato o uno nuovo (chiuso alla fine)."""
    if http is not None:
        return _run(args, session, http)
    with httpx.Client(timeout=REQUEST_TIMEOUT) as own_http:
        return _run(args, session, own_http)


if __name__ == "__main__":
    sys.exit(main())
