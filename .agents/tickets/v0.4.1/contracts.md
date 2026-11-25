# v0.4.1 — Contract (gate 2, parte 2 di 2)

> **Stato: APPROVATO il 2026-11-12 (gate 2), CONGELATO.** `ft-test-writer` e `ft-implementer` lavorano solo da qui
> e dai criteri `AC-NN` della [spec](README.md); cambiarlo richiede `/fix`.
> Convenzioni: docstring e commenti in italiano, precisi e completi (anche test e script); core puro (solo stdlib e
> Pydantic, niente `Session`, `httpx`, `fastapi`, `settings` né `datetime.now()`: tempo e parola di `CARTA` si
> passano come argomenti); errori di `app/core/errors.py`, mai `HTTPException` nei service; soldi in centesimi
> (`*_cents`), euro solo ai bordi; timestamp UTC aware. Modello: [domain-model.md](domain-model.md).

## 1. Costanti e configurazione

```python
# app/core/text.py
INSTAGRAM_TEXT_MAX = 1000          # caratteri (len() Python) di un DM di testo o di una risposta privata

# app/services/campaign_service.py
NAME_MIN, NAME_MAX = 3, 40
KEYWORD_MIN, KEYWORD_MAX = 3, 30   # sulla forma scritta (strip), vedi §4
PROMO_TEXT_MIN, PROMO_TEXT_MAX = 1, 850
VALUE_MIN_CENTS, VALUE_MAX_CENTS = 0, 5000

# app/services/zernio_service.py
WEBHOOK_EVENTS = ["message.received", "comment.received"]   # era ["message.received"]
```

- **Nessuna env var nuova**, nessuna dipendenza nuova. La parola di `CARTA` resta `settings.INSTAGRAM_CARD_KEYWORD`,
  letta solo dalla shell.
- **Versione**: `pyproject.toml` `version = "0.4.1"` e `scripts/smoke_test_prod.py` `EXPECTED_VERSION = "0.4.1"`
  (AC-29; `tests/test_version.py` le confronta).

## 2. `app/core/text.py` (nuovo)

```python
def normalize_text(text: Optional[str]) -> str
```
Spostata da `instagram_service` **senza cambiare comportamento**: NFKD senza segni diacritici, `casefold`, ogni
carattere non alfanumerico → spazio, spazi compattati, `strip`; `None` o `""` → `""`. `instagram_service` la
ri-esporta (`from app.core.text import normalize_text`): `instagram_service.normalize_text` resta importabile e i
test di oggi non cambiano. Esempi: `"Black-Friday!"` → `"black friday"`, `"BLACK-FRIDAY 🎄"` → `"black friday"`,
`"blackfriday"` → `"blackfriday"`, `"!!"` → `""`.

## 3. Modello (`app/models/models.py`)

```python
class Campaign(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: int = Field(foreign_key="merchant.id", ondelete="CASCADE", index=True)
    name: str = Field(max_length=40)
    keyword: str = Field(max_length=30)        # come l'ha scritta il founder (strip), MAI normalizzata
    promo_text: str = Field(max_length=850)
    value_cents: int = Field(default=0)        # 0 = nessun importo (D1)
    request_limit: Optional[int] = Field(default=None)   # None = nessun limite
    is_archived: bool = Field(default=False)
    dm_requests: int = Field(default=0)        # DM e risposte alle storie
    comment_requests: int = Field(default=0)
    uses: int = Field(default=0)               # «Applica» confermati
    created_at: datetime = _created_at_field()  # UTC aware, NOT NULL

    merchant: Merchant = Relationship(back_populates="campaigns")
```

- Tabella `campaign`; colonne non `Optional` = `NOT NULL`; **nessun default lato DB** (`server_default`): i valori
  iniziali li mette l'app, come per tutte le altre tabelle.
- `Merchant.campaigns: List["Campaign"] = Relationship(back_populates="merchant", sa_relationship_kwargs={"cascade":
  "all, delete-orphan"})` — solo lato ORM, nessuna colonna (I8): eliminare un negozio elimina le sue campagne anche
  su SQLite, dove i test non applicano `ON DELETE CASCADE`.
- Nessun'altra tabella o enum cambia (I8). In particolare `WebhookOutcome` resta com'è.

## 4. `campaign_service` — core puro

```python
class RequestChannel(str, Enum):
    DM = "dm"              # DM e risposte alle storie
    COMMENT = "comment"

class CampaignStatus(str, Enum):        # NON è una colonna: si deriva (R3)
    ACTIVE = "active"; ARCHIVED = "archived"; STOPPED = "stopped"   # stopped = negozio in attesa o in pausa

class CampaignInput(BaseModel):         # già validato
    name: str; keyword: str; promo_text: str; value_cents: int; request_limit: Optional[int]

class CampaignKey(BaseModel):           # quanto serve al confronto delle parole chiave
    id: int; keyword: str               # keyword come salvata (forma scritta)

def validate_campaign_input(raw: object) -> CampaignInput
```
`raw` è il corpo grezzo (`dict` con `name`, `keyword`, `promo_text`, `value_eur`, `request_limit`; chiavi mancanti =
`None`). Qualunque tipo sbagliato dà `InvalidInputError` (400), mai `TypeError`. Il messaggio cita il campo e la
regola, mai il valore inviato. Regole:
- `raw` non `dict` → errore.
- `name`: stringa; `strip`; 3-40 caratteri.
- `keyword`: stringa; `strip`; nessun carattere di spazio al suo interno (`str.isspace`); 3-30 caratteri;
  `normalize_text(keyword)` non vuota. Salvata come risulta dopo lo `strip` (es. `"Black-Friday"`).
- `promo_text`: stringa; `strip` ai lati (gli a capo interni restano); 1-850 caratteri.
- `value_eur`: `None`, `""` o assente → 0; numero (`int`/`float`, **non** `bool`) oppure stringa con un numero (virgola
  o punto decimale); non finito o non numerico → errore; centesimi con `money.euro_to_cents`; ammessi 0-5000.
- `request_limit`: `None`, `""` o assente → `None`; intero (non `bool`) o stringa di sole cifre; un `float` con parte
  decimale → errore; ammesso solo ≥ 1 (0 e negativi → errore).

Esempi di AC-03 che danno 400: nome `"ab"`; parola `"NATALE 2026"`; parola `"!!"`; testo di 851 caratteri; importo
`50.01`; limite `0`.

```python
def keyword_conflict(keyword: str, card_keyword: str, others: Iterable[CampaignKey],
                     exclude_id: Optional[int] = None) -> Optional[str]
```
`None` se la parola è libera; altrimenti il motivo, uno tra `"riservata"` (normalizzata uguale a `card_keyword`
normalizzata) e `"in uso"` (uguale alla forma normalizzata di una di `others` con `id != exclude_id`). `others` sono
le campagne **non archiviate** dello stesso negozio (lo filtra il chiamante).

```python
def campaign_status(is_archived: bool, merchant_state: ServiceState) -> CampaignStatus
    # ARCHIVED se archiviata; altrimenti ACTIVE con negozio ACTIVE, STOPPED con PENDING o PAUSED
def match_campaign(text: Optional[str], campaigns: Iterable[CampaignKey]) -> Optional[int]
    # id della prima campagna (nell'ordine dato) con normalize_text(keyword) == normalize_text(text);
    # testo vuoto dopo la normalizzazione → None. Il chiamante passa solo le non archiviate.
def is_within_limit(total_requests: int, request_limit: Optional[int]) -> bool
    # True senza limite; altrimenti total_requests <= request_limit (totale DM + commenti DOPO l'incremento)
def pause_begins(before: ServiceState, after: ServiceState) -> bool
    # True solo se after is PAUSED e before is not PAUSED
def scanner_label(name: str, value_cents: int) -> str
    # value_cents > 0 → f"Applica {name} (+{euro} €)" con euro = due decimali e virgola (250 → "2,50");
    # value_cents == 0 → f"Applica {name}"
```

### Testi dei DM (byte per byte; R7, AC-27)

```python
PROMO_FOOTER = ("Per utilizzare questa offerta devi avere la nostra carta fedeltà. "
                "Se non l'hai ricevuta o non la ritrovi nella chat scrivi {keyword}.")
EXHAUSTED_TEXT = ("Le offerte disponibili sono terminate. Per essere informato più velocemente la prossima volta "
                  "attiva la campanella delle notifiche al profilo!!")

def build_promo_text(promo_text: str, card_keyword: str) -> str
    # f"{promo_text}\n\n" + PROMO_FOOTER.format(keyword=card_keyword)
    # InvalidInputError se promo_text è vuoto dopo lo strip; MessageTooLongError se il totale > INSTAGRAM_TEXT_MAX
def build_exhausted_text() -> str          # EXHAUSTED_TEXT
def campaign_reply_text(promo_text: str, total_requests: int, request_limit: Optional[int],
                        card_keyword: str) -> str
    # build_promo_text(...) se is_within_limit(...), altrimenti build_exhausted_text()
```

Con `promo_text` di 850 caratteri e `card_keyword="CARTA"` il DM completo sta sotto i 1000 (AC-27). L'apostrofo di
«l'hai» è l'ASCII `'`; «fedeltà» e «più» con le lettere accentate.

### Righe per `/admin` e per lo scanner

```python
class CampaignRow(BaseModel):
    id: int; merchant_id: int; name: str; keyword: str; promo_text: str
    value_cents: int; request_limit: Optional[int]; is_archived: bool; status: CampaignStatus
    dm_requests: int; comment_requests: int; uses: int; created_at: datetime
def campaign_row(campaign, merchant_state: ServiceState) -> CampaignRow   # puro; created_at senza fuso → UTC

class ScannerCampaign(BaseModel):
    id: int; name: str; value_cents: int; label: str          # label = scanner_label(name, value_cents)
```

## 5. `campaign_service` — shell

Gli errori sono quelli di `app/core/errors.py`; nessuna funzione logga testo dei clienti, IGSID o id dei commenti.

### Admin (UC1)

```python
def list_campaigns(session, merchant: Merchant) -> list[CampaignRow]
    # ordine D11: non archiviate prima, poi archiviate; dentro ciascun gruppo created_at decrescente, poi id decrescente
def create_campaign(session, merchant: Merchant, raw: object) -> CampaignRow
    # validate_campaign_input (400) → keyword_conflict con le non archiviate del negozio (409) → INSERT non archiviata,
    # contatori a 0, created_at = utc_now(). Niente scritto in caso di errore.
def get_campaign_for_merchant(session, merchant_id: int, campaign_id: int) -> Campaign
    # NotFoundError se la campagna non esiste o è di un altro negozio (stesso messaggio nei due casi)
def update_campaign(session, merchant: Merchant, campaign_id: int, raw: object) -> CampaignRow
    # 404 → 400 → 409 (conflitto «riservata» sempre; «in uso» solo se la campagna è non archiviata, esclusa se stessa)
    # → sostituisce TUTTI i campi modificabili; contatori, is_archived e created_at invariati (AC-05)
def archive_campaign(session, merchant: Merchant, campaign_id: int) -> CampaignRow     # 404; idempotente
def restore_campaign(session, merchant: Merchant, campaign_id: int) -> CampaignRow
    # 404; già non archiviata → nessun cambiamento; altrimenti keyword_conflict escludendo se stessa (409) → non archiviata
def delete_campaign(session, merchant: Merchant, campaign_id: int) -> None
    # 404 (anche al secondo «Elimina»); cancella la riga, contatori compresi
```
`merchant` arriva da `merchant_service.get_merchant_for_admin` (404 per un negozio inesistente).

### Pausa (UC2) — usata da `merchant_service`

```python
def archive_on_pause(session, merchant_id: int, before: ServiceState, after: ServiceState) -> int
    # se pause_begins(before, after): UPDATE campaign SET is_archived = true WHERE merchant_id = … AND NOT is_archived,
    # SENZA commit (lo fa il chiamante insieme al cambio di stato); ritorna quante ne ha archiviate (0 se nessuna pausa)
```
`merchant_service.set_merchant_state` e `merchant_service.update_merchant_as_admin` calcolano lo stato derivato prima
e dopo (`card_service.service_state`) e chiamano `archive_on_pause` **prima** di `merchant_crud.update_merchant` (che fa
il commit): archiviazione e cambio di stato stanno nello stesso commit. Se la modifica non va a buon fine (400, 409,
anche un 400 di `merchant_crud.update_merchant` dopo l'archiviazione) si fa `session.rollback()` prima di rilanciare:
nessuna campagna risulta archiviata. «Avvia» e «Riattiva» non ripristinano nulla.

### Webhook (UC3, UC4)

```python
class CampaignReply(BaseModel):
    campaign_id: int; text: str; exhausted: bool     # exhausted = testo «offerte terminate»

def register_request(session, campaign_id: int, channel: RequestChannel) -> Optional[int]
    # UN solo UPDATE atomico: incrementa dm_requests o comment_requests e ritorna dm_requests + comment_requests
    # DOPO l'incremento (UPDATE … RETURNING), poi commit. Non legge i contatori dall'oggetto in memoria.
    # Nessuna riga (campagna eliminata tra il riconoscimento e l'incremento) → None.
def handle_campaign_request(session, merchant: Merchant, text: Optional[str],
                            channel: RequestChannel) -> Optional[CampaignReply]
    # match_campaign tra le non archiviate del negozio (created_at decrescente) → None se nessuna;
    # negozio non ACTIVE → None, NIENTE contato (AC-12, AC-17);
    # altrimenti register_request (None → None: il webhook dà IGNORED)
    # → campaign_reply_text(promo_text, totale, request_limit, INSTAGRAM_CARD_KEYWORD).
    # Un MessageTooLongError del testo si propaga (la richiesta resta contata).
```

### Scanner (UC5)

```python
def scanner_campaigns(session, merchant: Merchant) -> list[ScannerCampaign]
    # non archiviate del negozio, created_at decrescente poi id decrescente; lista vuota se non ce ne sono

@dataclass
class ApplyResult:                      # dataclass come ScanResult di card_service (contiene un'istanza SQLModel)
    card: Card; applied_cents: int      # card ricaricata dopo gli UPDATE

def apply_campaign(session, merchant: Merchant, card_id: uuid.UUID, campaign_id: int) -> ApplyResult
    # 1. carta inesistente o di un altro negozio → NotFoundError
    # 2. campagna inesistente o di un altro negozio → NotFoundError (una campagna ARCHIVIATA si applica: AC-25)
    # 3. check_balance_change(merchant_state(merchant), value_cents ATTUALE) → ForbiddenError (403) prima di scrivere
    # 4. UPDATE card SET cashback_cents = cashback_cents + v; UPDATE campaign SET uses = uses + 1; UN commit
    # Non tocca tree points, MerchantPool, conversione né PointTransaction (AC-26). Con v = 0 conta solo l'utilizzo.
```

## 6. `instagram_service`

### Core (aggiunte)

```python
class InboundComment(BaseModel):
    event_id: str; account_id: str; comment_id: str; post_id: str; text: Optional[str] = None

def parse_comment_received(payload: dict, event_id: str) -> Optional[InboundComment]
    # None se payload["event"] != "comment.received"; InvalidInputError se mancano o sono vuoti
    # account.accountId, comment.id, comment.platformPostId (post_id). comment.text facoltativo.
    # Nessun altro campo letto (né author, né date, né isOwner).

COMMENT_CARD_INVITE = "Per ricevere la tua carta scrivici {keyword} qui in chat"   # senza punto finale
def build_comment_card_invite_text(card_keyword: str) -> str
    # COMMENT_CARD_INVITE.format(keyword=card_keyword); MessageTooLongError oltre INSTAGRAM_TEXT_MAX
```
`parse_message_received`, `detect_trigger` e il resto del core restano invariati. Una risposta a una storia è un
`message.received` con `metadata.storyReply` e il testo in `message.text`: si legge come un DM di testo.

### Shell: flusso dei DM (`message.received`), D2

Firma, dedup, pulizia degli eventi, account, `direction`, standby: **invariati**. Poi:
1. `detect_trigger(msg, INSTAGRAM_CARD_KEYWORD)` riconosce `CARTA` o la voce di menu → flusso di oggi, **invariato**
   (compreso `isFollower`).
2. Altrimenti, se il messaggio è un testo: `campaign_service.handle_campaign_request(session, merchant, msg.text,
   RequestChannel.DM)`; `None` → `IGNORED`. Un postback diverso dal nostro → `IGNORED`.
3. Fuori dalle 24 ore (`can_reply(msg.sent_at, now)` falso) → `OUT_OF_WINDOW`, nessun invio (la richiesta è già contata).
4. `zernio_service.send_text(http, creds, msg.conversation_id, reply.text, f"{event_id}:promo")` → `SENT` e
   `_record_send` (quota +1, attivazione). `isFollower` ignorato. Nessuna carta letta, creata o modificata.
5. Errori: `_handle_send_error` com'è (timeout → `SEND_UNCERTAIN` e quota +1; chiave rifiutata → `KEY_INVALID` e
   `SEND_FAILED`; conversazione di un'altra app → `STANDBY`; altro → `SEND_FAILED`). Un `MessageTooLongError` del
   testo → `SEND_FAILED` senza invio.

### Shell: flusso dei commenti (`comment.received`)

Stessa route, stesso negozio dal `hook_id`, stessa firma, stessa riga di dedup inserita per prima (un evento ripetuto
non invia e non conta: AC-14). Poi:
1. `parse_comment_received`; `InvalidInputError` o `account_id != merchant.zernio_account_id` → `IGNORED`.
2. `normalize_text(text) == normalize_text(INSTAGRAM_CARD_KEYWORD)` → risposta privata con
   `build_comment_card_invite_text(INSTAGRAM_CARD_KEYWORD)` **in ogni stato del negozio** (D7); nessun contatore di
   campagna, nessuna carta.
3. Altrimenti `handle_campaign_request(..., RequestChannel.COMMENT)`; `None` → `IGNORED`; altrimenti risposta privata con
   `reply.text`.
4. `zernio_service.send_private_reply(http, creds, comment.post_id, comment.comment_id, testo)` → `SENT` e
   `_record_send` (D5). Nessun controllo nostro dei 7 giorni, nessuna finestra di 24 ore.
5. Errori della risposta privata (mappatura propria, AC-18): `TIMEOUT` → `SEND_UNCERTAIN` e quota +1 senza attivare;
   `AUTH` → stato `KEY_INVALID` e `SEND_FAILED`; **ogni altro** tipo (compresi `NOT_THREAD_OWNER`, `NOT_FOLLOWER`,
   `QUOTA`, 4xx, 5xx) → `SEND_FAILED`. Mai un nuovo tentativo. Un `MessageTooLongError` del testo (invito o
   campagna) → `SEND_FAILED` senza invio (la richiesta di campagna resta contata).

Ogni altro valore di `event` → `IGNORED` (come oggi). Risposta HTTP sempre 200 per ogni esito; 401 firma, 404
`hook_id` (invariati). Log: id del negozio, id dell'evento, esito e, se c'è, id della campagna e canale (`dm` /
`commento`); **mai** testo, IGSID, id del commento o del post, chiavi, token.

## 7. `zernio_service`

```python
WEBHOOK_EVENTS = ["message.received", "comment.received"]   # build_webhook_body li manda alla registrazione (AC-20)

def build_private_reply_body(account_id: str, text: str) -> dict      # {"accountId": account_id, "message": text}
    # solo testo: mai "buttons", "quickReplies" o "template"
async def send_private_reply(http, creds: ZernioCredentials, post_id: str, comment_id: str, text: str) -> None
    # POST {ZERNIO_BASE_URL}/v1/inbox/comments/{post_id}/{comment_id}/private-reply (id con quote(safe=''))
    # timeout SEND_TIMEOUT (4 s); mai ritentata; NESSUN header Idempotency-Key; senza account → ZernioError(NOT_CONFIGURED)
    # prima di ogni chiamata. Errori: classify_error, tranne 502 con body.details.privateReplyOutcome == "unknown"
    # → ZernioError(TIMEOUT). 400 con details.privateReplyConsumed → BAD_REQUEST (da classify_error).
```
Da riprendere dall'archivio: `git show 621a278 -- app/services/zernio_service.py scripts/zernio_check.py
tests/test_zernio_client.py` (comando `send-private-reply` di `zernio_check` compreso). Piano B (decisione 13):
`WEBHOOK_EVENTS` torna a `["message.received"]` e il ramo dei commenti si spegne.

## 8. `merchant_service`

```python
def set_merchant_state(session, merchant, action: AdminAction) -> Merchant          # firma invariata
def update_merchant_as_admin(session, merchant, changes: dict) -> Merchant         # firma invariata
```
In più, entrambe: stato derivato prima e dopo, `campaign_service.archive_on_pause(...)` prima del commit (§5). Su
un negozio in attesa la pausa dalla dashboard resta 409 e non archivia nulla; un `PUT` che lascia il negozio «in
attesa» (es. `is_paused=true` su un non approvato) non archivia nulla; un `PUT` che lo porta in pausa sì (anche
impostando `is_approved=true` su un negozio con `is_paused` già vero).

## 9. HTTP

### Admin (`app/routes/admin.py`), regole di oggi della dashboard

Autenticazione con `require_admin_session` (GET) e `require_admin_action` (POST, PUT, DELETE: sessione o
`X-Admin-Key`, più `Origin`/`Referer` uguale a `Host` con il cookie → 403 altrimenti). Ogni risposta ha
`Cache-Control: no-store`, `X-Robots-Tag: noindex`, `Referrer-Policy: same-origin`. Errori: 400 campo non valido,
401 senza sessione, 403 origine, 404 negozio o campagna inesistenti o campagna di un altro negozio, 409 parola chiave.

| Metodo e percorso | Corpo | Risposta |
|---|---|---|
| `GET /admin/api/merchants/{merchant_id}/campaigns` | — | 200 `{"campaigns": [CampaignRow]}` |
| `POST /admin/api/merchants/{merchant_id}/campaigns` | `CampaignRequest` | 201 `CampaignRow` |
| `PUT /admin/api/merchants/{merchant_id}/campaigns/{campaign_id}` | `CampaignRequest` | 200 `CampaignRow` |
| `POST /admin/api/merchants/{merchant_id}/campaigns/{campaign_id}/archive` | — | 200 `CampaignRow` |
| `POST /admin/api/merchants/{merchant_id}/campaigns/{campaign_id}/restore` | — | 200 `CampaignRow` |
| `DELETE /admin/api/merchants/{merchant_id}/campaigns/{campaign_id}` | — | 200 `{"deleted": true}` |

`CampaignRequest` (in `app/schemas/campaign.py`): `name`, `keyword`, `promo_text`, `value_eur`, `request_limit`, tutti
`Any = None` (un 422 di FastAPI rimanderebbe indietro il corpo): la validazione è nel service (400). `PUT` vuole il
corpo completo, come la creazione. `CampaignRow` è il `response_model` (un campo non dichiarato non esce mai).

**Pagina** `admin/dashboard.html`: per ogni negozio un pulsante «Campagne» che apre la sezione delle sue campagne
(lista con i campi di AC-01 nell'ordine di D11, «nessun importo» per 0 e «nessun limite» per `null`, stato
«attiva» / «archiviata» / «ferma: negozio non attivo»), un form crea/modifica e i pulsanti «Archivia», «Ripristina»,
«Elimina» (quest'ultimo dopo `confirm()`). Il DOM si costruisce **solo** con `textContent` / `createElement`
(niente `innerHTML`, `insertAdjacentHTML`, `outerHTML`, `eval`, `| safe`): i test di oggi che lo vietano valgono
anche per la sezione nuova.

### Merchant

- `GET /merchant/card/{card_id}/manage` (invariata per autenticazione e 404): nel contesto in più `campaigns:
  list[ScannerCampaign]` (`scanner_campaigns`). Con almeno una campagna la pagina contiene un blocco con
  `id="campaigns-section"` e un `<button>` per campagna con `data-campaign-id="<id>"`, l'etichetta `label` come testo
  (autoescape di Jinja) e `disabled` se `value_cents > 0` e il negozio non è attivo (`can_add` falso). **Senza
  campagne la pagina non contiene `campaigns-section` ed è identica a oggi** (AC-21).
- Il bottone apre la **finestra di conferma già presente** nella pagina (sì/no); il nome della campagna entra nella
  finestra solo con `textContent`. Con «no» nessuna richiesta parte (AC-22); con «sì» parte la `POST` qui sotto e la
  pagina mostra cashback aggiornato e importo accreditato.
- `POST /api/merchant/card/{card_id}/campaigns/{campaign_id}/apply` (sessione merchant, nessun corpo) → 200
  `ApplyCampaignResponse` = `{"card": CardResponse, "applied_cashback": float}` (euro, da `applied_cents`).
  Errori: 401 senza sessione, 403 negozio non attivo e importo > 0, 404 carta o campagna inesistenti o di un altro
  negozio.

### Webhook

`POST /webhooks/zernio/{hook_id}`: route **invariata**; cambia solo `instagram_service.handle_webhook` (§6).

### Strumenti di collaudo (proposti dall'agente, nessun AC: approvati dal founder al gate 2)

- `python -m scripts.zernio_check send-private-reply --post-id ID --comment-id ID --text TESTO [--merchant-id N]`
  (ticket 04, dall'archivio `621a278`): una risposta privata reale, per il collaudo.
- `python -m scripts.replay_webhook --merchant-id N --comment TESTO [--post-id ID] [--comment-id ID] [--event-id ID]`
  (ticket 06): manda al server un evento `comment.received` firmato con il payload di §11 (account del negozio,
  `post-id` e `comment-id` finti di default) al posto del `message.received`; `--comment` esclude `--text` e
  `--postback`. Come oggi, il server invia davvero a Zernio.

## 10. Migrazione (`migrations/0001_campagne.sql`)

- **Una sola** `CREATE TABLE IF NOT EXISTS campaign (...)` più `CREATE INDEX IF NOT EXISTS ix_campaign_merchant_id ON
  campaign (merchant_id)`; nessun `ALTER`, `DROP`, `CREATE TYPE` (AC-28).
- Il testo delle colonne si ricava da `CreateTable(Campaign.__table__).compile(dialect=postgresql.dialect())`:
  `id SERIAL NOT NULL`, `VARCHAR(40)`/`VARCHAR(30)`/`VARCHAR(850)`, `INTEGER`, `BOOLEAN`, `TIMESTAMP WITH TIME ZONE`,
  `NOT NULL` come nel modello, `PRIMARY KEY (id)`, `FOREIGN KEY(merchant_id) REFERENCES merchant (id) ON DELETE
  CASCADE`; nessun `DEFAULT`.
- Commento in testa (italiano): cosa crea, che si applica a mano su Neon (prima `development`, poi `production` dopo
  il branch di backup, procedura in `deploy.md`) e che è idempotente.
- **Test** (`tests/test_migrations.py`): ogni definizione di colonna e di vincolo del DDL PostgreSQL generato dal
  modello compare nello script (spazi compattati, maiuscole ignorate); lo script contiene esattamente un `CREATE
  TABLE` e l'indice su `merchant_id`; nessuna delle parole `ALTER`, `DROP`, `CREATE TYPE`. Lo script **non** si
  esegue su SQLite (`SERIAL` lì non è un id automatico): la prova vera è su Neon `development` (ticket 06).

## 11. Dove si testa

I test usano le fixture di `tests/conftest.py`: `session`, `client`, `merchant`, `card`, `make_card`, `auth_client`,
`admin_headers`, `instagram_merchant` (negozio approvato e collegato, account `INSTAGRAM_ACCOUNT_ID`, `hook_id`
`INSTAGRAM_HOOK_ID`), `zernio_mock` (Zernio finto: registra le richieste, 200 di default, `queue(...)` per risposte o
eccezioni httpx), `signed_webhook(client, merchant, payload, event_id=...)`. Una campagna si crea con
`campaign_service.create_campaign(session, merchant, {...})` oppure direttamente con il modello `Campaign(...)` (§3).
La pausa e l'approvazione si impostano con `merchant_crud.update_merchant` o con le API admin.

Payload di riferimento (valori finti):

```json
{"id": "evt_c1", "event": "comment.received",
 "account": {"accountId": "<INSTAGRAM_ACCOUNT_ID>"},
 "comment": {"id": "c_1", "platformPostId": "17890000000000001", "postId": null, "text": "Natale!",
             "author": {"id": "igsid-commentatore", "username": "cliente"}}}
```
Risposta a una storia: il `message.received` di oggi con `"metadata": {"storyReply": {"storyId": "s_1",
"storyUrl": "https://..."}}` e il testo in `message.text`.
Zernio finto per la risposta privata: `POST …/v1/inbox/comments/{post_id}/{comment_id}/private-reply`, corpo
`{"accountId", "message"}`; 502 incerto = `{"details": {"privateReplyOutcome": "unknown"}}`; 400 consumata =
`{"details": {"privateReplyConsumed": true}}`.

| Slice | Criteri | Confine pubblico | Cosa cattura / cosa no |
|---|---|---|---|
| 01 | AC-03 (core), AC-27 | `tests/unit/`: `validate_campaign_input`, `keyword_conflict`, `match_campaign`, `is_within_limit`, testi, `scanner_label`, `campaign_status`, `pause_begins`, `normalize_text` | tutte le regole pure; non il DB |
| 01 | AC-28 | `tests/test_migrations.py` sullo script e sul modello | coerenza script ↔ modello; non l'esecuzione su Postgres (collaudo) |
| 01 | AC-29 | `tests/test_version.py` | — |
| 02 | AC-01..07 | endpoint `/admin/api/...` con `client` (cookie o `X-Admin-Key`, `Origin`) | autorizzazioni, codici, header, ordine, contatori invariati; il DOM solo con controlli statici del template |
| 02 | AC-08 | endpoint `pause`/`resume`/`approve` e `PUT /api/merchant/{id}` | archiviazione nello stesso commit, nessun ripristino; non la concorrenza |
| 03 | AC-09..13 | `signed_webhook` + `zernio_mock` + lettura della riga `campaign` | testo inviato, contatori, esiti, dedup, finestra, quota, log (caplog) |
| 03 | AC-11 (atomicità) | `campaign_service.register_request` | totali consecutivi con un oggetto `Campaign` **caricato prima** di un incremento fatto da un'altra sessione (un leggi-modifica-scrivi fallirebbe); SQLite non prova la concorrenza vera, che regge sull'`UPDATE … RETURNING` di Postgres |
| 04 | AC-14..19 | `signed_webhook` con `comment.received` + `zernio_mock` | percorso e corpo della risposta privata, esiti, contatori, quota |
| 04 | AC-20 | `zernio_service.build_webhook_body` e onboarding con `zernio_mock` | eventi registrati (i due test di oggi su `["message.received"]` si aggiornano) |
| 05 | AC-21, 24, 25 | `GET /merchant/card/{id}/manage` con `auth_client` | presenza/assenza di `campaigns-section`, bottoni `disabled`, 404 |
| 05 | AC-22 | **solo collaudo manuale** (browser); in pytest solo che la pagina contenga la finestra di conferma | il clic su «no» non è verificabile senza browser |
| 05 | AC-23, 24, 25, 26 | `POST /api/merchant/card/{id}/campaigns/{cid}/apply` e `campaign_service.apply_campaign` | saldi, contatori, 403/404, nessuna riga `PointTransaction`, pool invariato, `/c/<token>` identica |
| 06 | AC-30 | documenti; prova dello script su Neon `development` e collaudo su Instagram vero (founder) | comportamento reale di Zernio e Meta |

## 12. Cosa NON è congelato

Struttura interna dei moduli, nomi privati (`_…`), funzioni di `campaign_crud`, ordine delle operazioni dentro una
transazione, testo dei log e dei messaggi d'errore (tranne: nessun valore inviato e nessun segreto dentro),
markup e stile delle pagine oltre a `id="campaigns-section"`, `data-campaign-id` e `disabled`. Nessun test ci può
fare asserzioni.
