# Architettura Fidelitree (v0.3.0)

> ⚠️ **Transizione (dal 2026-10-22)**: questo documento descrive l'architettura **target** di v0.3.0, in sviluppo su
> `feature/instagram-cards` ([ticket](../tickets/v0.3.0/README.md)). Finché il ticket 09 non è chiuso, nel codice
> convivono il vecchio flusso cliente (OTP, wallet, `/join`) e il nuovo. Il banner si toglie nel ticket 11.

## Vista d'insieme

Monolite FastAPI con rendering server-side (Jinja2) e API JSON. Un solo processo, un solo database.
La carta del cliente nasce da un **DM Instagram** al negozio, ricevuto tramite **Zernio** (webhook) e risposto con una
card che contiene un link segreto. Il cliente non ha autenticazione. La **PWA** è solo del merchant (scanner e gestione).

```
Cliente (Instagram) ── DM "CARTA" / menu ──► Instagram ──► Zernio ── webhook firmato ──┐
        ▲                                                                              │
        └──── card "Apri la carta" ◄── Zernio ◄── POST messages (chiave del merchant) ─┤
                                                                                       ▼
Browser cliente: /c/<token> (pagina carta + QR)        FastAPI (app/main.py)
Browser merchant: PWA /merchant/* (scanner, gestione)    routes → services (core puro + shell) → db_crud
                                                          ▼
                                       PostgreSQL (Neon oggi, Supabase al collegamento del provider auth)

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
```

| Tabella | Campi principali | Note |
|---|---|---|
| **Merchant** | campi v0.2.0 + `zernio_api_key_enc`, `zernio_account_id` (unico), `zernio_profile_id`, `zernio_team_id`, `instagram_username`, `webhook_hook_id` (unico), `webhook_secret_enc`, `zernio_webhook_id`, `instagram_status`, `persistent_menu_set`, `standby_detected_at`, `standby_owner_app_id` | chiave e secret cifrati, mai restituiti |
| **Card** | `id` UUID (= contenuto del QR per lo scan), `merchant_id`, `igsid_hash`, `link_version`, `link_token_hash` (unico), `zernio_conversation_id`, `last_inbound_at`, `cashback_cents`, `tree_points`, `created_at` | `UNIQUE(merchant_id, igsid_hash)`: una carta per (negozio, profilo Instagram) |
| **PointTransaction** | `merchant_id`, `card_id` (non FK), `kind` (`scan`\|`conversion`), `delta`, `period`, `created_at` | **registro = fonte di verità** e audit |
| **MerchantPool** | PK `(merchant_id, period)`, `points` | contatore del pool, aggiornato nella **stessa transazione** dello scan |
| **TreePlanting** | `merchant_id`, `period`, `level`, `tree_count`, `pool_points`, `ecologi_ref`, `test` | `UNIQUE(merchant_id, period, test)`: idempotenza della chiusura |
| **ProcessedWebhookEvent** | PK `event_id` (`X-Zernio-Event-Id`), `merchant_id`, `received_at`, `outcome` (`received` → esito) | inserito **per primo**: i retry Zernio diventano no-op; conservato 7 giorni |
| **ZernioSendCounter** | PK `(quota_scope, period)`, `sent` | quota Zernio di 10.000 invii al mese **per team**; solo avviso, non blocca |

⚠️ Nota SQLModel: con `table=True` i validatori pydantic **non girano sul costruttore**: per validare usa `Model.model_validate(...)` (come fanno i `db_crud`).

### Segreti e dati personali

| Dato | Come si salva | Perché |
|---|---|---|
| IGSID del cliente | solo `igsid_hash` = HMAC-SHA256(`IGSID_HMAC_KEY`, IGSID) | serve solo a ritrovare la carta; per rispondere basta `zernio_conversation_id`. La chiave **non è ruotabile** (scollegherebbe le carte) |
| Token del link | **non si salva**: token = HMAC(`CARD_LINK_KEY`, id carta + versione), nel DB solo `SHA-256(token)` | stesso link a ogni messaggio; revoca = `link_version + 1` |
| Chiave Zernio, secret del webhook | AES-256-GCM (`ENCRYPTION_KEY`), formato `<id chiave>:<nonce+cifrato>` | servono in chiaro per chiamare Zernio e verificare le firme; l'id della chiave prepara la rotazione |
| Testo dei messaggi, username, nome | **non si salvano** | minimizzazione |

Nei log non compaiono chiave Zernio, secret, IGSID, token o testo. Un filtro su `uvicorn.access` maschera `/c/<token>` e
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
7. carta = get_or_create(merchant, HMAC(IGSID)); salva conversation.id e last_inbound_at = message.sentAt
8. can_reply(sentAt, ora) (< 24 h)?                                                  no → 200 (fuori finestra)
9. card generic template: titolo = nome negozio, sottotitolo fisso, bottone "Apri la carta" → <PUBLIC_BASE_URL>/c/<token>
   POST /v1/inbox/conversations/{conversation.id}/messages (Idempotency-Key = event id, timeout 3 s, nessun nuovo tentativo)
   └─ errore Meta 2/1545133 (non follower) → testo fisso con il link
   └─ 401/403 chiave → instagram_status = key_invalid · 409 not_thread_owner → come standby · altri → log
10. invio riuscito: ZernioSendCounter(quota_scope, mese) += 1 (avviso al 75%); awaiting_test_dm → active
11. risposta 200 entro 5 s (sempre, dopo una firma valida)
```

Il riconoscitore di trigger lavora su `InboundMessage` con un campo `source` (`dm_text`, `dm_postback`): commenti e
risposte alle storie si aggiungeranno come nuove sorgenti, senza toccare i passi 7-11.

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
+tree points → registro, pool e conversione come in v0.2.0.

### 4. Chiusura mensile

`python -m scripts.close_period` (vedi `deploy.md`), invariata.

## Punto di aggancio per la migrazione a una chiave Zernio unica

`zernio_service.zernio_credentials_for(merchant) -> ZernioCredentials(api_key, account_id, profile_id, webhook_secret,
quota_scope)` è l'**unico** codice che sa da dove arriva la chiave.

| | Oggi (pilota) | Domani (chiave unica del founder) |
|---|---|---|
| `api_key` | chiave del merchant, decifrata | chiave di piattaforma (env) |
| `account_id` / `profile_id` | scelti all'onboarding | `profileId` per negozio, account collegato con il connect OAuth di Zernio (`GET /v1/connect/instagram?profileId=...`) |
| `webhook_secret` | secret per negozio | invariato (un webhook per negozio, oppure uno unico con instradamento per `accountId`) |
| `quota_scope` | `"zernio:<zernio_team_id>"` (team Zernio della chiave del merchant; fallback `"account:<zernio_account_id>"`) | `"platform"` (un solo team: 10.000 invii al mese condivisi, rate limit per team) |

Service, modelli, webhook e contatore non cambiano: cambiano solo questa funzione e l'onboarding (connect al posto
della chiave incollata).

## Autenticazione

Tutto passa da `AuthProvider` (`app/core/auth.py`); nel DB non ci sono password, solo `auth_user_id` ed email del merchant.

- **Provider `dev`** (locale/test): utenti in memoria, password `DEV_AUTH_PASSWORD` per i merchant non registrati nel processo (così funzionano gli account del seed), token = JWT firmato con `JWT_SECRET_KEY`. Con `ENVIRONMENT=production` l'app **rifiuta** di usarlo.
- **Provider `supabase`**: stub, si collega in un rilascio successivo.
- **Merchant**: `POST /merchant/register` (nasce non approvato, lavora subito) e `POST /merchant/login` (email + password) → cookie `access_token` httpOnly → `get_current_merchant`.
- **Cliente**: **nessuna autenticazione**. La carta si vede solo con il link segreto `/c/<token>`.
- **Zernio → app**: firma HMAC per negozio sul webhook.
- **Admin**: header `X-Admin-Key` = `ADMIN_SECRET_KEY` → `require_admin_key`.

## Endpoint

| Metodo e path | Protezione | Scopo |
|---|---|---|
| GET /health | pubblico | health check con `version` (da `pyproject.toml`) |
| GET /sw.js | pubblico | service worker della PWA merchant (scope `/merchant/`) |
| POST /webhooks/zernio/{hook_id} | firma HMAC del negozio | DM Instagram → carta → card di risposta |
| GET /c/{token} | link segreto | pagina carta con QR (id carta), saldo e pool del negozio |
| GET /privacy | pubblico | informativa per i clienti |
| GET /merchant/login, /merchant/register | pubblico | pagine di accesso |
| POST /merchant/register, POST /merchant/login, GET /merchant/logout | pubblico | auth merchant |
| GET /merchant/scanner, /merchant/settings, /merchant/card/{id}/manage | cookie merchant | pagine merchant (PWA) |
| GET /api/merchant/me, PUT /api/merchant/me/settings | cookie merchant | profilo e impostazioni di conversione |
| POST /api/merchant/instagram/key, GET /api/merchant/instagram/accounts, POST /api/merchant/instagram/account, GET /api/merchant/instagram, DELETE /api/merchant/instagram | cookie merchant | onboarding Instagram/Zernio e pannello |
| POST /api/merchant/add-tree-points/{id} | cookie merchant | scan: tree points (+ conversione automatica) |
| POST /api/merchant/add-point/{id} | cookie merchant | +/- cashback in euro |
| DELETE /api/merchant/card/{id} | cookie merchant | elimina carta propria (cancellazione su richiesta del cliente) |
| CRUD /api/merchant/…, POST /api/merchant/{id}/approve | X-Admin-Key | gestione merchant, approvazione, soglie |

Rimossi in v0.3.0: `/customer/login`, `/api/customer/otp/*`, `/customer/logout`, `/join/{id}`, `/wallet`,
`/api/customer/*`, `/card/{id}`, `/api/card/{id}`.

## Scelte tecniche rilevanti

- **Functional core / imperative shell** nello stesso modulo di `services/` (regole in AGENTS.md). Errori di dominio in `app/core/errors.py`, tradotti in HTTP da un handler globale (`ExternalServiceError` → 502).
- **Zernio**: client httpx diretto (`zernio_service.py`), niente SDK. `httpx.AsyncClient` iniettato tramite dependency (`MockTransport` nei test). Timeout 3 s sugli invii (il webhook deve rispondere entro 5 s), nessun nuovo tentativo (un 5xx può aver già consegnato). Vincoli e fonti: [zernio-notes.md](zernio-notes.md).
- **Cifratura**: `cryptography` (AES-256-GCM), tornata in v0.3.0 perché la chiave Zernio deve essere recuperabile. Le chiavi arrivano solo da env e l'app non parte se mancano o sono malformate.
- **Engine DB** in `app/main.py` con `pool_pre_ping=True` e `pool_recycle=300` (timeout SSL di Neon).
- **`get_session`** importa l'engine lazy da `app.main` (evita import circolari); nei test viene sostituita da SQLite in-memory (`tests/conftest.py`).
- **QR code** generato client-side (niente dipendenze server).
- **Lifespan**: `create_all`, validazione delle chiavi di cifratura, filtro dei log di accesso (niente Alembic: il DB si resetta con `scripts.reset_db`).
- **Ecologi**: un solo URL (`ECOLOGI_BASE_URL`), due chiavi scelte da `ECOLOGI_TEST_MODE` (`ECOLOGI_TEST_API_KEY` / `ECOLOGI_API_KEY`, nessun fallback). Con `true` la richiesta porta `"test": true` (nessun addebito). Il `name` inviato è `<negozio> · <mese> <anno>` (`tree_service.planting_name`) e compare nella foresta pubblica; `TreePlanting.ecologi_ref` = `treeUrl` della risposta (non c'è un `id`).
