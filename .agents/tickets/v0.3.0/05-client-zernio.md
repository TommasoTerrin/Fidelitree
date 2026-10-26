# 05 — Client Zernio, `zernio_check` e collaudo anticipato

## Obiettivo
1. Un client **httpx diretto** per l'API Zernio (niente `zernio-sdk`), sul modello di `ecologi_service.py`.
2. Il **punto di aggancio** `zernio_credentials_for(merchant)`.
3. Lo script `zernio_check` per le chiamate reali.
4. Un **collaudo manuale anticipato** su un account Instagram vero, per verificare i rischi non documentati prima di
   costruire webhook e onboarding.

## Contesto
Endpoint, limiti ed errori in [zernio-notes.md](../../architecture/zernio-notes.md).
- **Base URL**: `ZERNIO_BASE_URL`, autenticazione `Authorization: Bearer <key>`.
- **Nessun nuovo tentativo sugli invii**: su 5xx o timeout Zernio non ritenta, rilascia l'`Idempotency-Key` e un nuovo
  tentativo potrebbe consegnare due volte.
- **Timeout**: invio 4 s (il webhook deve rispondere entro 5 s; era 3 s, alzato il 2026-10-26); chiamate di configurazione 10 s.
- **Errori**: si classificano su status, `code` e `platformError`, mai sul testo di `error`.
- **Migrazione futura** (chiave unica del founder e un `profileId` per negozio): oggi
  `zernio_credentials_for(merchant)` restituisce la chiave del merchant; domani restituirà quella di piattaforma.
  `quota_scope` segue il **team Zernio** che fa l'invio, non il merchant, perché Zernio conta gli invii per team.
  Così un merchant che incolla una chiave di un altro account Zernio a metà mese non eredita il conteggio vecchio:
  - oggi `"zernio:<Merchant.zernio_team_id>"`, valore catturato all'onboarding;
  - se l'identità del team non è disponibile, `"account:<zernio_account_id>"`;
  - domani `"platform"`.

  Nessun altro modulo deve sapere da dove arriva la chiave.

## Dipendenze
03, 04.

## Modifiche
1. **`app/services/zernio_service.py`** (nuovo):
   - **Core puro**:
     - `ZernioErrorKind(str, Enum)`: `AUTH`, `QUOTA`, `NOT_THREAD_OWNER`, `NOT_FOLLOWER`, `RATE_LIMITED`, `SERVER`,
       `BAD_REQUEST`, `NOT_CONFIGURED`.
     - `classify_error(status: int, body: dict | None) -> ZernioErrorKind`, con questa mappatura:

       | Risposta Zernio | Tipo |
       |---|---|
       | 401; 403 con `code` `insufficient_permissions` o `invalid_credentials` | `AUTH` |
       | 403 `message_allowance_exceeded` | `QUOTA` |
       | 409 `not_thread_owner` | `NOT_THREAD_OWNER` |
       | 400 con `platformError.code == 2` e `subcode == 1545133` | `NOT_FOLLOWER` |
       | 429 | `RATE_LIMITED` |
       | 5xx | `SERVER` |
       | altro 4xx, **compreso ogni altro 403** | `BAD_REQUEST` |

       Nota sull'ultima riga: Zernio usa il 403 anche per "addon inbox mancante" e per "Meta ha rifiutato l'invio
       fuori finestra". Non sono problemi di chiave, quindi non devono portare il merchant a `KEY_INVALID`.

     - `build_card_body(account_id, card: CardMessage) -> dict`: `{"accountId", "template": {"type": "generic",
       "elements": [{"title", "subtitle", "buttons": [{"type": "url", "title", "url"}]}]}}`. Niente `message` né
       `buttons` di primo livello.
     - `build_text_body(account_id, text) -> dict`.
     - `ZernioAccount(BaseModel)` (`id`, `username`, `profile_id`) e
       `parse_accounts(body) -> list[ZernioAccount]`, che considera solo `platform == "instagram"`.
     - `ZernioCredentials(BaseModel)`: `api_key: SecretStr`, `account_id`, `profile_id`,
       `webhook_secret: SecretStr | None`, `quota_scope: str`. Con `SecretStr` la chiave non compare in `repr` né nei
       log.
   - **Shell** (async):
     - `ZernioError(Exception)` con `kind` e `status`. Il messaggio è in italiano e non contiene mai la chiave né il
       corpo della richiesta.
     - `zernio_credentials_for(merchant) -> ZernioCredentials` decifra chiave e secret con `crypto`. Se mancano chiave
       o account solleva `ZernioError(NOT_CONFIGURED)`. **Unico** punto che legge i campi cifrati del merchant.
     - `credentials_from_key(api_key, account_id=None) -> ZernioCredentials`, per onboarding e script (chiave non
       ancora salvata).
     - `make_http_client(timeout) -> httpx.AsyncClient` e la dependency FastAPI `get_zernio_http()`, sovrascrivibile
       nei test.
     - `list_instagram_accounts(http, creds)`: `GET /v1/accounts?platform=instagram&status=connected`.
     - `send_card(http, creds, conversation_id, card, idempotency_key) -> str` e `send_text(...)`:
       `POST /v1/inbox/conversations/{id}/messages` con header `Idempotency-Key`; restituiscono `data.messageId`.
     - `register_webhook(http, creds, url, secret) -> str`: `POST /v1/webhooks/settings` con `name="Fidelitree"`,
       `events=["message.received"]`, `secret`, `accountIds=[account_id]`, `isActive=True`; restituisce l'id del webhook.
     - `delete_webhook(http, creds, webhook_id) -> None`.
     - `get_persistent_menu(http, creds) -> list` e `set_persistent_menu(http, creds, title, payload) -> None`
       (`/v1/accounts/{accountId}/messenger-menu`).
     - `list_conversations(http, creds, folder=None) -> list[dict]`, solo per lo script.
     - `get_team_identity(http, creds) -> str | None`: identificativo stabile del team o account Zernio della chiave.
       Candidato: `GET /v1/users` → `currentUserId`, oppure un id di team se la spec lo espone. **Verifica nella spec**
       quale campo identifica il team (la quota è per team) e annotalo in zernio-notes. Se nessun campo è affidabile,
       restituisci `None` e si usa il fallback `account:<id>`.
     - Prima di scriverle, controlla nella spec `https://zernio.com/openapi.yaml` path e corpo esatti di
       `delete_webhook`, `get/set_persistent_menu` e `list_conversations`, e il limite del titolo della voce di menu.
       Annota in zernio-notes i valori trovati.
2. **`scripts/zernio_check.py`** (stile `ecologi_check`: `main(argv) -> int`, exit 0/1, nessun accesso al DB). La chiave
   si legge da env `ZERNIO_CHECK_API_KEY` oppure con `getpass`, mai da argomento della riga di comando, che finirebbe
   nella history.
   - `accounts`: elenca gli account Instagram collegati (id, @username).
   - `conversations --account-id X [--folder requests]`: id della conversazione e data, **senza** IGSID né username
     dei clienti.
   - `send-card --account-id X --conversation-id Y [--name "Negozio di prova"] [--url https://...]`: invia la card
     costruita dal core.
   - `send-text --account-id X --conversation-id Y [--url ...]`: invia il testo di ripiego.
   - Stampa sempre la chiave mascherata (`…1234`) e l'esito con il `kind` dell'eventuale errore.

## File coinvolti
`app/services/zernio_service.py` (nuovo), `scripts/zernio_check.py` (nuovo), `tests/unit/test_zernio_core.py` (nuovo),
`tests/test_zernio_client.py` (nuovo), `tests/test_scripts.py`, `.agents/architecture/zernio-notes.md` (esiti del
collaudo), `AGENTS.md` (comando).

## Test da superare
**Unit:**
- `classify_error`: un caso per ogni riga della mappatura. Un 403 senza `code` e un 403 con un `code` diverso da quelli
  di autorizzazione e quota danno `BAD_REQUEST`, **non** `AUTH`.
- `build_card_body`: struttura esatta, un solo elemento, un solo bottone di tipo `url`, nessuna chiave `buttons` o
  `message` di primo livello.
- `parse_accounts` scarta le piattaforme diverse da Instagram.
- `repr(ZernioCredentials(...))` non contiene la chiave.

**Integrazione (`httpx.MockTransport`, nessuna rete):**
- `send_card`: metodo, path, header `Authorization: Bearer …` e `Idempotency-Key`, corpo atteso; restituisce
  `messageId`.
- Errori: 401 → `ZernioError(AUTH)`; 409 `not_thread_owner` → `NOT_THREAD_OWNER`; 500 → `SERVER`; eccezione di rete o
  timeout → `SERVER`. Il messaggio non contiene mai la chiave e c'è **una sola** richiesta, senza nuovi tentativi.
- `list_instagram_accounts`: query string `platform=instagram&status=connected`.
- `register_webhook`: corpo con `events`, `secret`, `accountIds`; restituisce l'id.
- `zernio_credentials_for`:
  - merchant con chiave e account cifrati → credenziali corrette e `quota_scope == "zernio:<zernio_team_id>"`;
  - merchant con `zernio_team_id` vuoto → `quota_scope == "account:<zernio_account_id>"`;
  - merchant senza chiave → `ZernioError(NOT_CONFIGURED)`.
- `zernio_check`:
  - `accounts` con chiave da env → exit 0, l'output contiene `…<ultime4>` e **non** la chiave intera;
  - 401 → exit 1 e messaggio su stderr;
  - `send-card` invia un solo POST con il corpo del core.

## Collaudo manuale anticipato (a cura del founder, PRIMA del ticket 07)
> Spostato il 2026-10-23: il 06 si scrive e si testa con risposte finte. Prima del 07 servono almeno i passi 1-2 (chiave,
> base URL, card su mobile al profilo che segue). Il passo 3 (profilo che non segue) si rifà nel collaudo finale (11).
Servono: un account Zernio gratuito; un account Instagram Business o Creator di prova collegato a Zernio; due profili
Instagram personali, A **che segue** il negozio e B **che non lo segue**.
1. `python -m scripts.zernio_check accounts` → l'account compare. Se `https://zernio.com/api` risponde 404, prova
   `https://api.zernio.com` e annota quale vale.
2. Dal profilo A scrivi "CARTA" al negozio. Con `conversations` trova la conversazione e lancia `send-card`.
   Annota:
   - la card arriva su A nell'app mobile?
   - si vede su instagram.com da desktop? Ci si aspetta di no.
3. Dal profilo B scrivi "CARTA": il messaggio finisce in Requests. Lancia `conversations --folder requests` e poi
   `send-card`. Annota:
   - risultato (ok o errore 2/1545133);
   - se la conversazione passa in Generale;
   - se `send-text` funziona.
4. Aggiorna zernio-notes.md: le righe "non verificato" toccate diventano "sì", con data e esito.

**Se la card a B è rifiutata e anche il testo fallisce, oppure se emerge altro di inatteso: fermati e chiedi.**
I controlli che richiedono il webhook (arrivo dei DM in Requests, standby con ManyChat) si fanno nel collaudo del
ticket 07.

## Fuori scope
Webhook (06), onboarding (07), modalità chiave unica (solo il punto di aggancio).

## Definition of Done
Suite verde, `python -m scripts.zernio_check --help` funziona, collaudo manuale 1-4 fatto ed esiti scritti in
zernio-notes.md.
