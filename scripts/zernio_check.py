"""
Chiamate reali a Zernio per il collaudo manuale: elenco account, conversazioni, invio della card e del testo
di ripiego. La chiave arriva da `ZERNIO_CHECK_API_KEY` (campo opzionale di `Settings`: la legge pydantic-settings
dall'ambiente o dal `.env`, quindi basta scriverla nel `.env`) oppure da una richiesta a video (mai da argomento
della riga di comando: finirebbe nella history), oppure è quella salvata di un negozio (`--merchant-id`). Si mostra
solo mascherata (`…1234`).

Utilizzo (dalla root del progetto):
    python -m scripts.zernio_check accounts [--merchant-id N]
    python -m scripts.zernio_check conversations [--account-id ACC | --merchant-id N] [--folder requests]
    python -m scripts.zernio_check send-card [--account-id ACC | --merchant-id N] --conversation-id CONV [--name "Bar"] [--url https://...]
    python -m scripts.zernio_check send-text [--account-id ACC | --merchant-id N] --conversation-id CONV [--name "Bar"] [--url https://...]

Senza `--merchant-id` non si tocca il DB e `--account-id` è obbligatorio (tranne per `accounts`). Con
`--merchant-id` le credenziali si leggono dal DB del `.env` solo tramite `zernio_credentials_for`, l'account è
quello del negozio (`--account-id` lo sostituisce) e prima del comando si stampa lo stato del negozio: stato
Instagram, `@username`, chiave mascherata e invii del mese. Lo script non scrive mai sul DB.
`conversations` stampa solo id e data della conversazione: niente IGSID né username dei clienti.
Codici di uscita: 0 ok, 1 errore (chiave mancante, negozio non trovato o senza chiave, Zernio, dati non validi).
"""

import argparse
import asyncio
import getpass
import logging
import sys
import uuid
from typing import Optional

from sqlmodel import Session

from app.core.clock import utc_now
from app.core.config import settings
from app.core.crypto import mask_secret
from app.core.errors import DomainError
from app.models.models import Merchant
from app.services import instagram_service, merchant_service, zernio_service
from app.services.zernio_service import ZernioCredentials, ZernioError

KEY_ENV = "ZERNIO_CHECK_API_KEY"
DEFAULT_NAME = "Negozio di prova"
DEFAULT_URL = "https://example.com/c/prova"


def _build_parser() -> argparse.ArgumentParser:
    """Parser dei comandi; `--merchant-id` e `--account-id` sono opzionali su ogni comando (si controllano dopo)."""
    parser = argparse.ArgumentParser(
        prog="python -m scripts.zernio_check",
        description=(
            "Chiamate reali a Zernio. La chiave si legge da ZERNIO_CHECK_API_KEY, si chiede a video "
            "o è quella salvata di un negozio (--merchant-id)."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    def add_target(command: argparse.ArgumentParser) -> None:
        command.add_argument("--merchant-id", type=int, help="usa la chiave e l'account salvati di questo negozio (DB del .env)")
        command.add_argument("--account-id", help="account Instagram (obbligatorio senza --merchant-id)")

    add_target(commands.add_parser("accounts", help="elenca gli account Instagram collegati (id, @username)"))

    conversations = commands.add_parser("conversations", help="elenca le conversazioni (solo id e data)")
    add_target(conversations)
    conversations.add_argument("--folder", choices=["inbox", "requests"], help="cartella (default: Generale)")

    for name, help_text in (("send-card", "invia la card"), ("send-text", "invia il testo di ripiego")):
        send = commands.add_parser(name, help=help_text)
        add_target(send)
        send.add_argument("--conversation-id", required=True)
        send.add_argument("--name", default=DEFAULT_NAME, help=f"nome del negozio (default: {DEFAULT_NAME})")
        send.add_argument("--url", default=DEFAULT_URL, help=f"link della carta, https (default: {DEFAULT_URL})")
    return parser


def _read_key() -> str:
    """
    Chiave da `settings.ZERNIO_CHECK_API_KEY` (ambiente o `.env`, letta a ogni chiamata) o da `getpass` (non si
    vede a video); stringa vuota se non fornita. Il valore non si stampa mai: solo `mask_secret` più avanti.
    """
    return settings.ZERNIO_CHECK_API_KEY.get_secret_value().strip() or getpass.getpass("Chiave Zernio: ").strip()


def _print_merchant_status(session: Session, merchant: Merchant) -> None:
    """
    Stampa lo stato Instagram del negozio ricavato da `read_instagram_panel` (nessuna chiamata a Zernio, nessun
    segreto: chiave mascherata). Il nome del negozio non si stampa: potrebbe contenere emoji che la console
    Windows non rappresenta.
    """
    panel = merchant_service.read_instagram_panel(session, merchant, utc_now())
    print(f"Negozio id {merchant.id}")
    print(f"Stato Instagram: {panel.status.value}")
    print(f"Account: {'@' + panel.username if panel.username else '(non collegato)'}")
    print(f"Chiave Zernio: {panel.key_masked or '(nessuna)'}")
    print(f"Invii del mese: {panel.quota.sent if panel.quota else 0}")


def _merchant_credentials(args: argparse.Namespace, session: Session) -> ZernioCredentials:
    """
    Stampa lo stato del negozio `--merchant-id` e ne ritorna le credenziali (`zernio_credentials_for`: unico
    lettore della chiave cifrata). Per `accounts` basta la chiave; per gli altri comandi serve anche l'account
    (o `--account-id`). Solleva `DomainError` se il negozio non esiste o non ha una chiave salvata.
    """
    merchant = session.get(Merchant, args.merchant_id)
    if merchant is None:
        raise DomainError(f"Merchant {args.merchant_id} non trovato")
    _print_merchant_status(session, merchant)
    try:
        creds = zernio_service.zernio_credentials_for(merchant, require_account=False)
    except ZernioError as error:
        if error.kind != zernio_service.ZernioErrorKind.NOT_CONFIGURED:
            raise
        raise DomainError(
            "Il negozio non ha una chiave Zernio utilizzabile (non salvata o illeggibile): "
            "collega Instagram dalle impostazioni"
        ) from None
    if args.account_id:
        creds = creds.model_copy(update={"account_id": args.account_id})
    return creds


def _credentials(args: argparse.Namespace, session: Optional[Session]) -> ZernioCredentials:
    """
    Credenziali per il comando: quelle del negozio con `--merchant-id` (apre una sessione sul DB del `.env`
    se non ne è stata passata una), altrimenti la chiave da env o a video. Stampa la chiave mascherata.
    Solleva `DomainError` se manca la chiave o, per i comandi che lo richiedono, l'account.
    """
    if args.merchant_id is not None:
        if session is not None:
            creds = _merchant_credentials(args, session)
        else:
            from app.main import engine  # import tardivo: senza --merchant-id il DB non si apre
            with Session(engine) as own_session:
                creds = _merchant_credentials(args, own_session)
    else:
        if args.command != "accounts" and not args.account_id:  # prima di chiedere una chiave che non servirebbe
            raise DomainError("manca l'account: passa --account-id (o --merchant-id di un negozio collegato)")
        key = _read_key()
        if not key:
            raise DomainError(f"chiave Zernio mancante (imposta {KEY_ENV} o digitala a richiesta)")
        print(f"Chiave Zernio {mask_secret(key)}")
        creds = zernio_service.credentials_from_key(key, args.account_id)

    if args.command != "accounts" and not creds.account_id:
        raise DomainError("manca l'account: passa --account-id (o --merchant-id di un negozio collegato)")
    return creds


async def _run(args: argparse.Namespace, creds: ZernioCredentials) -> None:
    """Esegue il comando con un client reale; solleva `ZernioError` o `DomainError`."""
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


def main(argv: Optional[list[str]] = None, session: Optional[Session] = None) -> int:
    """
    Esegue il comando e ritorna il codice di uscita. `session` si inietta nei test (serve solo con
    `--merchant-id`); senza, per `--merchant-id` si apre una sessione sul DB del `.env`.
    """
    args = _build_parser().parse_args(argv)
    try:
        creds = _credentials(args, session)
        print(f"URL: {settings.ZERNIO_BASE_URL.rstrip('/')}")
        asyncio.run(_run(args, creds))
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
