# Architettura Fidelitree (v0.3.0)

## Vista d'insieme

Monolite FastAPI con rendering server-side (Jinja2) e API JSON. Un solo processo, un solo database.
La carta del cliente nasce da un **DM Instagram** al negozio, ricevuto tramite **Zernio** (webhook) e risposto con una
card che contiene un link segreto. Il cliente non ha autenticazione. La **PWA** è solo del merchant (scanner e gestione).

```
Cliente (Instagram) ── DM "CARTA" / menu ──► Instagram ──► Zernio ── webhook firmato ──┐
        ▲                                                                              │
        └──── card "Apri la carta" ◄── Zernio ◄── POST messages (chiave del merchant) ─┤
                                                                                       ▼
Browser cliente: /c/<token> (pagina carta + QR),         FastAPI (app/main.py)
                 /carta-di-prova (negozio in attesa)
Browser merchant: PWA /merchant/* (scanner, gestione)    routes → services (core puro + shell) → db_crud
Browser del founder: /admin (dashboard: approva, pausa, reset password)
                                                          ▼
                                       PostgreSQL (Neon oggi, Supabase più avanti)

Script a mano: reset_db · seed_db · close_period · ecologi_check · zernio_check · replay_webhook · smoke_test_prod
   └─ close_period ──► Ecologi Impact API (chiave unica di piattaforma)
```

## Modello dati

Definito in `app/models/models.py`; lo schema nasce da `create_all()` all'avvio.
Denaro in **centesimi interi** (`*_cents`), timestamp **UTC aware**, mese = `period` `'YYYY-MM'` (UTC) fissato in scrittura.

```
Merchant 1 ──< Card >── (nessun Customer: il cliente è l'indice cieco del suo IGSID per quel negozio)
   │  zernio_api_key_enc, webhook_secret_enc (AES-GCM)      igsid_hash  UNIQUE(merchant_id, igsid_hash)
   │  zernio_account_id, webhook_hook_id, instagram_status  link_token_hash, link_version
   │                                                         zernio_conversation_id, last_inbound_at
   ├──< PointTransaction   (registro scan/conversion: fonte di verità)
   ├──< MerchantPool       (contatore del pool del mese)
   ├──< TreePlanting       (piantumazioni di fine mese)
   └──< ProcessedWebhookEvent (dedup dei webhook, 7 giorni)

ZernioSendCounter (quota_scope, period) → invii riusciti del mese per team Zernio
AuthCredential (user_id = Merchant.auth_user_id, nessuna FK) → hash della password, solo con il provider `local`
```

| Tabella | Campi principali | Note |
|---|---|---|
| **Merchant** | campi v0.2.0 + `is_paused` (default `False`), `created_at` (iscrizione, UTC) + `zernio_api_key_enc`, `zernio_account_id` (unico), `zernio_profile_id`, `zernio_team_id`, `instagram_username`, `webhook_hook_id` (unico), `webhook_secret_enc`, `zernio_webhook_id`, `instagram_status`, `persistent_menu_set`, `standby_detected_at`, `standby_owner_app_id` | chiave e secret cifrati, mai restituiti. **Stato del servizio** derivato da `is_approved` + `is_paused` (nessuna colonna di stato): vedi «Stato del servizio» |
| **Card** | `id` UUID (= contenuto del QR per lo scan), `merchant_id`, `igsid_hash`, `link_version`, `link_token_hash` (unico), `zernio_conversation_id`, `last_inbound_at`, `cashback_cents`, `tree_points`, `created_at` | `UNIQUE(merchant_id, igsid_hash)`: una carta per (negozio, profilo Instagram) |
| **PointTransaction** | `merchant_id`, `card_id` (non FK), `kind` (`scan`\|`conversion`), `delta`, `period`, `created_at` | **registro = fonte di verità** e audit |
| **MerchantPool** | PK `(merchant_id, period)`, `points` | contatore del pool, aggiornato nella **stessa transazione** dello scan |
| **TreePlanting** | `merchant_id`, `period`, `level`, `tree_count`, `pool_points`, `ecologi_ref`, `test` | `UNIQUE(merchant_id, period, test)`: idempotenza della chiusura |
| **ProcessedWebhookEvent** | PK `event_id` (`X-Zernio-Event-Id`), `merchant_id`, `received_at`, `outcome` (`received` → esito) | inserito **per primo**: i retry Zernio diventano no-op; conservato 7 giorni |
| **ZernioSendCounter** | PK `(quota_scope, period)`, `sent` | quota Zernio di 10.000 invii al mese **per team** (oggi l'ambito è `account:<id>`); solo avviso, non blocca |
| **AuthCredential** | PK `user_id` (uuid = `Merchant.auth_user_id`), `email` (unica, minuscola), `password_hash`, `token_version`, `created_at` | solo provider `local`; **nessuna FK** verso `merchant` (se si passa a Supabase la tabella si elimina); `password_hash` fuori dal `repr`. Si cancella con il merchant (API admin) o se la registrazione fallisce a metà |

⚠️ Nota SQLModel: con `table=True` i validatori pydantic **non girano sul costruttore**: per validare usa `Model.model_validate(...)` (come fanno i `db_crud`).

### Segreti e dati personali

| Dato | Come si salva | Perché |
|---|---|---|
| IGSID del cliente | solo `igsid_hash` = HMAC-SHA256(`IGSID_HMAC_KEY`, IGSID) | serve solo a ritrovare la carta; per rispondere basta `zernio_conversation_id`. La chiave **non è ruotabile** (scollegherebbe le carte) |
| Token del link | **non si salva**: token = HMAC(`CARD_LINK_KEY`, id carta + versione), nel DB solo `SHA-256(token)` | stesso link a ogni messaggio; revoca = `link_version + 1` |
| Chiave Zernio, secret del webhook | AES-256-GCM (`ENCRYPTION_KEY`), formato `<id chiave>:<nonce+cifrato>` | servono in chiaro per chiamare Zernio e verificare le firme; l'id della chiave prepara la rotazione |
| Password del merchant (provider `local`) | solo l'hash `scrypt$n$r$p$salt$hash` in `AuthCredential` (salt casuale per password, parametri nella stringa) | la password in chiaro non si salva né si logga; confronto in tempo costante |
| Testo dei messaggi, username, nome | **non si salvano** | minimizzazione |

Nei log non compaiono chiave Zernio, secret, IGSID, token del link, testo, password, hash o token di sessione. Un filtro su `uvicorn.access` maschera `/c/<token>` e
`/webhooks/zernio/<hook_id>`. I log della piattaforma DigitalOcean sono fuori dal nostro controllo: trade-off accettato.

## Il pool del negozio (invariato da v0.2.0)

```
 Cliente A ─┐                                   ┌─ conversione in cashback (card):
 Cliente B ─┼─ scan +N tree points ─► PointTransaction(scan)   al raggiungimento della soglia
 Cliente C ─┘            │                         PointTransaction(conversion) — NON tocca il pool
                         ▼ (stessa transazione)
              MerchantPool(merchant, 'YYYY-MM').points += N
                         │
        fine mese: scripts.close_period  (anteprima → conferma → idempotente)
                         ▼
   livello = f(points, soglie effettive)   soglie = default TIER_* + override del negozio
   🥉 Bronzo → 1 albero · 🥈 Argento → 3 · 🥇 Oro → 5   (totali del mese, non cumulativi)
                         ▼
   Ecologi (chiave di piattaforma) → TreePlanting(snapshot pool_points, ecologi_ref)
   Il mese successivo il pool riparte da zero (nuova riga MerchantPool).
```

Guardie della chiusura: solo negozi **approvati**; si ferma se contatore e registro **divergono**
(`pool_mismatches`) o se il totale supera il **cap globale** (`ECOLOGI_GLOBAL_MONTHLY_CAP`, `--cap` per autorizzare);
un errore su un negozio non blocca gli altri (resta non chiuso e si ritenta).

## Flussi

### 1. Webhook → carta → risposta (`POST /webhooks/zernio/{hook_id}`)

```
1. hook_id → Merchant (sconosciuto → 404)
2. firma X-Zernio-Signature = HMAC-SHA256(secret del negozio, corpo grezzo), compare_digest (errata → 401)
3. INSERT ProcessedWebhookEvent(X-Zernio-Event-Id) — già presente → 200, fine (retry Zernio)
4. parse message.received → account.accountId del negozio? direction incoming?      no → 200 (ignorato)
5. metadata.standby? → standby_detected_at = ora (avviso nel pannello), nessuna carta → 200
6. trigger: testo normalizzato == INSTAGRAM_CARD_KEYWORD  oppure  postback FIDELITREE_CARD   no → 200 (ignorato)
7. isFollower == false? → NESSUNA carta: testo fisso "segui @negozio, poi riscrivi CARTA" (outcome follow_requested,
   stessa finestra di 24 h, stessa quota). true o null (dato non disponibile) → si prosegue con la carta
8. negozio ATTIVO o IN PAUSA: carta = get_or_create(merchant, HMAC(IGSID)); salva conversation.id e last_inbound_at = message.sentAt
   negozio IN ATTESA: carta = solo ricerca (mai creata). Se esiste → come sopra; se non esiste → nessuna riga Card, nulla salvato
9. can_reply(sentAt, ora) (< 24 h)?                                                  no → 200 (fuori finestra)
10. card generic template: titolo = nome negozio, sottotitolo fisso, bottone "Apri la carta" → <PUBLIC_BASE_URL>/c/<token>
    (cliente nuovo di un negozio in attesa: → <PUBLIC_BASE_URL>/carta-di-prova, anche nel testo di ripiego)
    POST /v1/inbox/conversations/{conversation.id}/messages (Idempotency-Key = event id, timeout 4 s, nessun nuovo tentativo)
    └─ errore Meta 2/1545133 (Meta rifiuta la card) → testo fisso con il link (rete di sicurezza)
    └─ 401/403 chiave → instagram_status = key_invalid · 409 not_thread_owner → come standby · timeout di lettura → send_uncertain (contato, negozio non attivato) · altri → send_failed, log
11. invio riuscito (card, ripiego o invito): ZernioSendCounter(quota_scope, mese) += 1 (avviso al 75%); awaiting_test_dm → active
12. risposta 200 entro 5 s (sempre, dopo una firma valida)
```

`hook_id` sconosciuto, o negozio senza chiave/account → 404; firma assente o errata → 401. Un corpo non valido, un
evento senza id o un `X-Zernio-Event-Id` già visto → 200 senza elaborare. Una riga evento rimasta `received` indica
un'elaborazione interrotta: il retry di Zernio non la ripete, per non rischiare un doppio invio.

Il riconoscitore di trigger lavora su `InboundMessage` con un campo `source` (`dm_text`, `dm_postback`): commenti e
risposte alle storie si aggiungeranno come nuove sorgenti, senza toccare i passi 8-12.

### 2. Onboarding Instagram del merchant (`/merchant/settings`)

```
registrazione merchant (invariata) → incolla chiave Zernio
   → GET /v1/accounts?platform=instagram&status=connected (validazione reale; 401 → "chiave non valida")
   → chiave salvata cifrata, scelta dell'account Instagram
   → genera hook_id + secret → POST /v1/webhooks/settings {url /webhooks/zernio/<hook_id>, secret, events [message.received], accountIds}
   → menu persistente: vuoto? imposta "🌳 La mia carta" : lascia quello esistente e avvisa
     (se c'è già la nostra voce vale come impostata; un errore sul menu non blocca il collegamento)
   → stato awaiting_test_dm: "scrivi CARTA al tuo negozio da un altro profilo"
   → primo invio riuscito → active      (standby → avviso "un'altra app gestisce i messaggi")
Se il webhook non si registra (502) non si salva nulla. Con un webhook già attivo si risponde 409: prima «Scollega».
Scollega: DELETE del webhook su Zernio (un tentativo, errore solo nel log) + cancellazione di chiave, secret e campi
Zernio (le carte restano; la voce di menu già impostata resta su Instagram).
```

### 3. Scan dal QR della pagina carta

Il cliente apre `/c/<token>` dal link della card: vede tree points, cashback, avanzamento della conversione, livello
del pool e un **QR che contiene solo l'id della carta** (non il token: una foto del QR non apre la carta). Il merchant
lo inquadra da `/merchant/scanner` (PWA) → `/merchant/card/<id>/manage` (cookie merchant + carta del suo negozio) →
+tree points → registro, pool e conversione come in v0.2.0 (solo se il negozio è **attivo**: vedi «Stato del servizio»).

La pagina carta risponde con `Cache-Control: no-store` e `Referrer-Policy: no-referrer` (il saldo cambia a ogni scan,
l'URL è il segreto); token sconosciuto o revocato → stessa 404 amichevole. Le pagine HTML merchant senza sessione valida
rimandano con 303 a `/merchant/login` (le API `/api/merchant/*` restano 401).

### 4. Dashboard admin del founder (`/admin`)

```
GET /admin/login → POST /admin/login (password = ADMIN_SECRET_KEY, confronto in tempo costante, freno 5 errori/15 min → 429)
   → cookie admin_session (JWT role=admin, httpOnly, SameSite=Strict, Path=/admin, 12 ore) → 303 /admin
GET /admin → pagina; GET /admin/api/merchants → lista JSON (al massimo 200, dai più recenti, nessun segreto)
POST /admin/api/merchants/{id}/approve | pause | resume | reset-password
   ├─ autenticazione: cookie valido oppure header X-Admin-Key corretto (401 altrimenti; pagine HTML: 303 al login)
   ├─ cookie → Origin (o Referer) deve coincidere con l'header Host, altrimenti 403 (con X-Admin-Key corretto non serve)
   └─ id sconosciuto 404 · pause/resume su negozio in attesa 409 · reset: 409 senza credenziale, 400 con provider senza password
```

**Flusso di approvazione**: il founder manda al merchant il link `/merchant/register` → il merchant si iscrive (nasce **in attesa**: Instagram sì, carta vera ai clienti no) → gli scrive (es. su WhatsApp) → il founder lo **avvia** dalla dashboard (`approve`: `is_approved=true`, `is_paused=false`) → il merchant è **attivo**. Periodo di prova finito o abbonamento non pagato → «Metti in pausa» (può solo togliere saldo); pagato → «Riattiva». Nessun pagamento in app, nessuna email, nessun link di invito.

**Reset della password**: «Reimposta password» genera una password temporanea di 12 caratteri (alfabeto senza caratteri ambigui) con `secrets.choice`, la imposta con `PasswordAdminProvider.set_password` (nuovo hash, `token_version + 1`: le sessioni aperte decadono), azzera il freno del login di quell'email (altrimenti il merchant fermato dal 429 non potrebbe usarla) e la mostra **una sola volta** (campo `temporary_password` della risposta, pulsante «Copia»). Non si salva in chiaro, non si logga, il `repr` della risposta non la mostra; la risposta è `no-store`. Il merchant la cambia da `/merchant/settings`.

La pagina costruisce il DOM solo con `textContent` (i nomi delle attività li scrivono i merchant, quindi mai HTML da stringa) e il server non stampa nessun dato dei merchant nell'HTML: la lista arriva dal JSON. Il founder **non** crea profili, non elimina e non modifica i dati del negozio dalla dashboard.

### 5. Chiusura mensile

`python -m scripts.close_period` (vedi `deploy.md`), invariata.

## Punto di aggancio per la migrazione a una chiave Zernio unica

`zernio_service.zernio_credentials_for(merchant) -> ZernioCredentials(api_key, account_id, profile_id, webhook_secret,
quota_scope)` è l'**unico** codice che sa da dove arriva la chiave.

| | Oggi (pilota) | Domani (chiave unica del founder) |
|---|---|---|
| `api_key` | chiave del merchant, decifrata | chiave di piattaforma (env) |
| `account_id` / `profile_id` | scelti all'onboarding | `profileId` per negozio, account collegato con il connect OAuth di Zernio (`GET /v1/connect/instagram?profileId=...`) |
| `webhook_secret` | secret per negozio | invariato (un webhook per negozio, oppure uno unico con instradamento per `accountId`) |
| `quota_scope` | `"account:<zernio_account_id>"`: Zernio non espone un id del team (`get_team_identity` ritorna sempre `None`), quindi il ramo `"zernio:<zernio_team_id>"` oggi non scatta | `"platform"` (un solo team: 10.000 invii al mese condivisi, rate limit per team) |

Service, modelli, webhook e contatore non cambiano: cambiano solo questa funzione e l'onboarding (connect al posto
della chiave incollata).

## Stato del servizio

Derivato da `Merchant.is_approved` e `Merchant.is_paused` (nessun enum in DB): `card_service.service_state(is_approved, is_paused)`
→ `ServiceState` (`app/core/enums.py`). Un negozio non approvato è sempre **in attesa**; la pausa conta solo se è approvato.
Core puro in `card_service`: `can_add_balance` (solo `active`), `can_remove_balance` (sempre), `check_balance_change(state, delta)`
(`ForbiddenError` → 403 per un delta positivo, prima di ogni scrittura; delta 0 sempre ammesso).

| Stato (`is_approved`, `is_paused`) | Webhook | Scanner (merchant) | Pagina carta `/c/<token>` |
|---|---|---|---|
| **In attesa** (`False`, —) | cliente con carta → link vero; **cliente nuovo → `/carta-di-prova`**, nessuna riga `Card` né indice cieco | solo togliere, nessuna conversione | identica |
| **Attivo** (`True`, `False`) | come sempre | tutto | identica |
| **In pausa** (`True`, `True`) | come sempre | solo togliere, nessuna conversione | identica |

- La conversione tree points → cashback si salta se il negozio non è attivo, anche con un delta negativo: il merchant può abbassare
  la soglia dalle impostazioni e un `-1` farebbe scattare una conversione, cioè un accredito.
- L'avviso sta solo nelle pagine del merchant (partial `service_banner`: scanner, gestione carta, impostazioni); il cliente non vede
  nessuna differenza. `/carta-di-prova` è una pagina statica (stessi header no-store/no-referrer della pagina carta, `noindex`), senza QR vero.
- `tree_service.close_period` non cambia: conta solo `is_approved` (un negozio approvato in pausa partecipa con i punti già raccolti).
- Il cambio di stato è manuale, dalla **dashboard admin** (flusso 4): «Avvia» (`approve`) imposta `is_approved` **e toglie la pausa**; «Metti in pausa» e
  «Riattiva» valgono solo per un negozio già approvato (su uno in attesa: 409). Anche `POST /api/merchant/{id}/approve` (X-Admin-Key) passa dallo stesso
  service, quindi toglie la pausa. Nessuna transizione verso «in attesa» (si rimette `is_approved=false` solo dall'API admin `PUT`).

## Autenticazione

Tutto passa da `AuthProvider` (`app/core/auth.py`), scelto da `AUTH_PROVIDER`; la tabella `merchant` non ha password, solo `auth_user_id` ed email.

- **Provider `local`** (pilota, **ammesso in produzione**): email+password, hash `scrypt` della libreria standard (N=2^14, r=8, p=1, salt casuale per password) in `AuthCredential`, password di 8-128 caratteri. Il token è un JWT (`JWT_SECRET_KEY`) con `sub`, `email` e `ver` = `token_version`: `verify_token` controlla firma, scadenza, **esistenza della credenziale e `ver`**, quindi `set_password` (reset dell'admin, ticket 13) e `change_password` (il merchant, dalle impostazioni) invalidano le sessioni aperte. Email sconosciuta e password errata danno lo stesso `AuthError` («Credenziali non valide»; con email sconosciuta si verifica un hash fittizio). Accede al DB con una *session factory* iniettabile (default `Session(engine)`, import tardivo; i test usano SQLite in-memory). Contratto `PasswordAdminProvider` (`set_password`, `change_password`, `delete_user`): lo implementa solo `local`.
- **Provider `dev`** (locale/test): utenti in memoria, password `DEV_AUTH_PASSWORD` per i merchant non registrati nel processo (così funzionano gli account del seed), token = JWT firmato con `JWT_SECRET_KEY` (senza `ver`: un token `dev` non vale con `local` e viceversa). Con `ENVIRONMENT=production` l'app **non parte** (`get_auth_provider()` è chiamato dal lifespan).
- **Provider `supabase`**: stub, si collega in un rilascio successivo.
- **Merchant**: `POST /merchant/register` (nasce non approvato, quindi **in attesa**: vedi «Stato del servizio») e `POST /merchant/login` (email + password) → cookie `access_token` (httpOnly, samesite lax, **Secure** con `ENVIRONMENT=production`) → `get_current_merchant`. Se la creazione del merchant fallisce dopo quella della credenziale, questa si elimina (altrimenti l'email resterebbe bloccata).
- **Freno ai tentativi sul login** (`LoginThrottle`, core in `auth.py`): 5 errori in 15 minuti **per email normalizzata** (nessun freno per IP: dietro il proxy di DO sarebbe lo stesso per tutti o falsificabile via `X-Forwarded-For`, quindi il Dockerfile non cambia). Dal 3° errore il 401 aggiunge «Attenzione: dopo 5 errori l'accesso si ferma per 15 minuti», al 5° «Accesso sospeso», poi 429 con `Retry-After` e l'invito a chiedere al founder di reimpostare la password. Il controllo precede ogni verifica (a soglia anche la password giusta riceve 429); l'email sconosciuta conta come errore, con gli stessi messaggi (l'avviso non rivela se l'account esiste); un accesso riuscito azzera il contatore; l'identità senza merchant (403) non conta. Contatore **in memoria**: corretto con un solo processo (oggi su DO), si azzera al riavvio, con più processi/worker ciascuno ha il suo (limite × N). Lo usa anche il login admin (chiave fissa `admin`, messaggio e invito diversi: vedi «Admin»).
- **Cambio password del merchant**: `POST /api/merchant/me/password` (password attuale + nuova): 400 se la nuova non è di 8-128 caratteri (o il provider non gestisce le password), 401 se l'attuale è errata; riemette il cookie con il nuovo `ver`. Il blocco «Cambia password» delle impostazioni compare solo se il provider è un `PasswordAdminProvider`.
- **Cliente**: **nessuna autenticazione**. La carta si vede solo con il link segreto `/c/<token>`.
- **Zernio → app**: firma HMAC per negozio sul webhook.
- **Admin**: due ingressi con la stessa `ADMIN_SECRET_KEY` (un valore vuoto non fa entrare nessuno). (1) header `X-Admin-Key` → `require_admin_key` per `/api/merchant/*` (CRUD, `approve`; 403 se manca) e `require_admin_session` per `/admin/api/*` (401). (2) **dashboard `/admin`**: `POST /admin/login` confronta la password con `hmac.compare_digest` e imposta il cookie `admin_session` (JWT firmato con `JWT_SECRET_KEY`, claim `role=admin` e **nessun** `sub`/`email`, quindi i provider dei merchant lo rifiutano e viceversa un token merchant non vale come sessione admin; 12 ore; httpOnly, SameSite=Strict, `Path=/admin`, `Secure` in produzione). Freno: 5 errori in 15 minuti → 429 su una chiave unica `admin` (in memoria; contatore globale, quindi il *form* si può fermare per 15 minuti con tentativi sbagliati: l'header `X-Admin-Key` non ha freno ed è la via di ripiego). CSRF: i POST con cookie richiedono `Origin`/`Referer` uguale a `Host` (403), `Origin: null` vale come estraneo; le risposte admin hanno `Cache-Control: no-store`, `noindex` e `Referrer-Policy: same-origin` (con `no-referrer` ogni azione darebbe 403). Il logout cancella solo il cookie: il JWT non è revocabile e scade da solo.

## Endpoint

| Metodo e path | Protezione | Scopo |
|---|---|---|
| GET /health | pubblico | health check con `version` (da `pyproject.toml`) |
| GET /sw.js | pubblico | service worker della PWA merchant (scope `/merchant/`) |
| POST /webhooks/zernio/{hook_id} | firma HMAC del negozio | DM Instagram → carta → card di risposta |
| GET /c/{token} | link segreto | pagina carta con QR (id carta), saldo e pool del negozio |
| GET /carta-di-prova | pubblico | carta fittizia per i clienti nuovi di un negozio in attesa (nessun dato, `noindex`, no-store) |
| GET /privacy | pubblico | informativa per i clienti |
| GET /merchant/login, /merchant/register | pubblico | pagine di accesso |
| POST /merchant/register, POST /merchant/login, GET /merchant/logout | pubblico | auth merchant (login: 401 credenziali, 403 senza negozio, **429** troppi tentativi con `Retry-After`) |
| GET /admin/login, POST /admin/login, GET /admin/logout | pubblico (login: `Origin` del nostro host, freno **429**) | accesso alla dashboard del founder (cookie `admin_session`) |
| GET /admin | cookie admin o `X-Admin-Key` (altrimenti 303 al login) | pagina della dashboard (la lista arriva dal JSON) |
| GET /admin/api/merchants | cookie admin o `X-Admin-Key` (401) | lista dei merchant: stato del servizio, stato Instagram, carte, punti del mese; nessun segreto |
| POST /admin/api/merchants/{id}/approve, /pause, /resume | cookie admin + `Origin` (403) o `X-Admin-Key` (401) | avvia (approva e toglie la pausa), metti in pausa, riattiva; ritornano la riga aggiornata (404, 409 per pausa/riattiva di un negozio in attesa) |
| POST /admin/api/merchants/{id}/reset-password | come sopra | password temporanea mostrata solo nella risposta (404, 409 senza credenziale, 400 provider senza password) |
| GET /merchant/scanner, /merchant/settings, /merchant/card/{id}/manage | cookie merchant | pagine merchant (PWA); banner di stato e pulsanti di aggiunta disattivati se il negozio è in attesa o in pausa |
| GET /api/merchant/me, PUT /api/merchant/me/settings | cookie merchant | profilo e impostazioni di conversione |
| POST /api/merchant/me/password | cookie merchant | cambio password (400 nuova non valida, 401 attuale errata); riemette il cookie |
| POST /api/merchant/instagram/key, GET /api/merchant/instagram/accounts, POST /api/merchant/instagram/account, GET /api/merchant/instagram, DELETE /api/merchant/instagram | cookie merchant | onboarding Instagram/Zernio e pannello |
| POST /api/merchant/add-tree-points/{id} | cookie merchant | scan: tree points (+ conversione automatica); **403** se il negozio non è attivo e il delta è positivo |
| POST /api/merchant/add-point/{id} | cookie merchant | +/- cashback in euro; **403** se il negozio non è attivo e l'importo è positivo |
| DELETE /api/merchant/card/{id} | cookie merchant | elimina carta propria (cancellazione su richiesta del cliente) |
| CRUD /api/merchant/…, POST /api/merchant/{id}/approve | X-Admin-Key (403) | gestione merchant, approvazione (toglie anche la pausa), soglie e `is_paused` (il DELETE elimina anche la credenziale `local`) |

Rimossi in v0.3.0: `/customer/login`, `/api/customer/otp/*`, `/customer/logout`, `/join/{id}`, `/wallet`,
`/api/customer/*`, `/card/{id}`, `/api/card/{id}`.

## Scelte tecniche rilevanti

- **Functional core / imperative shell** nello stesso modulo di `services/` (regole in AGENTS.md). Errori di dominio in `app/core/errors.py`, tradotti in HTTP da un handler globale (`ExternalServiceError` → 502, `TooManyAttemptsError` → 429 con `Retry-After`).
- **Zernio**: client httpx diretto (`zernio_service.py`), niente SDK. `httpx.AsyncClient` iniettato tramite dependency (`MockTransport` nei test). Timeout 4 s sugli invii (il webhook deve rispondere entro 5 s), nessun nuovo tentativo (un 5xx può aver già consegnato). Vincoli e fonti: [zernio-notes.md](zernio-notes.md).
- **Cifratura**: `cryptography` (AES-256-GCM), tornata in v0.3.0 perché la chiave Zernio deve essere recuperabile. Le chiavi arrivano solo da env e l'app non parte se mancano o sono malformate.
- **Engine DB** in `app/main.py` con `pool_pre_ping=True` e `pool_recycle=300` (timeout SSL di Neon).
- **`get_session`** importa l'engine lazy da `app.main` (evita import circolari); nei test viene sostituita da SQLite in-memory (`tests/conftest.py`).
- **QR code** generato client-side (niente dipendenze server).
- **Lifespan**: validazione delle chiavi di cifratura, scelta del provider di autenticazione (`dev` con `production` → l'app non parte), filtro dei log di accesso, `create_all` (niente Alembic: il DB si resetta con `scripts.reset_db`).
- **Ecologi**: un solo URL (`ECOLOGI_BASE_URL`), due chiavi scelte da `ECOLOGI_TEST_MODE` (`ECOLOGI_TEST_API_KEY` / `ECOLOGI_API_KEY`, nessun fallback). Con `true` la richiesta porta `"test": true` (nessun addebito). Il `name` inviato è `<negozio> · <mese> <anno>` (`tree_service.planting_name`) e compare nella foresta pubblica; `TreePlanting.ecologi_ref` = `treeUrl` della risposta (non c'è un `id`).
