# Fidelitree — Guida per Coding Agent

> **Punto di ingresso unico** per qualsiasi coding agent (Claude Code, Codex, Gemini CLI, OpenCode, ...).
> Leggi questo file prima di toccare il codice. Approfondimenti in [`.agents/`](.agents/).

> **Versione corrente: v0.2.1** (pool del negozio, auth, wallet cliente + logo e icone PWA), su `develop`: non ancora su `main` né in produzione.
> I ticket con cui è stata costruita sono archiviati in [`.agents/tickets/v0.2.0/`](.agents/tickets/v0.2.0/README.md)
> (storia e decisioni, non lavoro aperto). Lo stato del lavoro è in [`.agents/planner/current.md`](.agents/planner/current.md).

## Contesto di business

**Fidelitree** è una micro-SaaS solo-founder di **carte fedeltà digitali che piantano alberi veri** per piccoli negozi (bar, forni, fioristi...).

- **Per il cliente finale** è una carta fedeltà nel telefono (wallet PWA) con cashback e *tree points*.
- **Per il merchant** è uno strumento di fidelizzazione con una storia di marketing pronta: *"questo mese, insieme ai nostri clienti, abbiamo piantato 5 alberi"*.
- **Per il founder** l'app è **gratuita per i merchant**: i ricavi arrivano da consulenza/gestione social e contenuti IA venduti ai merchant (modello agenzia). Gli alberi sono l'hook narrativo del build-in-public e **sono pagati dal founder** (Ecologi, ~0,80 €/albero, chiave API unica di piattaforma).

### Come funziona (v0.2.0)

1. **Il cliente si iscrive una volta** (email + codice OTP) e ha un **wallet** con tutte le sue carte, una per negozio.
2. In negozio inquadra il **QR statico del negozio** (`/join/{negozio}`) → la carta viene creata (o aperta) e compare nel wallet.
3. Il merchant scansiona il QR della carta del cliente e aggiunge **tree points** (e, a sua discrezione, **cashback** in €).
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
| Frontend | Template Jinja2 + Vanilla JS (Tailwind via CDN, QR client-side), wallet cliente come PWA |
| Database | PostgreSQL su **Neon** oggi, **Supabase** in un rilascio successivo / SQLite in-memory (test) e su file (collaudo locale) |
| Auth | **Supabase Auth** in arrivo: email+password per merchant, OTP email per clienti. In v0.2.0 solo interfaccia + provider `dev` (locale/test; rifiutato con `ENVIRONMENT=production`) |
| Alberi | Ecologi Impact API, **chiave unica di piattaforma** (env) |
| Hosting | **DigitalOcean App Platform** (Docker, auto-deploy da `main`) |

## Versionamento

- **Fonte unica della versione**: `[project] version` in `pyproject.toml` (SemVer 0.x).
- A ogni rilascio: bump in `pyproject.toml` → merge su `main` → tag git `vX.Y.Z` con lo stesso valore.
- `v0.1.0` = MVP cashback. `v0.2.0` = pool del negozio + auth + wallet (assorbe la vecchia "Release 2", mai andata in produzione).

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
python -m scripts.seed_db       # 2 merchant, 2 clienti, carte e scan di prova (solo AUTH_PROVIDER=dev)

# Chiusura mensile: pianta gli alberi del pool (anteprima, conferma, idempotente)
python -m scripts.close_period [--month AAAA-MM] [--cap N] [--yes]

# Verifica la chiave Ecologi: chiamata reale con test=true, nessun addebito
python -m scripts.ecologi_check [--trees N] [--merchant-name NOME] [--month AAAA-MM]

# Smoke test post-deploy (non pianta alberi)
python scripts/smoke_test_prod.py https://<app>.ondigitalocean.app <ADMIN_SECRET_KEY>
```

## Mappa del codice

```
app/
  main.py               # FastAPI app, engine DB, lifespan (create_all), router
  core/
    config.py           # Settings da .env — variabili obbligatorie: vedi .env.example
    auth.py             # interfaccia AuthProvider + provider dev (Supabase: stub)
    security.py         # JWT (sessione, usato dal provider dev)
    dependencies.py     # get_session, get_auth_identity, get_current_merchant/customer, require_admin_key
    errors.py enums.py money.py clock.py   # errori di dominio, enum (Level...), centesimi↔euro, utc_now
  models/models.py      # tabelle SQLModel
  version.py            # versione letta da pyproject.toml (esposta da /health)
  schemas/              # Pydantic request/response
  services/             # un modulo per funzionalità: core puro + shell (vedi sotto)
    card_service.py     # carte, cashback, conversione tree points → cashback
    customer_service.py # cliente: iscrizione al negozio (join), wallet, proprietà della carta
    tree_service.py     # pool del negozio, livelli, chiusura periodo
    ecologi_service.py  # client Impact API Ecologi
    db_crud/            # accesso DB puro
  routes/
    consumer/           # api + pagine cliente
    merchant/           # api + auth + pagine merchant
  templates/            # Jinja2 (consumer/, merchant/, partials/ condivisi: pwa, toast, levels)
  static/               # PWA: manifest.webmanifest, sw.js (servito anche da GET /sw.js), icone
scripts/                # reset_db, seed_db, close_period, ecologi_check, smoke_test_prod
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
7. **Branch**: per v0.2.0 si lavora su `rinascimento`; in generale si parte da `develop` (`feature/<nome>`), mai direttamente su `main`. Il push su `main` **deploya automaticamente in produzione**. Dettagli: [.agents/workflows/development.md](.agents/workflows/development.md).
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
- **Auth: Supabase in arrivo, in v0.2.0 solo interfaccia** (2026-10-09): la verifica del token è dietro un'interfaccia con provider `dev` (locale/test). Il provider Supabase reale si collega in un rilascio successivo. Niente password nel nostro DB (sparisce Fernet).
- **Iscrizione cliente obbligatoria, niente carte anonime né WhatsApp** (2026-10-09): la carta è visibile solo al suo proprietario; il merchant la gestisce via scan.
- **Un solo modello di negozio** (2026-10-09): niente campo `mode`; "solo alberi" = conversione disattivata.
- **Modello dati: denaro, tempo, pool** (2026-10-12): soldi in **centesimi interi** (`*_cents`, mai float; euro solo ai bordi); timestamp **UTC aware** e mese **UTC** deciso in scrittura (`period` 'YYYY-MM'; niente fusi orari, lo scarto di 1-2 ore col mese italiano è accettato); il pool del mese è il contatore **`MerchantPool`** aggiornato a ogni scan nella stessa transazione (cache del registro `PointTransaction`, che resta fonte di verità; `close_period` si ferma se divergono); `TreePlanting` unica per `(merchant, period, test)` con snapshot `pool_points` ed `ecologi_ref`.
- **Provider `dev` e password dei merchant del seed** (2026-10-13): il provider `dev` tiene le password in memoria del processo, ma il seed gira in un processo separato dal server; per questo `DEV_AUTH_PASSWORD` (env, default `dev-password`) vale per ogni merchant non registrato in memoria. Solo locale/test: con `ENVIRONMENT=production` il provider `dev` non parte; la variabile non va impostata in produzione.
- **Merchant creato dall'admin senza `auth_user_id`** (2026-10-13): non può accedere né registrare la stessa email (409). Limite accettato fino a Supabase; "adottare" la riga alla registrazione senza email verificata sarebbe un buco di sicurezza (vedi roadmap).
- **Niente Alembic**: lo schema è gestito da `create_all()` all'avvio; il DB si resetta con gli script. Alembic tornerà quando i dati di produzione andranno preservati.
- Il vecchio prototipo in `feature/trees` è archivio, non mergiare.

## Approfondimenti

| Documento | Contenuto |
|---|---|
| [.agents/tickets/v0.2.0/README.md](.agents/tickets/v0.2.0/README.md) | Ticket con cui è stata costruita v0.2.0 (storia e decisioni) |
| [.agents/architecture/overview.md](.agents/architecture/overview.md) | Architettura, modello dati, diagramma del pool, flussi, auth, endpoint |
| [.agents/workflows/development.md](.agents/workflows/development.md) | Git flow, ciclo di sviluppo di una feature |
| [.agents/workflows/deploy.md](.agents/workflows/deploy.md) | Deploy DigitalOcean, env vars |
| [.agents/checklists/pre-release.md](.agents/checklists/pre-release.md) | Checklist prima del merge su main |
| [.agents/planner/roadmap.md](.agents/planner/roadmap.md) | Backlog e feature future |
| [.agents/planner/current.md](.agents/planner/current.md) | Stato corrente del lavoro |
