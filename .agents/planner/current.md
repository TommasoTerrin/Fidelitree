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

**Stato (2026-10-27)**: codice dei ticket 01-13 completo (1049 test verdi). Il 2026-10-27 l'utente ha deciso di aggiungere
**tre ticket prima del pilota** (11 auth locale, 12 stato del servizio, 13 dashboard admin): in produzione i merchant non
potevano accedere e il founder deve poter approvare, mettere in pausa e reimpostare le password. Il vecchio ticket 11 è il
**14**. **I ticket 11 e 12 sono fatti** (i merchant possono registrarsi, accedere e cambiare la password con `AUTH_PROVIDER=local`;
lo stato in attesa / attivo / in pausa governa carta di prova e scanner; **il 13** dà al founder la dashboard `/admin`: approva, pausa, riattiva, reset password). **Pronta al merge dopo** il collaudo end-to-end del founder (ticket 14) (procedura in
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
| 07 | Onboarding Instagram del merchant | ✅ codice 2026-10-26 (739 test); collaudo 2026-10-26 fatto per onboarding e DM da follower (timeout invio 4 s); non follower/Requests, ManyChat, menu e «Scollega» rimandati al ticket 14 |
| 08 | Pagina carta, QR, scan e PWA merchant | ✅ 2026-10-26 (793 test); prova manuale del founder riuscita (link `/c/<token>`, scan dalla PWA con aggiunta di punti, PWA installata, redirect al login) |
| 09 | Rimozione del vecchio flusso cliente (OTP, wallet, `/join`, `Customer`) | ✅ 2026-10-26 (744 test) |
| 10 | Seed, smoke test e script | ✅ 2026-10-26 (766 test) |
| 11 | Autenticazione dei merchant: provider `local` (registrazione, login, cambio password) | ✅ 2026-10-27 `d3a32d6` + `9ae5b3e` (freno solo per email) (878 test); smoke su SQLite usa-e-getta con `ENVIRONMENT=production` + `AUTH_PROVIDER=local`: registrazione, login, cambio password ok |
| 12 | Stato del servizio: approvazione, pausa e carta di prova | ✅ 2026-10-27 `f5df96c` + `86f00dd` (936 test); avvio verificato su SQLite usa-e-getta (reset, seed, colonne `is_paused` e `created_at`) |
| 13 | Dashboard admin | ✅ 2026-10-27 `4081bcd` (+ `897ee7e`, 1049 test); verificato su SQLite usa-e-getta con `AUTH_PROVIDER=local` e un processo vero: login, lista, approva, reset, `smoke_test_prod` ok |
| 14 | Documentazione, collaudo end-to-end e release (era l'11) | 🔶 2026-10-27: documentazione generale fatta (`65caf34`) e `replay_webhook --event-id` (`b40401a`, 767 test). 2026-10-27 seconda sessione: documentazione dei ticket 11-13 riverificata contro il codice (commit `f52379f`, solo commenti) e passi 9-11 del collaudo verificati via HTTP su un processo vero (nota sotto). Restano **a cura del founder**: collaudo Instagram (passi 1-8), prova nel browser, esiti in `zernio-notes.md`, ok al merge |

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

- **11**: `app/core/auth.py` ha ora le sezioni `# --- Core puro ---` (hash `scrypt`, `validate_password` 8-128, `login_retry_after`) e `# --- Shell ---` (`LocalAuthProvider`, `LoginThrottle`, contratto `PasswordAdminProvider` con `set_password`, `change_password` e `delete_user`). Tabella `AuthCredential` (`password_hash` fuori dal `repr`). `login_merchant` prende `client_ip` e `now` e controlla il freno prima di verificare; `POST /api/merchant/me/password`; blocco «Cambia password» nelle impostazioni (solo se il provider è un `PasswordAdminProvider`); `TooManyAttemptsError` → 429 con `Retry-After`. **Scelte non previste dal ticket** (decise dall'agente, da rivedere): (1) **freno solo per email, senza IP** (deciso con l'utente a fine ticket: prima era per email e per IP con `--proxy-headers` nel Dockerfile; tolti entrambi perché dietro il proxy di DO l'IP sarebbe globale o falsificabile): dal 3° errore il messaggio avvisa («Attenzione: dopo 5 errori l'accesso si ferma per 15 minuti»), al 5° «Accesso sospeso», dal 6° 429 con invito a chiedere il reset al founder; il `Dockerfile` è com'era (corretto solo il commento su Railway); `login_merchant` non ha più `client_ip`; (2) `PasswordAdminProvider.delete_user` + compensazione in `register_merchant` (se la creazione del merchant fallisce la credenziale si elimina) + pulizia nel `DELETE` admin del merchant: senza, una credenziale orfana bloccherebbe l'email per sempre (409); (3) il successo azzera il contatore dell'email; (4) il lifespan chiama `get_auth_provider()`: `dev` con `production` ora impedisce davvero l'avvio (prima falliva alla prima richiesta di auth, con un 500); (5) cookie `Secure` e `samesite=lax` con `ENVIRONMENT=production`; (6) `RegisterRequest` e `ChangePasswordRequest` senza campi obbligatori né tipi (`Any`): un 422 su un campo mancante rimanderebbe indietro il corpo, password comprese; la validazione è nel service (400), e `validate_registration`/`validate_business_name` accettano qualunque tipo (la registrazione con campo mancante passa da 422 a 400); (7) `change_password` valida la nuova password **prima** di verificare quella attuale (400 prima di 401) e ritorna il token riemesso; (8) password lunga oltre 128 al login = «Credenziali non valide» senza hash; (9) con `dev`/`supabase` `POST /me/password` risponde 400 e il blocco non compare; (10) fixture `autouse` `reset_login_throttle` e fixture `local_auth` in `conftest` (il provider usa la sessione di test: **non apre mai l'engine dell'app**; gli unici test che toccano il lifespan sostituiscono `app.main.engine` con SQLite in-memory). Limiti noti (in roadmap): freno in memoria per processo; `scrypt` blocca l'event loop ~60-130 ms a ogni login/registrazione; un login sbagliato mostra il JSON dell'errore (già così prima); chi conosce un'email può bloccarne il login per 15 minuti. `security.py` non è cambiato (il `ver` entra nel payload). Il debito «accesso dei merchant in produzione» è chiuso per la parte di auth; l'avviso in `deploy.md` resta finché non sono chiusi 12 e 13.

- **12**: `Merchant.is_paused` (default `False`) e `Merchant.created_at` (UTC, per la lista admin del 13). Stato derivato, nessun enum
  in DB: `ServiceState` in `app/core/enums.py`; `service_state`, `can_add_balance`, `can_remove_balance` e `check_balance_change`
  (`ForbiddenError` → 403) nel core di `card_service`; `merchant_state(merchant)` nella shell. **Scelte non previste dal ticket**:
  (1) il core sta in `card_service` e non in `merchant_service` come dice il ticket: `merchant_service` importa `instagram_service`
  in cima al core, quindi il webhook non può importarlo senza un ciclo (il ticket ammette `card_service`, che non importa nessuno
  dei due; con `merchant_service` l'ordine di import avrebbe deciso se l'app parte); (2) la conversione si salta **per stato**, non per
  segno del delta: un negozio non attivo può abbassare la soglia dalle impostazioni e un `-1` farebbe scattare una conversione, cioè un
  accredito di cashback (test dedicato); (3) per il cashback il segno si guarda sui **centesimi** dopo `euro_to_cents` (0,004 € = 0, non è
  un'aggiunta); il controllo viene prima di ogni scrittura e dopo la verifica della proprietà della carta (carta altrui = 404 prima di 403);
  (4) webhook in attesa: `_reply_with_card` cerca la carta **senza crearla** con `card_crud.get_card_by_igsid_hash` (l'indice cieco si calcola
  solo in memoria); se la carta manca l'URL è `demo_card_url()` (`<PUBLIC_BASE_URL>/carta-di-prova`, anche per il testo di ripiego 2/1545133);
  fuori finestra di 24 h un cliente nuovo non salva nulla; il resto (contatore, `AWAITING_TEST_DM` → `ACTIVE`, esiti) è invariato; la funzione
  si chiama `demo_card_url` e non `test_card_url`, perché importata in un test pytest la raccoglierebbe come test; (5) `/carta-di-prova` è una
  pagina statica (nessuna dipendenza da sessione o DB), con gli stessi header della pagina carta (no-store, no-referrer) più `noindex`; il nome
  del negozio non compare (titolo «Il tuo negozio»), il «QR» è un riquadro segnaposto: niente `qrcode.min.js`, niente `<img>`/`<canvas>`;
  (6) banner come partial `partials/service_banner.html` (macro con variante scura per lo scanner), nelle tre pagine merchant; i pulsanti
  «AGGIUNGI TREE POINTS» e «AGGIUNGI CASHBACK» hanno `disabled` (con id `btn-add-tree`/`btn-cashback`), «TOGLI…» e «USA INTERO CASHBACK» restano
  attivi; il badge «Approvato ✅» delle impostazioni compare solo se attivo e il vecchio testo «Puoi usare le carte fin da subito» è tolto
  (anche dalla pagina di registrazione); (7) **test riscritto**: `test_merchant_non_approvato_puo_lavorare` (ticket 11) descriveva il vecchio
  «lavora subito» → ora `test_merchant_non_approvato_vede_lo_scanner_ma_puo_solo_togliere` (scanner 200, aggiunta 403); (8) **`is_paused` non è
  esposto dall'API admin** (`MerchantUpdateRequest`, `/approve` invariato): spetta al ticket 13; finora la pausa si imposta solo dal DB (e nei
  test con `merchant_crud.update_merchant`), e `POST /{id}/approve` non toglie la pausa (lo farà l'azione della dashboard); (9) la pagina carta
  `/c/<token>` è verificata **a byte** identica nei tre stati; (10) tra i test, `pool_mismatches` resta vuoto dopo una rimozione in pausa e
  `close_period` include un negozio approvato in pausa ed esclude uno in attesa; (11) smoke test: `/carta-di-prova` 200 HTML; `seed_db` invariato
  (approvati e attivi). Discrepanze della documentazione corrette: `deploy.md` diceva che `create_all` aggiunge le colonne nuove (falso, verificato:
  crea solo le tabelle mancanti; contraddiceva anche la nota di «Schema v0.3.0»); `pre-release.md` chiedeva di verificare che un merchant non
  approvato «lavori»; «lavora subito» in `overview.md`, `merchant_service`, `routes/merchant/auth.py`, `settings.html` e pagina di registrazione.
  Limite noto: `ZernioSendCounter` (docstring in `models.py`) cita ancora l'ambito `zernio:<team_id>`, oggi sempre `account:<id>` (non toccato).
  **Il passo 2 del collaudo** (`deploy.md`) ora richiede un passo 2b: approvare il negozio (API admin) prima di aspettarsi `/c/<token>`.
- **13**: dashboard admin `/admin` (nessuna colonna nuova nel DB). `app/routes/admin.py` (login, logout, pagina, `GET /admin/api/merchants`,
  `POST .../approve|pause|resume|reset-password`), template `admin/login.html` e `admin/dashboard.html` (Tailwind + JS vanilla), `app/core/security.py`
  (token `role=admin` di 12 ore, `create_jwt_token(expires_delta=)`, `request_origin_allowed`), `app/core/dependencies.py` (`admin_auth_method`,
  `require_admin_session`, `require_same_origin`, `require_admin_action`, cookie), `app/core/auth.py` (`admin_key_matches`), `merchant_service`
  (`login_admin`, `list_admin_merchants`, `set_merchant_state`, `approve_merchant`, `reset_merchant_password`; core: `AdminAction`, `apply_admin_action`,
  `generate_temporary_password`, `AdminMerchantRow`). **Scelte non previste dal ticket**: (1) **Origin**: confronto il netloc di `Origin` (o `Referer`) con l'header
  `Host`, senza guardare lo schema (dietro il proxy di DO sarebbe ambiguo); vale per ogni POST con sessione a cookie **e per il POST di login**; mancante,
  estraneo o `null` → 403, e si controlla prima del freno (un POST cross-site non consuma tentativi); con `X-Admin-Key` **corretto** non serve (un header errato
  con cookie valido è rifiutato, 401, senza ripiego sul cookie); (2) **`Referrer-Policy: same-origin`** sulle risposte admin, non `no-referrer` come la pagina carta:
  con `no-referrer` il browser manda `Origin: null` sui POST e ogni azione darebbe 403 mentre i test (che impostano `Origin` a mano) resterebbero verdi;
  più `Cache-Control: no-store` e `X-Robots-Tag: noindex`; (3) **chiave admin vuota = accesso chiuso**: `.env.example` lascia `ADMIN_SECRET_KEY=` e `Settings` accetta
  `""`, quindi `compare_digest("", "")` avrebbe fatto entrare una password vuota; `admin_key_matches` fallisce chiuso (anche per l'header); (4) il token admin ha solo
  `role=admin` (nessun `sub`/`email`/`ver`), quindi i provider dei merchant lo rifiutano e un token merchant (stessa `JWT_SECRET_KEY`) non vale come admin: il claim si
  controlla con uguaglianza stretta, test nei due versi; cookie `admin_session` con `Path=/admin` e logout con lo stesso `Path` (senza, il browser lo tiene); (5) **freno**:
  la stessa istanza `login_throttle` con chiave fissa `admin`, messaggi propri (`admin_login_failure_message`) e un `suffix` opzionale in `TooManyAttemptsError` /
  `LoginThrottle.check` (quello di default invita a chiedere il reset al founder, che per l'admin non ha senso: il 429 admin dice di usare `X-Admin-Key`); il contatore è
  globale (chiunque può fermare il form per 15 minuti, il ripiego è l'header, senza freno) e il successo lo azzera; (6) **il reset azzera anche il freno del login di quell'email**
  (`login_throttle_key`): il 429 del merchant dice «chiedi al founder il reset» e senza questo la password temporanea sarebbe inutilizzabile fino a 15 minuti; (7) **transizioni**:
  `approve` da ogni stato imposta `is_approved` e toglie la pausa; `pause` e `resume` valgono solo per un negozio approvato (409 su uno in attesa, perché la pausa non conta
  lì e l'azione sarebbe ambigua); ripetere un'azione è un no-op con 200; (8) **API admin vecchia**: `POST /api/merchant/{id}/approve` ora passa da `approve_merchant` (toglie la pausa),
  `is_paused` è in `MerchantUpdateRequest` e in `MerchantResponse` (quindi anche in `GET /api/merchant/me`: il merchant vede il proprio flag); `require_admin_key` dopo l'approvazione (`897ee7e`) usa `admin_key_matches`
  (tempo costante, chiave vuota = chiusa; sempre 403); (9) **reset**: password temporanea di 12 caratteri da un alfabeto di 54 senza `0 O 1 l I` con `secrets.choice` (la `choice` è iniettabile: il core resta
  deterministico nei test), `set_password` poi `throttle.clear`; 409 senza `auth_user_id` o con la credenziale mancante (`NotFoundError` del provider tradotto), 400 con un
  provider senza password; la risposta (`AdminResetPasswordResponse`, `temporary_password` con `repr=False`) ha un `response_model` fisso e `no-store`; (10) **la lista** usa due
  query raggruppate (`card_crud.count_cards_by_merchant`, `tree_service.pool_points_by_merchant`) più una per i merchant, non una per riga (un test conta le query); risposta con
  `response_model` (un campo non dichiarato non esce mai) e test sui **valori** dei segreti (chiave cifrata, secret, `hook_id`, hash, id del provider, `ADMIN_SECRET_KEY`,
  `JWT_SECRET_KEY`), non solo sui nomi dei campi; (11) **XSS**: i nomi li scrivono i merchant, quindi la pagina usa solo `textContent` (un test vieta `innerHTML`, `eval`,
  `| safe`...) e il server non stampa nessun dato nell'HTML; (12) il form di login usa `fetch` per mostrare 401 e 429 nella pagina (senza JS resta il POST classico) e va su `/admin`
  solo se il redirect ha portato lì (cookie accettato); (13) **Modifica A**: «Attivo ✅» → «Collegato con Zernio ✅» nelle impostazioni e «la funzione è attiva» → «il collegamento con
  Zernio è completo» (stesso stato, riga 82); nella dashboard lo stesso stato si chiama «Collegato con Zernio» (il ticket diceva «attivo»: accanto alla colonna dello stato del
  servizio confonderebbe); `InstagramStatus.ACTIVE` e `data-state="active"` invariati; nessun test dipendeva dai vecchi testi (verificato), ne ho aggiunti due;
  (14) **Modifica B**: `ZERNIO_CHECK_API_KEY: SecretStr = SecretStr("")` in `Settings` (pydantic-settings la legge dall'ambiente **o dal `.env`**; nessuna dipendenza nuova, il `.env` non
  si legge a mano, la chiave non si stampa), `scripts/zernio_check._read_key` la legge da `settings` a ogni chiamata; **test riscritti**: quelli che usavano `monkeypatch.setenv/delenv`
  ora impostano `settings.ZERNIO_CHECK_API_KEY`, e due test nuovi usano un `.env` temporaneo con valori finti; (15) **`tests/conftest.py`**: `ADMIN_SECRET_KEY`, `JWT_SECRET_KEY` e
  `ZERNIO_CHECK_API_KEY` si impostano nell'ambiente prima di importare l'app (le env var vincono sul `.env`): ora `ZERNIO_CHECK_API_KEY` è un campo di `Settings`, quindi
  la chiave vera del `.env` entrerebbe nel processo di test e un'asserzione fallita potrebbe stamparla; vale anche per i due segreti dell'admin. Fuori scope rispettato (nessuna creazione /
  eliminazione / modifica dei dati del merchant, link di invito, più admin, audit log, statistiche).
- **14** (ex 11, parte già fatta): verifica della documentazione contro il codice. Discrepanze corrette: il flusso del webhook in `overview.md`
  non citava `isFollower` (invito a seguire, `follow_requested`); l'ambito di quota oggi è sempre `account:<id>`
  (`get_team_identity` → `None`), non `zernio:<team>`; ordine del lifespan; `deploy.md` elencava ancora la tabella
  `customer` e la voce `seed_db` senza `--links`; `pre-release.md` testava ancora OTP, wallet e `/join`; il README
  descriveva il wallet. **Il passo 6 del collaudo (evento duplicato) non era fattibile**: `replay_webhook`
  generava un `event_id` nuovo a ogni esecuzione → aggiunto `--event-id` (con test). Segnalato a parte: in
  produzione i merchant non possono accedere (provider `dev` rifiutato con `ENVIRONMENT=production`, Supabase stub:
  avviso in `deploy.md`; **risolto dal ticket 11**), e il commento del `Dockerfile` cita ancora Railway (corretto nel ticket 11).
- **14, seconda sessione** (verifica senza Instagram): letti i documenti contro il codice (env var di `.env.example` e `Settings` 1:1, endpoint, modello dati, cifre della dashboard, lifespan, smoke test): nessuna discrepanza sostanziale; corretti solo due commenti stantii (router in `main.py`, `ZernioSendCounter`/`zernio_team_id` che citavano ancora l'ambito `zernio:<team_id>`). **Passi 9-11 del collaudo verificati via HTTP** (script usa-e-getta, processo uvicorn vero, SQLite fuori dal repo, `AUTH_PROVIDER=local`, `ENVIRONMENT=development`, chiavi casuali, `.env` non letto): registrazione; in attesa → scanner 200 ma aggiunta punti e cashback 403; admin: login (password errata 401, `Origin` estraneo 403, POST senza `Origin` 403), lista senza segreti, `pause` su in attesa 409, Avvia, +60 punti con conversione, pausa (aggiunta 403, rimozione ok), riattiva; reset password (12 caratteri, no-store, sessione aperta decaduta, vecchia password 401, temporanea ok, cambio password); freno merchant (5×401 poi 429, a freno attivo anche la password giusta dà 429, il reset sblocca subito) e freno admin (5×401 poi 429, `X-Admin-Key` funziona); log del server (49 righe, app a livello info): nessuna password, temporanea, `ADMIN_SECRET_KEY`, `JWT_SECRET_KEY`, chiavi, hash `scrypt$`, IGSID né token del link; compare solo `GET /c/***`. **Non verificato qui**: browser vero (dashboard, PWA, cookie `Secure` con https), qualunque cosa con Instagram/Zernio, Neon, la pagina carta identica a byte nei tre stati (coperta dal test del ticket 12), `/carta-di-prova` via webhook reale.

### Prossimo passo

1. ~~Ticket 05~~ fatto (passi 1-2 del collaudo; il passo 3, non follower, è nel collaudo del 14).
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
**Piano unificato (deciso il 2026-10-28)**: documentazione e codice dei ticket 01-14 completi. Un solo **collaudo finale** a cura del founder (passi 1-11
di `deploy.md`, esiti nella tabella di `zernio-notes.md`). Se va tutto bene: si compila la tabella, si chiudono **insieme** i ticket aperti (05 e 07 con le
voci rimandate, 14), si spunta `pre-release.md` (parte locale), poi ok esplicito dell'utente → merge su `develop`. Se un esito contraddice AGENTS.md: fermarsi
e chiedere. Dopo il merge: `main` e produzione secondo «Primo deploy di v0.3.0».

6. ~~Ticket 11~~ fatto. ~~Ticket 12~~ fatto. ~~Ticket 13~~ fatto (attende l'approvazione dell'utente), poi **ticket 14**: documentazione generale fatta. **Collaudo end-to-end a cura del founder** (checklist passo-passo in
   `deploy.md`, «Collaudo end-to-end del flusso Instagram»). Da verificare e riportare in `zernio-notes.md`
   («Collaudo finale del ticket 14»): card a un non follower, DM in Requests via webhook, `isFollower` `null`,
   ManyChat/standby, tocco sulla voce di menu, «Scollega» da pannello, evento duplicato, log senza segreti, latenza
   (~30 s osservati; webhook ~11,5 s dopo `sentAt`). Poi: aggiornare gli esiti, rimuovere o riformulare le righe
   «non verificato» che il collaudo ha chiuso, marcare il 14 come ✅ e attendere l'ok al merge.

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

- **Accesso dei merchant in produzione**: chiuso. Con `AUTH_PROVIDER=local` (ticket 11) i merchant si registrano e accedono anche con
  `ENVIRONMENT=production`, lo stato del servizio (12) governa carta di prova e scanner e la dashboard `/admin` (13) permette di avviare,
  mettere in pausa, riattivare e reimpostare le password. Il primo deploy aspetta solo il collaudo (14) e l'ok al merge. Supabase più avanti, DB su Neon.
- **Punto aperto: freno ai tentativi in memoria** (solo per email). Giusto con un solo processo (oggi); si azzera al riavvio e
  con più processi/container il limite si moltiplica (5 × N): spostarlo su DB **prima** di scalare (dettagli in `roadmap.md`).
  Dopo il primo deploy fai la verifica del login in `deploy.md` («Primo deploy», passi 4 e 4b).
- **Punto aperto: il freno del login admin** è lo stesso contatore in memoria, con una chiave sola (`admin`): chiunque può fermare il form
  di `/admin` per 15 minuti; ripiego `X-Admin-Key` (nessun freno). Si risolve insieme al freno su DB.

- Merchant creato dall'admin senza `auth_user_id`: la sua email non si può registrare (409) e non può accedere (il reset
  dalla dashboard riguarda solo i registrati: il pulsante è grigio e l'API risponde 409). Si risolve con Supabase.
- `create_all()` non migra: serve `scripts.reset_db` (nessun dato di produzione da preservare per ora). Con il ticket 12 la tabella `merchant` ha due colonne nuove (`is_paused`, `created_at`): ogni DB già creato (Neon di sviluppo, `collaudo*.db`) va resettato.
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
