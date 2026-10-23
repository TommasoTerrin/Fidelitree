# Fidelitree — Guida per Coding Agent

> **Punto di ingresso unico** per qualsiasi coding agent (Claude Code, Codex, Gemini CLI, OpenCode, ...).
> Leggi questo file prima di toccare il codice. Approfondimenti in [`.agents/`](.agents/).

> **Versione su `develop`: v0.2.1** (pool del negozio, auth, wallet cliente + logo e icone PWA), mai andata in produzione
> e **non** verrà rilasciata: è assorbita da v0.3.0.
> ⚠️ **In sviluppo: v0.3.0 — carta fedeltà via DM Instagram (Zernio)** su `feature/instagram-cards`, ticket in
> [`.agents/tickets/v0.3.0/`](.agents/tickets/v0.3.0/README.md). Da qui in giù questo file descrive **v0.3.0 (target)**:
> finché il ticket 09 non è chiuso, il vecchio flusso cliente (OTP, wallet, `/join`) esiste ancora nel codice.
> Il banner si toglie nel ticket 11. Storia di v0.2.0: [`.agents/tickets/v0.2.0/`](.agents/tickets/v0.2.0/README.md).
> Lo stato del lavoro è in [`.agents/planner/current.md`](.agents/planner/current.md).

## Contesto di business

**Fidelitree** è una micro-SaaS solo-founder di **carte fedeltà digitali che piantano alberi veri** per piccoli negozi (bar, forni, fioristi...).

- **Per il cliente finale** è una carta fedeltà che riceve **scrivendo al negozio su Instagram**: nessuna app né iscrizione, un link alla sua carta con cashback e *tree points*.
- **Per il merchant** è uno strumento di fidelizzazione con una storia di marketing pronta: *"questo mese, insieme ai nostri clienti, abbiamo piantato 5 alberi"*.
- **Per il founder** l'app è **gratuita per i merchant**: i ricavi arrivano da consulenza/gestione social e contenuti IA venduti ai merchant (modello agenzia). Gli alberi sono l'hook narrativo del build-in-public e **sono pagati dal founder** (Ecologi, ~0,80 €/albero, chiave API unica di piattaforma).

### Come funziona (v0.3.0)

1. **Il merchant collega il suo Instagram** dalle impostazioni: incolla la sua chiave **Zernio** (account gratuito suo), sceglie l'account Instagram Business/Creator; l'app configura da sola il webhook e la voce di menu "🌳 La mia carta". Diventa attivo dopo un DM di prova.
2. **Il cliente scrive "CARTA" in DM al negozio** (o tocca la voce di menu). Zernio chiama il nostro webhook: l'app crea (o ritrova) la sua carta e risponde con **una card** (titolo = nome del negozio, testo fisso, bottone "Apri la carta"). Nessun dato dinamico nel messaggio; a ogni nuova parola chiave arriva di nuovo la stessa card con lo stesso link.
3. Il link apre la **pagina carta** (`/c/<token segreto>`, nessun login): punti, cashback, livello del pool e un QR. Il merchant scansiona il QR dalla sua **PWA** e aggiunge **tree points** (e, a sua discrezione, **cashback** in €).
4. **Tree points del cliente → cashback**: raggiunta una soglia scelta dal merchant, i tree points della carta si convertono automaticamente in cashback (es. 50 punti → 2,00 €). Il merchant può disattivare la conversione ("solo alberi") e può sempre aggiungere/togliere cashback a mano.
5. **Pool del negozio (gamification collettiva)**: tutti i tree points raccolti dai clienti di un negozio nel **mese solare** formano il pool. Il pool raggiunge dei livelli:

   | Livello | Alberi piantati a fine mese (totali, non cumulativi) |
   |---|---|
   | 🥉 Bronzo | 1 |
   | 🥈 Argento | 3 |
   | 🥇 Oro | 5 |

   Le soglie di punti hanno un default di piattaforma (config) con override per singolo negozio deciso dall'admin. Il cliente vede sulla carta il livello del negozio e quanto manca al successivo.
6. **A fine mese** il founder lancia la chiusura del periodo (script con anteprima e conferma): per ogni negozio approvato si piantano gli alberi del livello raggiunto con la chiave Ecologi di piattaforma. Il pool riparte da zero.

### Regole di business chiave

- **Il founder paga gli alberi** → la spesa è controllata da tre leve: soglie decise dall'admin, merchant **approvati manualmente** (`is_approved`), **cap globale mensile** di alberi (env). Se la chiusura supera il cap, lo script si **blocca e chiede** al founder (nessuna ripartizione automatica in v0.2.0).
- **Il cashback lo paga il merchant** → soglia e valore della conversione li decide lui.
- Il pool conta i movimenti netti di tree points del mese (una rimozione per errore lo riduce); la **conversione in cashback non tocca il pool**.
- Lo scan del merchant **non pianta mai alberi**: la piantumazione avviene solo alla chiusura del periodo.

## Stack

| Livello | Tecnologia |
|---|---|
| Backend | FastAPI + SQLModel (Python 3.12) |
| Frontend | Template Jinja2 + Vanilla JS (Tailwind via CDN, QR client-side); **PWA solo per il merchant** (scanner e gestione); pagina carta del cliente = pagina web semplice |
| Database | PostgreSQL su **Neon** oggi, **Supabase** in un rilascio successivo / SQLite in-memory (test) e su file (collaudo locale) |
| Auth | Merchant: **Supabase Auth** in arrivo (email+password), oggi interfaccia + provider `dev` (locale/test; rifiutato con `ENVIRONMENT=production`). Cliente: **nessuna auth**, link segreto |
| Instagram | **Zernio** (API unificata social): webhook `message.received` + invio card; client httpx diretto. Pilota: **chiave Zernio del merchant**, cifrata |
| Cifratura | `cryptography` (AES-256-GCM) per chiave Zernio e secret del webhook; HMAC per indice cieco dell'IGSID e token del link |
| Alberi | Ecologi Impact API, **chiave unica di piattaforma** (env) |
| Hosting | **DigitalOcean App Platform** (Docker, auto-deploy da `main`) |

## Versionamento

- **Fonte unica della versione**: `[project] version` in `pyproject.toml` (SemVer 0.x).
- A ogni rilascio: bump in `pyproject.toml` → merge su `main` → tag git `vX.Y.Z` con lo stesso valore.
- `v0.1.0` = MVP cashback. `v0.2.0`/`v0.2.1` = pool del negozio + auth + wallet (assorbe la vecchia "Release 2"; mai andata in produzione). `v0.3.0` = carta via DM Instagram (assorbe v0.2.x: prima release in produzione dopo v0.1.0).

## Comandi essenziali

```bash
# Ambiente (Windows)
.venv\Scripts\activate
pip install -r requirements.txt

# Avvio locale con hot-reload (richiede .env — vedi .env.example)
python local_main.py

# Test (SQLite in-memory: NON toccano il DB reale, nessuna rete)
python -m pytest
python -m pytest tests/unit      # solo core puro, velocissimi

# Utilità DB (ATTENZIONE: agiscono sul DATABASE_URL in .env, che può essere il DB vero:
# per il collaudo locale usa un SQLite usa-e-getta, vedi .agents/workflows/deploy.md)
python -m scripts.reset_db      # drop + ricrea schema (chiede conferma)
python -m scripts.seed_db       # 2 merchant, carte "Instagram" finte con link /c/... e scan di prova (solo AUTH_PROVIDER=dev)

# Chiusura mensile: pianta gli alberi del pool (anteprima, conferma, idempotente)
python -m scripts.close_period [--month AAAA-MM] [--cap N] [--yes]

# Verifica la chiave Ecologi: chiamata reale con test=true, nessun addebito
python -m scripts.ecologi_check [--trees N] [--merchant-name NOME] [--month AAAA-MM]

# Zernio: chiamate reali con una chiave (da env ZERNIO_CHECK_API_KEY o richiesta a video) o quella di un merchant
python -m scripts.zernio_check accounts | conversations | send-card | send-text [--merchant-id N]

# Collaudo locale del webhook: evento message.received firmato verso il server (che invia DAVVERO a Zernio)
python -m scripts.replay_webhook --merchant-id N --conversation-id ID [--text CARTA | --postback] [--standby]

# Tunnel https per ricevere i webhook in locale (PUBLIC_BASE_URL = URL stampato)
cloudflared tunnel --url http://127.0.0.1:8001

# Smoke test post-deploy (non pianta alberi)
python scripts/smoke_test_prod.py https://<app>.ondigitalocean.app <ADMIN_SECRET_KEY>
```

## Mappa del codice

```
app/
  main.py               # FastAPI app, engine DB, lifespan (create_all), router
  core/
    config.py           # Settings da .env — variabili obbligatorie: vedi .env.example
    auth.py             # interfaccia AuthProvider + provider dev (Supabase: stub) — solo merchant
    security.py         # JWT (sessione, usato dal provider dev)
    crypto.py           # AES-GCM (chiave Zernio, secret webhook), indice cieco IGSID, token del link, mask_secret
    dependencies.py     # get_session, get_auth_identity, get_current_merchant, require_admin_key
    errors.py enums.py money.py clock.py   # errori di dominio, enum (Level, InstagramStatus...), centesimi↔euro, utc_now
  models/models.py      # tabelle SQLModel
  version.py            # versione letta da pyproject.toml (esposta da /health)
  schemas/              # Pydantic request/response
  services/             # un modulo per funzionalità: core puro + shell (vedi sotto)
    card_service.py     # carte, cashback, conversione tree points → cashback
    instagram_service.py # trigger, card di risposta, finestra 24 h, quota, webhook → carta, link della carta
    zernio_service.py   # client API Zernio + zernio_credentials_for (UNICO punto che sa da dove arriva la chiave)
    merchant_service.py # registrazione, impostazioni, onboarding Instagram
    tree_service.py     # pool del negozio, livelli, chiusura periodo
    ecologi_service.py  # client Impact API Ecologi
    db_crud/            # accesso DB puro
  routes/
    consumer/           # pagina carta /c/{token}, /privacy
    merchant/           # api + auth + pagine merchant
    webhooks.py         # POST /webhooks/zernio/{hook_id}
  templates/            # Jinja2 (consumer/, merchant/, partials/ condivisi: pwa, toast, levels)
  static/               # PWA merchant: manifest.webmanifest, sw.js (servito anche da GET /sw.js), icone
scripts/                # reset_db, seed_db, close_period, ecologi_check, zernio_check, replay_webhook, smoke_test_prod
tests/                  # pytest + conftest (SQLite in-memory); tests/unit/ = core puro senza DB
```

## Regole di lavoro

1. **Semplicità prima di tutto**: è una micro-SaaS, non un'architettura enterprise. Niente dipendenze o astrazioni non necessarie.
2. **Layer separati**: route → service → crud → modello. La business logic NON vive nelle route.
3. **Functional core / imperative shell, dentro lo stesso modulo**: ogni service è un *deep module* per funzionalità, diviso in due sezioni:
   - `# --- Core puro ---` in alto: funzioni deterministiche (calcoli, regole, trasformazioni). Possono dipendere **solo da Pydantic e dalla standard library**: niente `Session`, `httpx`, `fastapi`, niente `datetime.now()` (il tempo si passa come argomento). Sollevano **errori di dominio** (vedi `app/core/errors.py`), mai `HTTPException`.
   - `# --- Shell ---` in basso: I/O (DB, rete, orologio). Carica i dati, chiama il core, salva. Il più sottile possibile.
   - Le route traducono gli errori di dominio in risposte HTTP (handler globale).
   - I test del core stanno in `tests/unit/` e non usano DB né mock.
4. **Docstring in italiano** su ogni modulo, classe e funzione aggiunta o modificata: cosa fa, parametri non ovvi, cosa ritorna/solleva.
5. **Imita il codice esistente**: naming, stile dei template Tailwind, struttura dei test e delle fixture.
6. **Il progetto deve restare funzionante dopo ogni modifica**: gira `python -m pytest` prima di ogni commit.
7. **Branch**: si parte da `develop` (`feature/<nome>`; v0.3.0 su `feature/instagram-cards`), mai direttamente su `main`. Il push su `main` **deploya automaticamente in produzione**. Dettagli: [.agents/workflows/development.md](.agents/workflows/development.md).
8. **Niente segreti nel codice**: tutto passa da `.env` (locale) / env vars DigitalOcean (prod). `.env.example` documenta le variabili obbligatorie.
9. **Prima di una release**: segui [.agents/checklists/pre-release.md](.agents/checklists/pre-release.md).
10. **Decisioni architetturali importanti**: fermati e chiedi conferma all'utente prima di implementare.
11. **Aggiorna il planner**: a inizio lavoro leggi [.agents/planner/current.md](.agents/planner/current.md) e aggiornalo a fine sessione.

## Vincoli e trade-off accettati (non "sistemarli" senza chiedere)

- **Chiave Ecologi unica di piattaforma** (decisione 2026-10-09, sostituisce quella per-merchant del 2026-07-09): sta in env (`ECOLOGI_API_KEY`), il founder paga tutti gli alberi. I merchant non hanno account Ecologi.
- **Ecologi: due chiavi, un solo URL, nome del negozio pubblico** (2026-10-14): non esiste un sandbox, la prova è il flag `"test": true` sullo stesso `ECOLOGI_BASE_URL`; `ECOLOGI_TEST_MODE` sceglie tra `ECOLOGI_TEST_API_KEY` e `ECOLOGI_API_KEY` (nessun fallback, nessun blocco legato a `ENVIRONMENT`). Il `name` mandato a Ecologi è `<negozio> · <mese> <anno>` e compare nella foresta pubblica **senza gestione del consenso** (i merchant sono pochi e informati a voce). Si salva solo `treeUrl` in `TreePlanting.ecologi_ref`.
- **Piantumazione solo a fine periodo, lanciata a mano** (2026-10-09): `scripts/close_period` con anteprima, conferma e idempotenza (un negozio non può essere chiuso due volte per lo stesso mese). Il cron/endpoint admin arriverà più avanti riusando lo stesso core.
- **Cap globale sforato → blocco, non ripartizione** (2026-10-09): lo script mostra lo sforamento e chiede al founder se procedere.
- **Gli errori Ecologi non bloccano mai lo scan**: lo scan non chiama più Ecologi. Durante la chiusura, un errore su un negozio non blocca gli altri; il negozio resta non chiuso e si ritenta.
- **Auth merchant: Supabase in arrivo, oggi solo interfaccia** (2026-10-09): la verifica del token è dietro un'interfaccia con provider `dev` (locale/test). Il provider Supabase reale si collega in un rilascio successivo. Niente password nel nostro DB. Dal 2026-10-22 l'auth serve solo ai merchant.
- ~~**Iscrizione cliente obbligatoria, niente carte anonime né WhatsApp** (2026-10-09)~~ — **ANNULLATO il 2026-10-22**: la carta nasce da un DM Instagram, il cliente non ha account né autenticazione e vede la carta con un link segreto. Spariscono OTP cliente, wallet, QR `/join/{negozio}` e `Customer`. WhatsApp resta escluso.
- **Carta via DM Instagram con Zernio** (2026-10-22): trigger = DM con la parola chiave **unica di piattaforma** (`INSTAGRAM_CARD_KEYWORD`, default `CARTA`; maiuscole, accenti, punteggiatura ed emoji ignorati, corrispondenza esatta) oppure voce del menu persistente "🌳 La mia carta" (impostata all'onboarding solo se il menu del negozio è vuoto). Gli altri messaggi sono ignorati in silenzio. Commenti e storie → DM sono **fuori scope** (roadmap) ma il riconoscitore di trigger è separato per aggiungerli.
- **Risposta = una sola card** (2026-10-22): un invio per azione, generic template con titolo = nome del negozio (≤ 80 caratteri, validato anche in registrazione), sottotitolo fisso, un bottone "Apri la carta". **Nessun dato dinamico** nel messaggio: punti, livello e cashback solo nella pagina carta. Limiti di caratteri verificati nel core. Unico ripiego: testo fisso con il link se Meta rifiuta la card a un non follower (errore 2/1545133). La card **non si vede su Instagram desktop** (limite Meta): accettato, l'uso è in negozio da telefono.
- **Carta solo a chi segue il negozio** (2026-10-23, modifica la regola "card a tutti"): `message.sender.instagramProfile.isFollower` del webhook decide. `true` → card; `false` → **nessuna carta**, solo un testo fisso "per avere la carta segui @negozio, poi riscrivi CARTA" (`outcome` `follow_requested`, nessuna riga `Card`); `null` (dato non disponibile) → card, da rivedere nel collaudo finale con un profilo che segue e uno che non segue. Chi non segue non ha i vantaggi (cashback, punti, alberi). Il ripiego "testo con il link" resta solo come rete di sicurezza se Meta rifiuta comunque la card (2/1545133). Il blocco vale per tutti i negozi; opzione per singolo negozio e testo scelto dal merchant sono in roadmap.
- **QR "apri la chat" in negozio** (2026-10-23): link `https://ig.me/m/<username>` stampato come QR, fatto **a mano dal founder** su richiesta del merchant. Fuori dall'app.
- **Identità del cliente** (2026-10-22): una carta per coppia (negozio, IGSID). Dell'IGSID si salva solo l'**indice cieco** HMAC-SHA256 (`IGSID_HMAC_KEY`, chiave **non ruotabile** senza scollegare le carte); per rispondere si usa il `conversation.id` di Zernio. Nessuno username, nome, foto o testo dei messaggi salvato. Niente tabella `Customer`: l'IGSID è diverso per ogni account Instagram, un cliente "trasversale" tra negozi non esiste (si potrà aggiungere quando ci sarà un dato che vale tra negozi).
- **Link della carta** (2026-10-22): `/c/<token>` con token = HMAC(`CARD_LINK_KEY`, id carta + versione), mai salvato (nel DB solo l'hash); stesso link a ogni messaggio, revoca = versione +1. Mai l'IGSID nell'URL. Il token nel percorso è mascherato nei nostri log; i log di DigitalOcean sono accettati (il "segreto dopo #" è in roadmap per quando l'app cresce).
- **QR della pagina carta = id della carta** (2026-10-22), distinto dal token: lo legge solo lo scanner del merchant del negozio, una foto del QR non apre la carta. In chat non si manda nessun QR.
- **Zernio: chiave del merchant nel pilota** (2026-10-22): ogni merchant ha il suo account Zernio gratuito, incolla la sua chiave (validata con una chiamata reale, salvata cifrata AES-GCM con `ENCRYPTION_KEY`, mai restituita né loggata, cancellata allo scollegamento). Webhook configurato in automatico, **uno per negozio** con id opaco nel path e secret per negozio. `zernio_service.zernio_credentials_for(merchant)` è l'**unico** punto che sa da dove arriva la chiave: la migrazione alla chiave unica del founder (un `profileId` per negozio) cambierà solo quella funzione e l'onboarding.
- **Webhook sincrono e idempotente** (2026-10-22): dedup su `X-Zernio-Event-Id` (riga inserita per prima, conservata 7 giorni), risposta entro 5 s, timeout 3 s verso Zernio, **nessun nuovo tentativo** sugli invii (un 5xx può aver già consegnato: il cliente riscrive la parola chiave). Si risponde solo entro **24 h** dal `sentAt` del messaggio del cliente; nessun invio proattivo.
- **Standby (ManyChat o altra app proprietaria della conversazione)** (2026-10-22): nessuna carta né invio, solo rilevamento e avviso nel pannello del merchant perché scolleghi l'altra app.
- **Quota Zernio: contatore e avviso, nessun blocco nostro** (2026-10-22): `ZernioSendCounter` per ambito di quota (= team Zernio, oggi del merchant) e mese UTC, avviso al `ZERNIO_SEND_WARN_PERCENT` (75%) di `ZERNIO_MONTHLY_SEND_LIMIT` (10.000); oltre, è Zernio a fermare gli invii (403 gestito).
- **Errori Zernio** (2026-10-22): 401/403 chiave → stato "chiave non valida" nel pannello; 429/5xx → solo log.
- **Privacy** (2026-10-22): informativa in `/privacy` (bozza da far verificare al founder), linkata in fondo alla pagina carta. Conservazione: finché il cliente non chiede la cancellazione al negozio (che elimina la carta) o il negozio esce. DPA con i merchant, comando di cancellazione via DM e pulizia automatica in roadmap.
- **PWA solo merchant** (2026-10-22): manifest con `start_url` `/merchant/scanner` e scope `/merchant/`; la pagina carta del cliente non ha manifest né service worker.
- **`cryptography` torna** (2026-10-22, tolta in v0.2.0): serve la cifratura autenticata della chiave Zernio. Chiavi solo da env, l'app non parte se mancano.
- **Un solo modello di negozio** (2026-10-09): niente campo `mode`; "solo alberi" = conversione disattivata.
- **Modello dati: denaro, tempo, pool** (2026-10-12): soldi in **centesimi interi** (`*_cents`, mai float; euro solo ai bordi); timestamp **UTC aware** e mese **UTC** deciso in scrittura (`period` 'YYYY-MM'; niente fusi orari, lo scarto di 1-2 ore col mese italiano è accettato); il pool del mese è il contatore **`MerchantPool`** aggiornato a ogni scan nella stessa transazione (cache del registro `PointTransaction`, che resta fonte di verità; `close_period` si ferma se divergono); `TreePlanting` unica per `(merchant, period, test)` con snapshot `pool_points` ed `ecologi_ref`.
- **Provider `dev` e password dei merchant del seed** (2026-10-13): il provider `dev` tiene le password in memoria del processo, ma il seed gira in un processo separato dal server; per questo `DEV_AUTH_PASSWORD` (env, default `dev-password`) vale per ogni merchant non registrato in memoria. Solo locale/test: con `ENVIRONMENT=production` il provider `dev` non parte; la variabile non va impostata in produzione.
- **Merchant creato dall'admin senza `auth_user_id`** (2026-10-13): non può accedere né registrare la stessa email (409). Limite accettato fino a Supabase; "adottare" la riga alla registrazione senza email verificata sarebbe un buco di sicurezza (vedi roadmap).
- **Niente Alembic**: lo schema è gestito da `create_all()` all'avvio; il DB si resetta con gli script. Alembic tornerà quando i dati di produzione andranno preservati.
- Il vecchio prototipo in `feature/trees` è archivio, non mergiare.

## Approfondimenti

| Documento | Contenuto |
|---|---|
| [.agents/tickets/v0.3.0/README.md](.agents/tickets/v0.3.0/README.md) | Ticket di v0.3.0 (carta via DM Instagram), lavoro aperto |
| [.agents/tickets/v0.2.0/README.md](.agents/tickets/v0.2.0/README.md) | Ticket con cui è stata costruita v0.2.0 (storia e decisioni) |
| [.agents/architecture/overview.md](.agents/architecture/overview.md) | Architettura, modello dati, segreti, flussi (webhook, onboarding, scan), punto di aggancio Zernio, endpoint |
| [.agents/architecture/zernio-notes.md](.agents/architecture/zernio-notes.md) | Vincoli Zernio e Meta con le fonti (limiti, firma, retry, quota, standby) |
| [.agents/workflows/development.md](.agents/workflows/development.md) | Git flow, ciclo di sviluppo di una feature |
| [.agents/workflows/deploy.md](.agents/workflows/deploy.md) | Deploy DigitalOcean, env vars |
| [.agents/checklists/pre-release.md](.agents/checklists/pre-release.md) | Checklist prima del merge su main |
| [.agents/planner/roadmap.md](.agents/planner/roadmap.md) | Backlog e feature future |
| [.agents/planner/current.md](.agents/planner/current.md) | Stato corrente del lavoro |
