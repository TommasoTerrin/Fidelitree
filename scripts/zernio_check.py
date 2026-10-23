"""
Chiamate reali a Zernio per il collaudo manuale: elenco account, conversazioni, invio della card e del testo
di ripiego. Non tocca il DB. La chiave arriva da `ZERNIO_CHECK_API_KEY` oppure da una richiesta a video
(mai da argomento della riga di comando: finirebbe nella history) e si mostra solo mascherata (`…1234`).

Utilizzo (dalla root del progetto):
    python -m scripts.zernio_check accounts
    python -m scripts.zernio_check conversations --account-id ACC [--folder requests]
    python -m scripts.zernio_check send-card --account-id ACC --conversation-id CONV [--name "Bar"] [--url https://...]
    python -m scripts.zernio_check send-text --account-id ACC --conversation-id CONV [--name "Bar"] [--url https://...]

`conversations` stampa solo id e data della conversazione: niente IGSID né username dei clienti.
Codici di uscita: 0 ok, 1 errore (chiave mancante, Zernio, dati non validi).
"""

import argparse
import asyncio
import getpass
import logging
import os
import sys
import uuid
from typing import Optional

from app.core.config import settings
from app.core.crypto import mask_secret
from app.core.errors import DomainError
from app.services import instagram_service, zernio_service
from app.services.zernio_service import ZernioError

KEY_ENV = "ZERNIO_CHECK_API_KEY"
DEFAULT_NAME = "Negozio di prova"
DEFAULT_URL = "https://example.com/c/prova"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.zernio_check",
        description=(
            "Chiamate reali a Zernio. La chiave si legge da ZERNIO_CHECK_API_KEY o si chiede a video."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("accounts", help="elenca gli account Instagram collegati (id, @username)")

    conversations = commands.add_parser("conversations", help="elenca le conversazioni (solo id e data)")
    conversations.add_argument("--account-id", required=True)
    conversations.add_argument("--folder", choices=["inbox", "requests"], help="cartella (default: Generale)")

    for name, help_text in (("send-card", "invia la card"), ("send-text", "invia il testo di ripiego")):
        send = commands.add_parser(name, help=help_text)
        send.add_argument("--account-id", required=True)
        send.add_argument("--conversation-id", required=True)
        send.add_argument("--name", default=DEFAULT_NAME, help=f"nome del negozio (default: {DEFAULT_NAME})")
        send.add_argument("--url", default=DEFAULT_URL, help=f"link della carta, https (default: {DEFAULT_URL})")
    return parser


def _read_key() -> str:
    """Chiave da env o da `getpass` (non si vede a video); stringa vuota se non fornita."""
    return (os.environ.get(KEY_ENV) or "").strip() or getpass.getpass("Chiave Zernio: ").strip()


async def _run(args: argparse.Namespace, key: str) -> None:
    """Esegue il comando con un client reale; solleva `ZernioError` o `DomainError`."""
    account_id = getattr(args, "account_id", None)
    creds = zernio_service.credentials_from_key(key, account_id)
    async with zernio_service.make_http_client(zernio_service.CONFIG_TIMEOUT) as http:
        if args.command == "accounts":
            accounts = await zernio_service.list_instagram_accounts(http, creds)
            for account in accounts:
                print(f"{account.id}  @{account.username or '?'}")
            print(f"{len(accounts)} account Instagram collegati")
        elif args.command == "conversations":
            conversations = await zernio_service.list_conversations(http, creds, folder=args.folder)
            for conversation in conversations:
                print(f"{conversation.get('id')}  {conversation.get('updatedTime') or '-'}")
            print(f"{len(conversations)} conversazioni")
        elif args.command == "send-card":
            card = instagram_service.build_card_message(args.name, args.url)
            message_id = await zernio_service.send_card(
                http, creds, args.conversation_id, card, str(uuid.uuid4()),
            )
            print(f"Card inviata (messageId: {message_id or '(assente)'})")
        else:  # send-text
            text = instagram_service.build_fallback_text(args.name, args.url)
            message_id = await zernio_service.send_text(
                http, creds, args.conversation_id, text, str(uuid.uuid4()),
            )
            print(f"Testo inviato (messageId: {message_id or '(assente)'})")


def main(argv: Optional[list[str]] = None) -> int:
    """Esegue il comando e ritorna il codice di uscita."""
    args = _build_parser().parse_args(argv)
    key = _read_key()
    if not key:
        print(f"ERRORE: chiave Zernio mancante (imposta {KEY_ENV} o digitala a richiesta)", file=sys.stderr)
        return 1

    print(f"Chiave Zernio {mask_secret(key)}")
    print(f"URL: {settings.ZERNIO_BASE_URL.rstrip('/')}")
    try:
        asyncio.run(_run(args, key))
    except ZernioError as e:
        status = f", HTTP {e.status}" if e.status else ""
        print(f"ERRORE [{e.kind.value}{status}]: {e}", file=sys.stderr)
        return 1
    except DomainError as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
