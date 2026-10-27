# Stato corrente

> Aggiorna questo file a inizio e fine sessione di lavoro, e dentro il commit di ogni ticket.
> Qui sta solo il lavoro **di adesso**. Item completati di una versione → riga nel changelog di `roadmap.md`;
> il registro dettagliato di una versione chiusa → `.agents/tickets/vX.Y.Z/STORICO.md`
> (v0.2.0: [STORICO.md](../tickets/v0.2.0/STORICO.md)).

## Dove siamo

**v0.3.0 — carta fedeltà via DM Instagram (Zernio)**, branch `feature/instagram-cards` (da `develop`, avviata il
2026-10-22). È la **prima release in produzione dopo v0.1.0**: assorbe v0.2.x (pool del negozio, auth merchant,
alberi), mai rilasciata. Dopo v0.3.0 l'app è funzionalmente quella descritta in AGENTS.md; la strada verso la
versione "a regime" è nella [roadmap](roadmap.md).

**Stato (2026-10-27)**: codice dei ticket 01-11 completo (874 test verdi). Il 2026-10-27 l'utente ha deciso di aggiungere
**tre ticket prima del pilota** (11 auth locale, 12 stato del servizio, 13 dashboard admin): in produzione i merchant non
potevano accedere e il founder deve poter approvare, mettere in pausa e reimpostare le password. Il vecchio ticket 11 è il
**14**. **Il ticket 11 è fatto** (i merchant possono registrarsi, accedere e cambiare la password con `AUTH_PROVIDER=local`);
restano 12 e 13. **Pronta al merge dopo** i ticket 12-13, il collaudo end-to-end del founder (procedura in
[deploy.md](../workflows/deploy.md), esiti in [zernio-notes.md](../architecture/zernio-notes.md)) e l'ok esplicito
dell'utente: nessun merge su `develop`/`main` e nessun tag prima. **v0.2.1 è assorbito da v0.3.0**: nessun merge
separato, `develop` oggi è alla v0.2.1 mai rilasciata e verrà superata dal merge di `feature/instagram-cards`.

Contesto di riferimento: decisioni in [AGENTS.md](../../AGENTS.md), vincoli Zernio/Meta con le fonti in
[zernio-notes.md](../architecture/zernio-notes.md), ticket in [tickets/v0.3.0](../tickets/v0.3.0/README.md).

### Ticket

| # | Ticket | Stato |
|---|---|---|
| 01 | Versione 0.3.0 | ✅ `505fc00` |
| 02 | Modelli, config ed errori | ✅ `865797d` |
| 03 | Cifratura AES-GCM, indice cieco IGSID, token del link | ✅ `161850d` (414 test) |
| 04 | Core dei messaggi: trigger, card, finestra 24 h, quota | ✅ 2026-10-23 `f4bb1b3` (459 test) |
| 05 | Client Zernio, `zernio_check`, **collaudo anticipato** | ✅ 2026-10-26: passi 1-2 del collaudo fatti (base URL `https://zernio.com/api` ok, `send-card` consegnata e corretta su mobile al profilo del founder); passo 3 (non follower) rimandato al collaudo del 07/11 |
| 06 | Webhook: dalla parola chiave alla card | ✅ 2026-10-23 (644 test) |
| 07 | Onboarding Instagram del merchant | ✅ codice 2026-10-26 (739 test); collaudo 2026-10-26 fatto per onboarding e DM da follower (timeout invio 4 s); non follower/Requests, ManyChat, menu e «Scollega» rimandati al ticket 11 |
| 08 | Pagina carta, QR, scan e PWA merchant | ✅ 2026-10-26 (793 test); prova manuale del founder riuscita (link `/c/<token>`, scan dalla PWA con aggiunta di punti, PWA installata, redirect al login) |
| 09 | Rimozione del vecchio flusso cliente (OTP, wallet, `/join`, `Customer`) | ✅ 2026-10-26 (744 test) |
| 10 | Seed, smoke test e script | ✅ 2026-10-26 (766 test) |
| 11 | Autenticazione dei merchant: provider `local` (registrazione, login, cambio password) | ✅ 2026-10-27 `d3a32d6` (874 test); smoke su SQLite usa-e-getta con `ENVIRONMENT=production` + `AUTH_PROVIDER=local`: registrazione, login, cambio password ok |
| 12 | Stato del servizio: approvazione, pausa e carta di prova | da fare (ticket scritto, scelte confermate dall'utente il 2026-10-27) |
| 13 | Dashboard admin | da fare (ticket scritto) |
| 14 | Documentazione, collaudo end-to-end e release (era l'11) | 🔶 2026-10-27: documentazione generale fatta (`65caf34`) e `replay_webhook --event-id` (`b40401a`, 767 test). Restano: collaudo Instagram del founder (si può fare subito), verifiche dei ticket 11-13, esiti in `zernio-notes.md`, ok al merge |

Suite di partenza: 360 test. I ticket 02-08 **aggiungono** il nuovo flusso accanto al vecchio (che continua a
funzionare); il vecchio si toglie tutto insieme nel 09.

Note sui ticket fatti:
- **03**: `app/core/crypto.py` (AES-256-GCM, HMAC dell'IGSID, token del link, `mask_secret`) e `validate_keys` all'avvio.
- **04**: `instagram_service` contiene per ora **solo il core** (payload `message.received`, firma, normalizzazione e
  trigger, card e testo di ripiego con limiti, finestra 24 h, stato quota); la shell arriva con i ticket 05-07.
  `merchant_service.validate_business_name`: nome del negozio ≤ 80 caratteri (è il titolo della card).

- **05**: `zernio_service` (core: `classify_error`, corpi delle richieste, `parse_accounts`, `ZernioCredentials` con
  `SecretStr`; shell: client httpx senza nuovi tentativi, timeout 4 s invio (era 3 s, alzato il 2026-10-26) / 10 s configurazione,
  `zernio_credentials_for` unico lettore dei campi cifrati) e `scripts/zernio_check`. Dalla spec: il menu si imposta con
  **PUT** `messenger-menu`, il webhook si elimina con `DELETE /v1/webhooks/settings?webhookId=`, e **`folder=requests`
  non funziona con Instagram Login** (400 `PLATFORM_LIMITATION`); nessun campo identifica il team Zernio, quindi
  `get_team_identity` → `None` (quota `account:<id>`). Dettagli in `zernio-notes.md`. Lo script ha bisogno di
  `ENCRYPTION_KEY`, `IGSID_HMAC_KEY`, `CARD_LINK_KEY` nell'ambiente (importa le settings).

- **06**: `instagram_service` ha ora anche la shell: `get_or_create_card`, `card_link_url`, `handle_webhook` (negozio da
  `hook_id` → firma → JSON → riga dell'evento per prima → pulizia a 7 giorni → trigger → `isFollower` → carta → invio),
  route `POST /webhooks/zernio/{hook_id}` in `app/routes/webhooks.py` e `scripts/replay_webhook` (`--follower si|no`
  in più rispetto al ticket). Esito nuovo `FOLLOW_REQUESTED`. Scelte non previste dal ticket:
  `build_follow_prompt_text` ha un terzo parametro `keyword` (il core non legge le settings); anche l'invito a seguire
  rispetta la finestra di 24 ore, conta per la quota e attiva un negozio `AWAITING_TEST_DM` (come card e ripiego);
  la mappatura degli errori è una sola per card, ripiego e invito (`AUTH` → `KEY_INVALID`, `NOT_THREAD_OWNER` → standby);
  un negozio con `hook_id` ma senza chiave/account risponde 404, senza secret 401; un errore di costruzione del
  messaggio (link non https, nome > 80 caratteri) dà `SEND_FAILED` e 200, non un 400 che farebbe ritentare Zernio.

- **07**: onboarding in `merchant_service` (come dice la mappa di AGENTS.md): core `validate_zernio_key`,
  `webhook_url_for`, `classify_persistent_menu`, `instagram_panel` (che, oltre alla firma del ticket, prende `keyword`,
  `send_limit` e `warn_percent` come argomenti nominati: il core non legge le settings); shell `save_zernio_key`, `list_zernio_accounts`,
  `connect_instagram_account`, `disconnect_instagram`, `read_instagram_panel`. `ExternalServiceError` → 502 nell'handler.
  5 endpoint in `/api/merchant/instagram...` e sezione "Instagram" nelle impostazioni (4 stati, server-side; il JS
  chiama solo l'API). Scelte non previste dal ticket: `zernio_credentials_for(..., require_account=False)` per la
  chiave salvata prima della scelta dell'account (resta l'unico punto che decifra; la chiave mascherata `…1234` si
  ricava da lì); `api_key` della richiesta è `Any` e si valida nel service (400, non il 422 di FastAPI che rimanda
  indietro il valore); `save_zernio_key` valida la nuova chiave **prima** di scollegare la vecchia configurazione;
  `connect_instagram_account` dà 409 se il negozio ha già un webhook (si scollega prima: «Scollega» c'è anche in
  `AWAITING_TEST_DM`, per il caso ManyChat) e controlla https/404/409 prima di ogni scrittura su Zernio;
  un errore sul menu (GET/PUT) **non** blocca il collegamento (`persistent_menu_set=False` + avviso); un menu che ha già
  la nostra voce `FIDELITREE_CARD` vale come impostato (nessun PUT). «Scollega» **non** rimuove il menu persistente
  (il ticket parla solo del webhook): resta su Instagram con un postback che non risponde più. Avvisi del pannello
  con `code` stabile (`menu`, `standby`, `key_invalid`, `quota`). Il vecchio test di `test_views` che vietava la parola
  «chiave» nelle impostazioni ora vieta solo `monthly`, `cap` ed `ecologi`.

- **08**: `instagram_service.get_card_by_link_token` (hash → `card_crud.get_card_by_link_token_hash`, poi il token
  presentato si confronta in tempo costante con quello **ricalcolato** da id e versione: la revoca vale anche con
  l'hash vecchio nel DB), `GET /c/{token}` e `GET /privacy` in `routes/consumer/views.py`, template `card` (QR = id
  della carta, niente PWA), `card_not_found` (404 uguale per token sconosciuto e revocato) e `privacy` (bozza: la nota
  è un commento Jinja, non arriva alla pagina). `app/core/logging_filters.py` (core `mask_sensitive_paths`, filtro che
  riscrive messaggio **e argomenti** del record, installato nel lifespan su `uvicorn.access`, idempotente). Le pagine
  HTML merchant usano `get_optional_merchant` (in `dependencies.py`) e senza sessione valida (anche con il cookie di
  un vecchio cliente, che prima dava 403) rimandano con 303 a `/merchant/login`; le API restano 401. Manifest
  `start_url` `/merchant/scanner` e `scope` `/merchant/`, `/sw.js` con `Service-Worker-Allowed: /merchant/`, partial
  PWA nelle 5 pagine merchant. Scelte non previste dal ticket: la pagina carta risponde con `Cache-Control: no-store`
  e `Referrer-Policy: no-referrer` (più `noindex`): il saldo cambia a ogni scan e l'URL è il segreto; il testo del 404
  cita `INSTAGRAM_CARD_KEYWORD` invece di «CARTA» fisso; il partial PWA è tolto anche dalle vecchie pagine cliente
  (wallet, join, login: spariscono nel 09) e `/card/{id}` condivide il template (ora con `scan_code`, niente
  `full_url`); lo scanner mostra «QR non riconosciuto» una sola volta ogni 3 s (la callback scatta ~15 volte al
  secondo); la fixture `auth_client` sovrascrive anche `get_optional_merchant` e `test_views` ha test con il cookie
  vero (la dependency non è coperta dagli override); `scripts/smoke_test_prod.py` controlla ora lo scope
  `/merchant/` (il resto dello script è del 10).

- **09**: tolto tutto il vecchio flusso cliente. Via `Customer`, `Card.customer_id` (e la sua `UniqueConstraint`),
  `customer_service`, `customer_crud`, `schemas/customer.py`, `consumer/auth.py` e `consumer/api.py` (restava vuoto: via
  anche dal `main`), `get_current_customer`/`get_optional_customer`, `request_otp`/`verify_otp`/`DEV_OTP_CODE` da
  `AuthProvider`, `card_crud.create_card`/`get_cards_by_customer`/`get_card_by_merchant_and_customer`, `JoinResponse` e
  `WalletEntryResponse`, i template `login`/`join`/`wallet`, le route `/customer/login`, `/customer/logout`,
  `/join/{id}`, `/wallet`, `/card/{id}` e `/api/customer/*`, `/api/card/{id}`. `Card.igsid_hash` e `link_token_hash`
  sono ora `str` obbligatori (NOT NULL: il costruttore di una tabella SQLModel non valida, l'errore è un
  `IntegrityError` al salvataggio). Scelte non previste dal ticket: il blocco «QR del negozio» `/join` delle
  impostazioni è tolto **per intero** (HTML, `join_path`, `qrcode.min.js` e tutto lo script QR: lasciando lo script
  `qrBox` sarebbe stato `null` e il form delle impostazioni avrebbe smesso di salvare); nessun sostituto, il QR
  `ig.me` resta a mano fuori dall'app. Fixture: `make_card(session, merchant, igsid="igsid-test-1")` in `conftest.py`
  su `instagram_service.get_or_create_card` (hash veri, quindi `/c/<token>` funziona nei test); `card` e
  `approved_merchants` lo usano, la fixture `customer` non c'è più. Test: `test_customer.py` e `test_customer_core.py`
  eliminati; il resto (WhatsApp, `/api/get-card` e `/download_card` 404) è in `tests/test_old_flow_removed.py`, che
  contiene anche le route rimosse (404), il grep case-insensitive su `app/` (`customer|wallet|\botp\b|/join`),
  le colonne NOT NULL, il flusso completo (webhook → `/c/<token>` → scan +60 → conversione e pool) e la
  cancellazione da parte del merchant con ricreazione a zero; i test di contenuto della pagina carta passati da
  `/card/{id}` a `/c/<token>` (nessun livello, oro, conversione disattivata) stanno in `test_card_page.py`.
  Modifica minima agli script (il resto è del 10): `seed_db` crea le carte con `get_or_create_card` da IGSID
  finti (`igsid-seed-anna`, `igsid-seed-luca`) e stampa solo credenziali merchant e id delle carte (niente token del
  link); `smoke_test_prod` controlla `/privacy` al posto di `/customer/login` e non verifica più `/join/{id}`.
  `create_all()`/`drop_all()` non conoscono più la tabella `customer`: su un DB vecchio resterebbe orfana (innocua;
  il DB di collaudo è usa-e-getta). Verificato l'avvio su un SQLite appena creato (lifespan, `/health`, `/privacy`,
  seed). Nota per il 10: la stampa del seed contiene `→`, che su una console Windows cp1252 dà
  `UnicodeEncodeError` (già così prima del 09; con `PYTHONIOENCODING=utf-8` funziona).

- **10**: script riallineati. `seed_db`: `main(argv)` con `--links`; di default stampa solo credenziali merchant e id
  delle carte, **con `--links` anche il link `/c/<token>`** (via `card_link_url`, quindi con `PUBLIC_BASE_URL`; solo
  stdout, mai nel logger): il ticket chiedeva di stamparli sempre, ma il token è un segreto, quindi è opt-in (`print_links`
  è ora `print_access`). Problema di encoding risolto alla radice: la stampa è solo ASCII (`->` al posto di `→`) e un
  test verifica che l'output si codifichi in cp1252. Gli IGSID finti restano `igsid-seed-anna`/`igsid-seed-luca`.
  `smoke_test_prod`: `EXPECTED_VERSION = "0.3.0"` (un test la confronta con `pyproject.toml`: al prossimo bump fallisce
  finché non si aggiorna), `/c/token-inesistente` 404, `POST /webhooks/zernio/hook-inesistente` 404 (risponde prima di
  firma, corpo e scritture: nessun invio a Zernio, nessuna riga evento), manifest con `start_url` `/merchant/scanner`,
  `/join/1` e `/wallet` 404, più i controlli di prima; resta senza scan né piantumazioni. `zernio_check`: `--merchant-id`
  (per sotto-comando, con `session` iniettabile) stampa lo stato (`read_instagram_panel`: stato, `@username`, chiave
  mascherata, invii del mese; mai il nome del negozio, per le emoji) e usa `zernio_credentials_for` come unico lettore
  (anche per «chiave non salvata»: si intercetta `NOT_CONFIGURED`, senza leggere il campo cifrato); `--account-id` è
  ora opzionale ovunque (si controlla dopo: obbligatorio senza `--merchant-id`, tranne `accounts`). Collaudo su SQLite
  usa-e-getta (porta 8011): `reset_db --force`, seed (idempotente), 4 link `/c/<token>` → 200, login del merchant del seed,
  scan +5 (10→15, pool 105→110), carta di un altro negozio 404, smoke test contro il server locale tutto OK.

- **11**: `app/core/auth.py` ha ora le sezioni `# --- Core puro ---` (hash `scrypt`, `validate_password` 8-128, `login_retry_after`) e `# --- Shell ---` (`LocalAuthProvider`, `LoginThrottle`, contratto `PasswordAdminProvider` con `set_password`, `change_password` e `delete_user`). Tabella `AuthCredential` (`password_hash` fuori dal `repr`). `login_merchant` prende `client_ip` e `now` e controlla il freno prima di verificare; `POST /api/merchant/me/password`; blocco «Cambia password» nelle impostazioni (solo se il provider è un `PasswordAdminProvider`); `TooManyAttemptsError` → 429 con `Retry-After`. **Scelte non previste dal ticket** (decise dall'agente, da rivedere): (1) il **Dockerfile** avvia uvicorn con `--proxy-headers --forwarded-allow-ips="*"`, altrimenti dietro il load balancer di DO il freno per IP sarebbe globale (5 errori di chiunque bloccano tutti); con `*` uvicorn si fida del primo `X-Forwarded-For`, che il client può falsificare, quindi **il freno per IP è un di più e quello per email è il vero freno**; verifica post-deploy in `deploy.md`; (2) `PasswordAdminProvider.delete_user` + compensazione in `register_merchant` (se la creazione del merchant fallisce la credenziale si elimina) + pulizia nel `DELETE` admin del merchant: senza, una credenziale orfana bloccherebbe l'email per sempre (409); (3) l'IP **non** si azzera al successo, solo l'email (altrimenti chi ha un account suo svuota il contatore); (4) il lifespan chiama `get_auth_provider()`: `dev` con `production` ora impedisce davvero l'avvio (prima falliva alla prima richiesta di auth, con un 500); (5) cookie `Secure` e `samesite=lax` con `ENVIRONMENT=production`; (6) `RegisterRequest` e `ChangePasswordRequest` senza campi obbligatori né tipi (`Any`): un 422 su un campo mancante rimanderebbe indietro il corpo, password comprese; la validazione è nel service (400), e `validate_registration`/`validate_business_name` accettano qualunque tipo (la registrazione con campo mancante passa da 422 a 400); (7) `change_password` valida la nuova password **prima** di verificare quella attuale (400 prima di 401) e ritorna il token riemesso; (8) password lunga oltre 128 al login = «Credenziali non valide» senza hash; (9) con `dev`/`supabase` `POST /me/password` risponde 400 e il blocco non compare; (10) fixture `autouse` `reset_login_throttle` e fixture `local_auth` in `conftest` (il provider usa la sessione di test: **non apre mai l'engine dell'app**; gli unici test che toccano il lifespan sostituiscono `app.main.engine` con SQLite in-memory). Limiti noti (in roadmap): freno in memoria per processo; `scrypt` blocca l'event loop ~60-130 ms a ogni login/registrazione; un login sbagliato mostra il JSON dell'errore (già così prima); chi conosce un'email può bloccarne il login per 15 minuti. `security.py` non è cambiato (il `ver` entra nel payload). Il debito «accesso dei merchant in produzione» è chiuso per la parte di auth; l'avviso in `deploy.md` resta finché non sono chiusi 12 e 13.

- **14** (ex 11, parte già fatta): verifica della documentazione contro il codice. Discrepanze corrette: il flusso del webhook in `overview.md`
  non citava `isFollower` (invito a seguire, `follow_requested`); l'ambito di quota oggi è sempre `account:<id>`
  (`get_team_identity` → `None`), non `zernio:<team>`; ordine del lifespan; `deploy.md` elencava ancora la tabella
  `customer` e la voce `seed_db` senza `--links`; `pre-release.md` testava ancora OTP, wallet e `/join`; il README
  descriveva il wallet. **Il passo 6 del collaudo (evento duplicato) non era fattibile**: `replay_webhook`
  generava un `event_id` nuovo a ogni esecuzione → aggiunto `--event-id` (con test). Segnalato a parte: in
  produzione i merchant non possono accedere (provider `dev` rifiutato con `ENVIRONMENT=production`, Supabase stub:
  avviso in `deploy.md`; **risolto dal ticket 11**), e il commento del `Dockerfile` cita ancora Railway (corretto nel ticket 11).

### Prossimo passo

1. ~~Ticket 05~~ fatto (passi 1-2 del collaudo; il passo 3, non follower, è nel collaudo del 11).
2. ~~Ticket 06~~ fatto. ~~Collaudo anticipato del 05~~ passi 1-2 fatti il 2026-10-26 (esiti sotto). Restano da verificare,
   nel collaudo del 07: card a un non follower, DM in Requests via webhook, ManyChat/standby. Se ManyChat risulta ancora
   collegato all'account, scollegarlo. Se l'esito contraddice le ipotesi di `zernio-notes.md`: **fermarsi e chiedere**.
3. ~~Ticket 07~~ codice fatto; collaudo manuale del 2026-10-26 (ngrok + SQLite usa-e-getta, `@oroscopo.kittysincula`)
   **fatto per i passi 1-2 con un follower**: onboarding, webhook, card consegnata, stato `ACTIVE` (esiti in
   `zernio-notes.md`, "Verificato nel collaudo del 07"). **Ancora da fare** (rimandati al collaudo finale, ticket 14):
   card/risposta a un **non follower** e DM in **Requests** via webhook (serve un profilo che non segue il negozio),
   `isFollower: null`, **ManyChat/standby**, tocco della voce di menu «🌳 La mia carta», «Scollega» da pannello.
4. ~~Ticket 08~~ fatto, prova manuale del founder riuscita il 2026-10-26.
5. ~~Ticket 09~~ fatto. ~~Ticket 10~~ fatto.
6. ~~Ticket 11~~ fatto. **Ticket 12-13** (nuovi, da fare in ordine, uno alla volta, con approvazione a fine ticket), poi **ticket 14**: documentazione generale fatta. **Collaudo end-to-end a cura del founder** (checklist passo-passo in
   `deploy.md`, «Collaudo end-to-end del flusso Instagram»). Da verificare e riportare in `zernio-notes.md`
   («Collaudo finale del ticket 11»): card a un non follower, DM in Requests via webhook, `isFollower` `null`,
   ManyChat/standby, tocco sulla voce di menu, «Scollega» da pannello, evento duplicato, log senza segreti, latenza
   (~30 s osservati; webhook ~11,5 s dopo `sentAt`). Poi: aggiornare gli esiti, rimuovere o riformulare le righe
   «non verificato» che il collaudo ha chiuso, marcare il 11 come ✅ e attendere l'ok al merge.

Esiti del collaudo del 05 (2026-10-26): `conversations` ha date in ritardo (la conversazione del founder risultava del
giorno prima: per trovarla si legge il mittente dei messaggi, non si fida dell'ordine); `--folder requests` dà 400
(limite già noto). Il founder ha notato una **latenza di circa 30 secondi** da qualche parte nel giro (non chiaro se
Zernio→webhook o consegna Instagram): **da misurare nel collaudo del 07** con timestamp di `sentAt`, arrivo del webhook e
consegna della card, perché in negozio il cliente aspetta al banco.
Primo giro del collaudo del 07 (2026-10-26, webhook reale via ngrok): DM `CARTA` inviato alle 14:39:57,7 UTC, webhook
arrivato alle 14:40:09,2 (**~11,5 s dopo `sentAt`**: Instagram → Zernio → noi), poi l'invio verso Zernio è scaduto a 3 s
pur avendo consegnato la card (esito `SEND_FAILED`, negozio rimasto `AWAITING_TEST_DM`). Misurata la sola chiamata di
invio (6 prove): 3,10 s a connessione nuova (come fa il webhook, un client per richiesta), poi 2,03 / 1,31 / 1,24 s, e
1,33 / 1,41 s a connessione aperta. **`SEND_TIMEOUT` portato da 3 a 4 s** (il webhook deve comunque rispondere entro
5 s). Il resto dei ~30 s non è nell'invio: webhook ~11,5 s + consegna Instagram/telefono. `/c/<token>` dà 404 fino al 08.
La chiave Zernio per gli script sta in `.env` come `ZERNIO_CHECK_API_KEY` (una sola variabile).

### Decisione del 2026-10-23: carta solo a chi segue
Il webhook (06) manda la card solo se `isFollower` è `true` o `null`; se `false` solo un testo di invito a seguire, senza
creare la carta. Dettagli in AGENTS.md e nel ticket 06 (nuovo esito `follow_requested`). Il comportamento con `null` si
rivede nel collaudo finale. QR "apri la chat": a mano dal founder (ticket 14).

### Da fare a mano (founder)

- Aggiungere al `.env` locale `ENCRYPTION_KEY`, `IGSID_HMAC_KEY`, `CARD_LINK_KEY` (l'app non parte senza; i test le
  impostano da soli). Non committare mai i valori.
- **Collaudo end-to-end del ticket 14** (passi 1-9 in `deploy.md`; i passi del flusso Instagram si possono fare subito, prima dei ticket 11-13). Servono un account Zernio gratuito, un account
  Instagram Business/Creator di prova e due profili personali (uno che segue il negozio, uno no). «Scollega» verifica
  solo il webhook: la voce di menu «🌳 La mia carta» resta su Instagram e, dopo lo scollegamento, toccarla non fa
  nulla (non è un bug, vedi nota 07). Il log `info` del webhook (`esito=...`) non si vede con `local_main.py` (solo i
  logger di uvicorn): la checklist usa un comando `python -c` con i log dell'app e l'ora, senza toccare il codice.
- Rimasti da v0.2.x e ancora validi per il rilascio di v0.3.0: collaudo di `ecologi_check` (chiave di test e reale) e
  di `close_period` in test mode; checklist `pre-release.md`, PWA merchant su telefono (HTTPS o tunnel).
- Dopo il collaudo: far verificare il testo di `/privacy` e decidere come far accedere i merchant pilota in produzione
  (vedi «Debito noto»).

## Debito noto

- **Accesso dei merchant in produzione**: con `AUTH_PROVIDER=local` (ticket 11, fatto) i merchant si registrano e accedono
  anche con `ENVIRONMENT=production`. Mancano ancora lo stato del servizio (12) e la dashboard admin con approvazione, pausa
  e reset password (13): **non fare il primo deploy prima**. Supabase più avanti, DB su Neon.
- Freno ai tentativi di login: in memoria, un solo processo; per IP best-effort (`X-Forwarded-For` falsificabile). Dopo il
  primo deploy fai la verifica del login in `deploy.md` («Primo deploy», passo 4).

- Merchant creato dall'admin senza `auth_user_id`: la sua email non si può registrare (409) e non può accedere (il reset
  dalla dashboard riguarda solo i registrati). Si risolve con Supabase.
- `create_all()` non migra: serve `scripts.reset_db` (nessun dato di produzione da preservare per ora).
- `reset_db`/`seed_db` agiscono sul `DATABASE_URL` del `.env` (oggi Neon): per il collaudo usare un SQLite usa-e-getta
  (`.agents/workflows/deploy.md`).
- Il testo di `/privacy` è una bozza da far verificare; DPA con i merchant ancora da scrivere (roadmap).

## Note per chi riprende il lavoro

- Regole di business e vincoli: AGENTS.md ("Contesto di business" e "Vincoli e trade-off").
- Convenzioni di codice (functional core / imperative shell, docstring italiane): AGENTS.md regole 3-5 e README dei ticket.
- I test girano offline (SQLite in-memory, Ecologi e Zernio mockati): `python -m pytest`; il core puro in `tests/unit/`.
- Si lavora un ticket alla volta; a fine ticket: test verdi, commit in italiano "... (ticket NN)", riepilogo di 3 righe
  e attesa dell'approvazione.
- La vecchia logica alberi/Telegram è in `feature/trees` (branch di archivio, non mergiare).
