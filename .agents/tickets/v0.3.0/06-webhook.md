# 06 — Webhook: dalla parola chiave alla card

## Obiettivo
`POST /webhooks/zernio/{hook_id}` riceve `message.received` e, quando riconosce il trigger:
1. crea o ritrova la carta del cliente per quel negozio;
2. risponde con **una** card (generic template) che contiene il link segreto;
3. ripiega su un testo con link solo se Meta rifiuta la card a un non follower.

Tutto in modo sincrono, idempotente e senza mai scrivere segreti nei log.

## Contesto
Decisioni del 2026-10-22, vincoli in [zernio-notes.md](../../architecture/zernio-notes.md):
- **Un webhook per negozio**: path con id opaco (`Merchant.webhook_hook_id`) e secret per negozio (cifrato). Dal path
  si sa quale secret usare **prima** di leggere il corpo; dopo la firma si controlla anche che `account.accountId` sia
  quello del negozio.
- **Tempi**: Zernio vuole un 2xx entro 5 s e ritenta fino a ~51 h; la consegna è at-least-once, quindi si deduplica su
  `X-Zernio-Event-Id`. La riga dell'evento si inserisce **per prima**: un duplicato riceve subito 200. Si conserva
  7 giorni.
- **Invio**: `Idempotency-Key` = id dell'evento; nessun nuovo tentativo. Su 5xx o timeout si logga, e il cliente può
  riscrivere la parola chiave.
- **Standby** (un'altra app possiede la conversazione): nessuna carta e nessun invio. Si registra
  `standby_detected_at` per l'avviso nel pannello (ticket 07).
- **Altri messaggi**: ignorati in silenzio. Il testo non si salva mai.
- **Quota**: dopo ogni invio riuscito il contatore del mese (`quota_scope` delle credenziali) cresce di 1, con un
  UPDATE atomico come `_increment_pool`. Nessun blocco nostro; `ZernioError(QUOTA)` si logga.
- **Attivazione**: un merchant in `AWAITING_TEST_DM` diventa `ACTIVE` al primo invio riuscito (card o ripiego).

- **Carta solo a chi segue** (decisione 2026-10-23, vedi AGENTS.md): `InboundMessage.is_follower` (da
  `message.sender.instagramProfile.isFollower`, `None` se assente). `False` → nessuna carta, solo il testo di invito
  (`build_follow_prompt_text(business_name, instagram_username, keyword)` nel core, con `instagram_username`
  facoltativo: senza handle si cita il nome del negozio; `keyword` lo passa la shell da `INSTAGRAM_CARD_KEYWORD`, il
  core non legge le settings) e esito nuovo `WebhookOutcome.FOLLOW_REQUESTED` (aggiungerlo all'enum e al
  modello dati del README). `True` e `None` → card (`None` da rivedere nel collaudo finale). Il controllo sta dopo
  `detect_trigger` e **prima** di `get_or_create_card`; l'invito conta come invio per la quota. Se anche l'invio del
  testo fallisce → `SEND_FAILED`. Test: follower, non follower (nessuna carta, un POST di testo), `null` (card), invito
  senza handle, nessun segreto nei log.

## Dipendenze
03, 04, 05.

## Modifiche
1. **`app/services/instagram_service.py`**, sezione `# --- Shell ---`:
   - `get_or_create_card(session, merchant, igsid) -> tuple[Card, bool]`:
     - cerca per `(merchant_id, igsid_blind_index(igsid))`;
     - alla creazione calcola `link_token_hash` da `card_link_token(card.id, 1)`;
     - un `IntegrityError` da richieste simultanee si gestisce come in `customer_service.join_merchant`.
   - `card_link_url(card) -> str`: `<PUBLIC_BASE_URL>/c/<token>`.
   - `handle_webhook(session, http, hook_id, raw_body, signature, event_id, now) -> WebhookOutcome`, in quest'ordine:
     1. merchant da `hook_id`, altrimenti `NotFoundError`;
     2. `verify_signature` con il secret da `zernio_credentials_for`, altrimenti `InvalidSignatureError`;
     3. parse JSON (JSON non valido → `IGNORED` con log);
     4. **insert** di `ProcessedWebhookEvent(event_id, merchant_id, received_at=now, outcome=RECEIVED)` e commit; un
        `IntegrityError` restituisce `IGNORED` senza altro lavoro. Una riga rimasta `RECEIVED` indica un'elaborazione
        interrotta: il retry non la ripete, per non rischiare un doppio invio;
     5. cancellazione degli eventi più vecchi di 7 giorni;
     6. `parse_message_received`: `None`, `accountId` diverso da `merchant.zernio_account_id` o messaggio non
        `incoming` → `IGNORED`;
     7. `standby` → aggiorna `standby_detected_at` → `STANDBY`;
     8. `detect_trigger`: `None` → `IGNORED`;
     9. `get_or_create_card`, poi aggiorna `zernio_conversation_id` e `last_inbound_at = msg.sent_at` e fa commit;
     10. `can_reply(msg.sent_at, now)` falso → `OUT_OF_WINDOW`;
     11. `send_card(..., idempotency_key=event_id)` → `SENT`;
     12. `ZernioError` con `NOT_FOLLOWER` → `send_text(build_fallback_text(...), idempotency_key=f"{event_id}:text")` →
         `FALLBACK_SENT`;
     13. `AUTH` → `merchant.instagram_status = KEY_INVALID` → `SEND_FAILED`;
     14. `NOT_THREAD_OWNER` → come lo standby → `STANDBY`;
     15. altri errori → `SEND_FAILED` con log (tipo dell'errore, id del merchant, id dell'evento);
     16. sugli invii riusciti: contatore +1, log warning quando si supera la soglia di avviso, `AWAITING_TEST_DM` →
         `ACTIVE`;
     17. salva `outcome` sull'evento.
   - I log contengono id del merchant, id dell'evento ed esito. **Mai** IGSID, token, link, chiave o testo del
     messaggio.
2. **`app/routes/webhooks.py`** (nuovo, router incluso in `app/main.py`):
   - `POST /webhooks/zernio/{hook_id}`;
   - legge il corpo **grezzo** (`await request.body()`) e gli header `X-Zernio-Signature` e `X-Zernio-Event-Id` (se
     manca, usa `payload.id`);
   - riceve `http` da `get_zernio_http` e chiama il service;
   - risposte: 200 `{"status": "ok"}` per ogni esito; 404 per `hook_id` sconosciuto; 401 per firma errata (handler
     globale). Nessun dettaglio dell'esito nella risposta.
3. **`scripts/replay_webhook.py`** (nuovo, collaudo locale), con `main(argv)`:
   ```
   python -m scripts.replay_webhook --merchant-id N --conversation-id ID
       [--text CARTA | --postback] [--sender-id finto-igsid] [--standby] [--hours-ago H]
       [--url http://127.0.0.1:8001]
   ```
   - costruisce un `message.received` realistico con un `event_id` nuovo, lo firma con il secret del merchant (dal DB
     del `.env`, via `zernio_credentials_for`) e lo invia al server;
   - stampa status ed esito;
   - avvisa che il server proverà un invio **vero** a Zernio sulla conversazione indicata.
4. **`tests/conftest.py`**:
   - fixture `instagram_merchant`: merchant con chiave, secret, `webhook_hook_id` e `zernio_account_id` cifrati e
     valorizzati;
   - fixture `zernio_mock`: `MockTransport` che registra le richieste, con risposte configurabili, installata con
     `dependency_overrides[get_zernio_http]`;
   - helper `signed_webhook(client, merchant, payload, event_id)`.

## File coinvolti
`app/services/instagram_service.py`, `app/routes/webhooks.py` (nuovo), `app/main.py`, `scripts/replay_webhook.py`
(nuovo), `tests/conftest.py`, `tests/test_webhook.py` (nuovo), `tests/test_scripts.py`, `AGENTS.md` (comando).

## Test da superare
(SQLite in-memory + `MockTransport`, nessuna rete.)
- **Flusso base**: "CARTA" → 200, una carta creata con `igsid_hash` e `link_token_hash`, **un** POST a Zernio con il
  corpo generic template e il bottone verso `<PUBLIC_BASE_URL>/c/<token>`. Il token ricalcolato corrisponde
  all'hash salvato.
- **Secondo messaggio "carta!"** dallo stesso IGSID con un nuovo evento: nessuna nuova carta, stesso link,
  `zernio_conversation_id` e `last_inbound_at` aggiornati.
- **Postback** `FIDELITREE_CARD` → stesso effetto della parola chiave.
- **Stesso IGSID su due negozi** → due carte distinte.
- **Duplicato**: stesso `X-Zernio-Event-Id` due volte → 200 entrambe le volte, un solo invio, una sola carta.
- **Firma**: firma errata → 401, nessuna carta, nessun invio, nessuna riga evento; firma assente → 401.
- **`hook_id`** sconosciuto → 404.
- **`accountId` diverso** da quello del negozio → 200, nessuna carta.
- **Ignorati senza invio**:
  - "ciao" → nessuna carta;
  - `direction: outgoing` → nessuna carta;
  - `event: message.sent` → nessuna carta;
  - JSON non valido ma firmato → 200.
- **Standby** → nessuna carta, nessun invio, `standby_detected_at` valorizzato.
- **Fuori finestra**: `sentAt` di 25 h prima → carta aggiornata, **nessun** invio, esito `OUT_OF_WINDOW`.
- **Errori di invio**:
  - Zernio 400 con `platformError` 2/1545133 → secondo POST con il testo di ripiego, esito `FALLBACK_SENT`,
    contatore +1;
  - Zernio 401 → `instagram_status == KEY_INVALID`, esito `SEND_FAILED`, risposta 200;
  - Zernio 500 o timeout → **un solo** tentativo, esito `SEND_FAILED`, risposta 200;
  - Zernio 409 `not_thread_owner` → esito `STANDBY`.
- **Contatore**: due invii riusciti nello stesso mese → `ZernioSendCounter(quota_scope=<scope delle credenziali>,
  period).sent == 2`. Due merchant con lo stesso `zernio_team_id` condividono il contatore.
- **Attivazione**: merchant `AWAITING_TEST_DM` + invio riuscito → `ACTIVE`; con standby resta `AWAITING_TEST_DM`.
- **Pulizia**: un evento di 8 giorni prima viene cancellato al webhook successivo; uno di 6 giorni no.
- **Nessun segreto nei log** (`caplog` sull'intero flusso, errori compresi): mancano IGSID, token, chiave Zernio,
  secret e testo del messaggio.
- **`replay_webhook`**: con un server finto (MockTransport) invia un corpo firmato che il core verifica come valido.

## Fuori scope
Configurazione del webhook su Zernio (07), pagina `/c/<token>` (08: fino ad allora il link esiste ma la pagina
risponde 404), trigger da commenti e storie (roadmap).

## Definition of Done
Suite verde; il webhook risponde in < 5 s anche con Zernio lento (timeout 3 s); nessun segreto nei log.
