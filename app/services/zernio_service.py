"""
Client dell'API Zernio (https://docs.zernio.com) per la carta fedeltà via DM Instagram.

Regole
------
- Client httpx diretto (niente SDK), con `httpx.AsyncClient` iniettabile: nei test si usa `MockTransport`.
  Le route lo ottengono dalla dependency `get_zernio_http`, sovrascrivibile in `app.dependency_overrides`.
- **Nessun nuovo tentativo**: su 5xx o timeout Zernio non ritenta e rilascia l'`Idempotency-Key`, quindi
  ritentare un invio potrebbe consegnare due volte. Un errore di rete o un timeout è `SERVER`.
- **Timeout**: invio 4 s (il webhook deve rispondere entro 5 s; misurato 1,2-3,1 s, con 3 s scadeva a freddo), configurazione 10 s.
- **Errori classificati su status, `code` e `platformError`**, mai sul testo di `error` (non è stabile).
  Un 403 è `AUTH` solo con `insufficient_permissions`/`invalid_credentials`: Zernio lo usa anche per
  "addon inbox mancante" e "Meta ha rifiutato l'invio fuori finestra", che non sono problemi di chiave.
- **Nessun segreto** (chiave, secret del webhook, token del link) in log, repr o messaggi di errore: i
  messaggi di `ZernioError` sono fissi e non citano né il corpo della richiesta né quello della risposta.
- `zernio_credentials_for(merchant)` è l'**unico** punto che legge `Merchant.zernio_api_key_enc` e
  `webhook_secret_enc` e li decifra. Con la chiave unica del founder cambierà solo quella funzione.

Endpoint, limiti e fonti: `.agents/architecture/zernio-notes.md`.
"""

import logging
from enum import Enum
from typing import Optional
from urllib.parse import quote

import httpx
from pydantic import BaseModel, SecretStr

from app.core import crypto
from app.core.config import settings
from app.services.instagram_service import CardMessage

logger = logging.getLogger(__name__)

# --- Core puro ---

WEBHOOK_NAME = "Fidelitree"
WEBHOOK_EVENTS = ["message.received"]
MENU_LOCALE = "default"

_AUTH_CODES = {"insufficient_permissions", "invalid_credentials"}
_QUOTA_CODE = "message_allowance_exceeded"
_NOT_THREAD_OWNER_CODE = "not_thread_owner"
_NOT_THREAD_OWNER_SUBCODE = "2534037"   # Meta: la conversazione appartiene a un'altra app
_NOT_FOLLOWER = ("2", "1545133")        # Meta: (code, subcode) di card/bottoni rifiutati a chi non segue


class ZernioErrorKind(str, Enum):
    """Che cosa è andato storto con Zernio, a prescindere dal testo dell'errore."""
    AUTH = "auth"                          # chiave non valida, revocata o senza i permessi necessari
    QUOTA = "quota"                        # invii mensili gratuiti esauriti
    NOT_THREAD_OWNER = "not_thread_owner"  # la conversazione è di un'altra app (standby)
    NOT_FOLLOWER = "not_follower"          # Meta rifiuta la card a chi non segue l'account
    RATE_LIMITED = "rate_limited"
    SERVER = "server"                      # 5xx, timeout o rete
    BAD_REQUEST = "bad_request"            # ogni altro 4xx, compreso ogni altro 403
    NOT_CONFIGURED = "not_configured"      # mancano chiave o account (nessuna chiamata fatta)


_ERROR_MESSAGES = {
    ZernioErrorKind.AUTH: "Zernio ha rifiutato la chiave (non valida, revocata o senza permessi)",
    ZernioErrorKind.QUOTA: "Quota mensile di invii Zernio esaurita",
    ZernioErrorKind.NOT_THREAD_OWNER: "La conversazione è gestita da un'altra app (standby)",
    ZernioErrorKind.NOT_FOLLOWER: "Instagram non consente la card a chi non segue l'account",
    ZernioErrorKind.RATE_LIMITED: "Troppe richieste a Zernio: riprova tra poco",
    ZernioErrorKind.SERVER: "Zernio non ha risposto correttamente (errore del servizio, rete o timeout)",
    ZernioErrorKind.BAD_REQUEST: "Zernio ha rifiutato la richiesta",
    ZernioErrorKind.NOT_CONFIGURED: "Instagram non è collegato: mancano la chiave o l'account Zernio",
}


def error_message(kind: ZernioErrorKind) -> str:
    """Messaggio fisso in italiano per un tipo di errore. Non contiene mai chiave né dati della risposta."""
    return _ERROR_MESSAGES[kind]


def _platform_error(body: Optional[dict]) -> dict:
    """`platformError` del corpo dell'errore, o dizionario vuoto se manca o ha un'altra forma."""
    value = body.get("platformError") if isinstance(body, dict) else None
    return value if isinstance(value, dict) else {}


def classify_error(status: int, body: Optional[dict]) -> ZernioErrorKind:
    """
    Classifica una risposta d'errore di Zernio su status, `code` e `platformError`, mai sul testo di `error`:
    401 e 403 `insufficient_permissions`/`invalid_credentials` → AUTH; 403 `message_allowance_exceeded` → QUOTA;
    409 `not_thread_owner` (o subcode Meta 2534037) → NOT_THREAD_OWNER; 400 con `platformError` 2/1545133 →
    NOT_FOLLOWER; 429 → RATE_LIMITED; 5xx → SERVER; ogni altro 4xx, compreso ogni altro 403 → BAD_REQUEST.
    `body` può essere `None` o non essere un dizionario.
    """
    code = body.get("code") if isinstance(body, dict) else None
    platform = _platform_error(body)
    if status == 401:
        return ZernioErrorKind.AUTH
    if status == 403:
        if code in _AUTH_CODES:
            return ZernioErrorKind.AUTH
        if code == _QUOTA_CODE:
            return ZernioErrorKind.QUOTA
        return ZernioErrorKind.BAD_REQUEST
    if status == 409 and (code == _NOT_THREAD_OWNER_CODE or str(platform.get("subcode")) == _NOT_THREAD_OWNER_SUBCODE):
        return ZernioErrorKind.NOT_THREAD_OWNER
    if status == 400 and (str(platform.get("code")), str(platform.get("subcode"))) == _NOT_FOLLOWER:
        return ZernioErrorKind.NOT_FOLLOWER
    if status == 429:
        return ZernioErrorKind.RATE_LIMITED
    if status >= 500:
        return ZernioErrorKind.SERVER
    return ZernioErrorKind.BAD_REQUEST


def build_card_body(account_id: str, card: CardMessage) -> dict:
    """
    Corpo dell'invio della card: `template` generic con un elemento e un bottone `url`. Niente `message` né
    `buttons` di primo livello (con `template` sono mutuamente esclusivi: Zernio risponde 400).
    """
    return {
        "accountId": account_id,
        "template": {
            "type": "generic",
            "elements": [{
                "title": card.title,
                "subtitle": card.subtitle,
                "buttons": [{"type": "url", "title": card.button_title, "url": card.button_url}],
            }],
        },
    }


def build_text_body(account_id: str, text: str) -> dict:
    """Corpo dell'invio di un testo semplice (il ripiego quando Meta rifiuta la card)."""
    return {"accountId": account_id, "message": text}


def build_webhook_body(account_id: str, url: str, secret: str) -> dict:
    """Corpo della registrazione del webhook: solo `message.received`, solo l'account del negozio, firmato."""
    return {
        "name": WEBHOOK_NAME,
        "url": url,
        "events": list(WEBHOOK_EVENTS),
        "secret": secret,
        "accountIds": [account_id],
        "isActive": True,
    }


def build_menu_body(title: str, payload: str) -> dict:
    """Corpo del menu persistente (formato Meta): una sola voce `postback` con payload fisso."""
    return {"persistent_menu": [{
        "locale": MENU_LOCALE,
        "call_to_actions": [{"type": "postback", "title": title, "payload": payload}],
    }]}


class ZernioAccount(BaseModel):
    """Account Instagram collegato a Zernio, come serve all'onboarding."""

    id: str
    username: Optional[str] = None
    profile_id: Optional[str] = None


def parse_accounts(body: object) -> list[ZernioAccount]:
    """
    Account Instagram dalla risposta di `GET /v1/accounts`: si scartano le altre piattaforme e le voci senza
    id. `profileId` può arrivare come stringa o come oggetto con `_id`. Un corpo inatteso dà una lista vuota.
    """
    items = body.get("accounts") if isinstance(body, dict) else None
    accounts: list[ZernioAccount] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or item.get("platform") != "instagram":
            continue
        account_id = item.get("_id") or item.get("id")
        if not account_id:
            continue
        profile = item.get("profileId")
        if isinstance(profile, dict):
            profile = profile.get("_id") or profile.get("id")
        accounts.append(ZernioAccount(
            id=str(account_id),
            username=item.get("username") or None,
            profile_id=str(profile) if profile else None,
        ))
    return accounts


class ZernioCredentials(BaseModel):
    """
    Con che cosa si parla a Zernio per un negozio. Chiave e secret sono `SecretStr`: non compaiono in
    `repr`, `str`, `model_dump_json` né nei log. `quota_scope` è l'ambito del contatore degli invii
    (`quota_scope_for`); vuoto se non c'è ancora un account.
    """

    api_key: SecretStr
    account_id: Optional[str] = None
    profile_id: Optional[str] = None
    webhook_secret: Optional[SecretStr] = None
    quota_scope: str = ""


def quota_scope_for(team_id: Optional[str], account_id: Optional[str]) -> str:
    """
    Ambito della quota: `"zernio:<team_id>"` se l'identità del team è nota (Zernio conta gli invii per team),
    altrimenti `"account:<account_id>"`; vuoto senza nessuno dei due. Con la chiave unica diventerà `"platform"`.
    """
    if team_id:
        return f"zernio:{team_id}"
    if account_id:
        return f"account:{account_id}"
    return ""


# --- Shell ---

SEND_TIMEOUT = 4.0     # secondi: il webhook deve rispondere a Zernio entro 5 s (misurato: 1,2-3,1 s)
CONFIG_TIMEOUT = 10.0  # secondi: onboarding e script


class ZernioError(Exception):
    """
    Errore nella comunicazione con Zernio. `kind` dice che cosa è successo, `status` è l'HTTP (`None` se non
    c'è stata risposta). Il messaggio è fisso: mai la chiave, né il corpo della richiesta o della risposta.
    """

    def __init__(self, kind: ZernioErrorKind, status: Optional[int] = None):
        super().__init__(error_message(kind))
        self.kind = kind
        self.status = status


def make_http_client(timeout: float = CONFIG_TIMEOUT) -> httpx.AsyncClient:
    """Client httpx per Zernio con il timeout dato (le singole chiamate lo ridefiniscono)."""
    return httpx.AsyncClient(timeout=timeout)


async def get_zernio_http():
    """Dependency FastAPI: un client httpx per richiesta, chiuso alla fine. Nei test si sovrascrive."""
    async with make_http_client() as client:
        yield client


def credentials_from_key(api_key: str, account_id: Optional[str] = None) -> ZernioCredentials:
    """Credenziali da una chiave in chiaro non ancora salvata (onboarding, script); nessun team noto."""
    return ZernioCredentials(
        api_key=api_key, account_id=account_id, quota_scope=quota_scope_for(None, account_id),
    )


def zernio_credentials_for(merchant, *, require_account: bool = True) -> ZernioCredentials:
    """
    Credenziali Zernio del negozio: decifra chiave e secret del webhook. **Unico** codice che legge
    `Merchant.zernio_api_key_enc` e `webhook_secret_enc`. `ZernioError(NOT_CONFIGURED)` se mancano chiave o
    account, o se la chiave non si decifra (dato alterato o chiave di cifratura diversa; nessun dettaglio).
    Con `require_account=False` (onboarding: chiave salvata, account Instagram non ancora scelto) l'account
    può mancare: la chiave è comunque obbligatoria.
    """
    if not merchant.zernio_api_key_enc or (require_account and not merchant.zernio_account_id):
        raise ZernioError(ZernioErrorKind.NOT_CONFIGURED)
    try:
        api_key = crypto.decrypt_secret(merchant.zernio_api_key_enc)
        secret = crypto.decrypt_secret(merchant.webhook_secret_enc) if merchant.webhook_secret_enc else None
    except crypto.SecretDecryptionError:
        logger.error("Credenziali Zernio del negozio %s illeggibili", merchant.id)
        raise ZernioError(ZernioErrorKind.NOT_CONFIGURED) from None
    return ZernioCredentials(
        api_key=api_key,
        account_id=merchant.zernio_account_id,
        profile_id=merchant.zernio_profile_id,
        webhook_secret=secret,
        quota_scope=quota_scope_for(merchant.zernio_team_id, merchant.zernio_account_id),
    )


def _account_id(creds: ZernioCredentials) -> str:
    """Account Instagram delle credenziali, o `ZernioError(NOT_CONFIGURED)` se manca."""
    if not creds.account_id:
        raise ZernioError(ZernioErrorKind.NOT_CONFIGURED)
    return creds.account_id


def _json_or_none(response: httpx.Response) -> Optional[dict]:
    """Corpo JSON della risposta se è un oggetto, altrimenti `None`."""
    try:
        data = response.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


async def _request(
    http: httpx.AsyncClient,
    creds: ZernioCredentials,
    method: str,
    path: str,
    *,
    timeout: float,
    json: Optional[dict] = None,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> dict:
    """
    Una sola richiesta (mai ritentata) con `Authorization: Bearer`. Ritorna il corpo JSON (vuoto se assente);
    solleva `ZernioError` su rete/timeout (`SERVER`) o status ≥ 400 (`classify_error`). Si logga solo
    metodo, path (senza query), status e tipo: mai corpi né chiave.
    """
    url = f"{settings.ZERNIO_BASE_URL.rstrip('/')}{path}"
    request_headers = {"Authorization": f"Bearer {creds.api_key.get_secret_value()}", **(headers or {})}
    try:
        response = await http.request(
            method, url, headers=request_headers, json=json, params=params, timeout=timeout,
        )
    except httpx.HTTPError:
        logger.warning("Zernio %s %s: errore di rete o timeout", method, path)
        raise ZernioError(ZernioErrorKind.SERVER) from None
    body = _json_or_none(response)
    if response.status_code >= 400:
        kind = classify_error(response.status_code, body)
        logger.warning("Zernio %s %s: HTTP %s (%s)", method, path, response.status_code, kind.value)
        raise ZernioError(kind, response.status_code)
    return body or {}


async def list_instagram_accounts(http: httpx.AsyncClient, creds: ZernioCredentials) -> list[ZernioAccount]:
    """Account Instagram collegati alla chiave (`GET /v1/accounts`); serve anche a validarla (401 → AUTH)."""
    body = await _request(
        http, creds, "GET", "/v1/accounts", timeout=CONFIG_TIMEOUT,
        params={"platform": "instagram", "status": "connected"},
    )
    return parse_accounts(body)


async def _send(
    http: httpx.AsyncClient, creds: ZernioCredentials, conversation_id: str, body: dict, idempotency_key: str,
) -> str:
    """Invio in una conversazione. Ritorna `data.messageId`, o `""` se la risposta 2xx non lo riporta."""
    data = (await _request(
        http, creds, "POST", f"/v1/inbox/conversations/{quote(conversation_id, safe='')}/messages",
        timeout=SEND_TIMEOUT, json=body, headers={"Idempotency-Key": idempotency_key},
    )).get("data")
    message_id = data.get("messageId") if isinstance(data, dict) else None
    return str(message_id) if message_id else ""


async def send_card(
    http: httpx.AsyncClient, creds: ZernioCredentials, conversation_id: str, card: CardMessage,
    idempotency_key: str,
) -> str:
    """
    Invia la card nella conversazione; ritorna `messageId` (`""` se la risposta non lo riporta: un 2xx è
    comunque consegnato, non va rifatto). Nessun nuovo tentativo: un 5xx può aver già consegnato.
    """
    return await _send(http, creds, conversation_id, build_card_body(_account_id(creds), card), idempotency_key)


async def send_text(
    http: httpx.AsyncClient, creds: ZernioCredentials, conversation_id: str, text: str, idempotency_key: str,
) -> str:
    """Invia un testo semplice nella conversazione (ripiego della card). Stesse regole di `send_card`."""
    return await _send(http, creds, conversation_id, build_text_body(_account_id(creds), text), idempotency_key)


async def register_webhook(http: httpx.AsyncClient, creds: ZernioCredentials, url: str, secret: str) -> str:
    """
    Registra il webhook del negozio (`POST /v1/webhooks/settings`) e ritorna il suo id (`webhook._id`).
    `ZernioError(SERVER)` se la risposta non contiene l'id: senza non si potrebbe più rimuovere.
    """
    body = await _request(
        http, creds, "POST", "/v1/webhooks/settings", timeout=CONFIG_TIMEOUT,
        json=build_webhook_body(_account_id(creds), url, secret),
    )
    webhook = body.get("webhook")
    webhook_id = webhook.get("_id") if isinstance(webhook, dict) else None
    if not webhook_id:
        raise ZernioError(ZernioErrorKind.SERVER)
    return str(webhook_id)


async def delete_webhook(http: httpx.AsyncClient, creds: ZernioCredentials, webhook_id: str) -> None:
    """Elimina il webhook (`DELETE /v1/webhooks/settings?webhookId=...`)."""
    await _request(
        http, creds, "DELETE", "/v1/webhooks/settings", timeout=CONFIG_TIMEOUT, params={"webhookId": webhook_id},
    )


async def get_persistent_menu(http: httpx.AsyncClient, creds: ZernioCredentials) -> list:
    """Menu persistente dell'account (`data` nel formato Meta); lista vuota se non c'è."""
    body = await _request(
        http, creds, "GET", f"/v1/accounts/{quote(_account_id(creds), safe='')}/messenger-menu",
        timeout=CONFIG_TIMEOUT,
    )
    data = body.get("data")
    return data if isinstance(data, list) else []


async def set_persistent_menu(http: httpx.AsyncClient, creds: ZernioCredentials, title: str, payload: str) -> None:
    """Imposta il menu con la sola voce `postback` (`PUT .../messenger-menu`). Sostituisce quello esistente."""
    await _request(
        http, creds, "PUT", f"/v1/accounts/{quote(_account_id(creds), safe='')}/messenger-menu",
        timeout=CONFIG_TIMEOUT, json=build_menu_body(title, payload),
    )


async def list_conversations(
    http: httpx.AsyncClient, creds: ZernioCredentials, folder: Optional[str] = None,
) -> list[dict]:
    """
    Conversazioni Instagram dell'account (`GET /v1/inbox/conversations`), solo per lo script di collaudo.
    `folder="requests"` per i Message Requests: con Instagram Login Zernio risponde 400 `PLATFORM_LIMITATION`.
    """
    params = {"accountId": _account_id(creds), "platform": "instagram"}
    if folder:
        params["folder"] = folder
    body = await _request(http, creds, "GET", "/v1/inbox/conversations", timeout=CONFIG_TIMEOUT, params=params)
    data = body.get("data")
    return data if isinstance(data, list) else []


async def get_team_identity(http: httpx.AsyncClient, creds: ZernioCredentials) -> Optional[str]:
    """
    Identificativo stabile del team Zernio della chiave, per l'ambito della quota. Oggi **sempre `None`**: la
    spec non espone un id di team (`GET /v1/users` dà `currentUserId`, che è l'utente, non il team) e si
    ripiega su `account:<id>`. Nessuna chiamata di rete.
    """
    return None
