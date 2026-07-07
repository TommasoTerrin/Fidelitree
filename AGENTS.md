# Fidelitree — Guida per Coding Agent

> **Punto di ingresso unico** per qualsiasi coding agent (Claude Code, Codex, Gemini CLI, OpenCode, ...).
> Leggi questo file prima di toccare il codice. Approfondimenti in [`.agents/`](.agents/).

## Cos'è Fidelitree

Micro-SaaS di **carte fedeltà digitali con cashback** per commercianti.

Flusso: il cliente ottiene la carta da `/download_card` → la salva via WhatsApp → apre il link della carta (QR code univoco) → il merchant fa login, scannerizza il QR e aggiunge/rimuove credito cashback.

- Il **cliente finale NON si autentica**: l'UUID della carta funge da capability URL.
- Il **merchant** si autentica con telefono+password (JWT in cookie httpOnly).
- Gli endpoint amministrativi (`/api/merchant` CRUD) richiedono l'header `X-Admin-Key`.

## Stack

| Livello | Tecnologia |
|---|---|
| Backend | FastAPI + SQLModel (Python 3.12) |
| Frontend | Template Jinja2 + Vanilla JS (Tailwind via CDN, QR client-side) |
| Database | PostgreSQL su **Neon** (prod) / SQLite in-memory (test) |
| Hosting | **DigitalOcean App Platform** (Docker, auto-deploy da `main`) |

## Comandi essenziali

```bash
# Ambiente (Windows)
.venv\Scripts\activate
pip install -r requirements.txt

# Avvio locale con hot-reload (richiede .env — vedi .env.example)
python local_main.py

# Test (SQLite in-memory: NON toccano Neon, nessuna rete)
python -m pytest

# Utilità DB (ATTENZIONE: agiscono sul DATABASE_URL in .env)
python -m scripts.reset_db      # drop + ricrea schema (chiede conferma)
python -m scripts.seed_db       # merchant di test + link carte

# Smoke test post-deploy
python scripts/smoke_test_prod.py https://<app>.ondigitalocean.app <ADMIN_SECRET_KEY>
```

## Mappa del codice

```
app/
  main.py               # FastAPI app, engine DB, lifespan (create_all), router
  core/
    config.py           # Settings da .env — variabili obbligatorie: vedi .env.example
    security.py         # Fernet (password) + JWT (sessione merchant)
    dependencies.py     # get_session, get_current_merchant, require_admin_key
    utils/whatsapp_utils.py  # link wa.me pre-compilato
  models/models.py      # Merchant, Card (SQLModel)
  schemas/              # Pydantic request/response
  services/
    card_service.py     # business logic (creazione carta, update cashback)
    db_crud/            # accesso DB puro (merchant_crud, card_crud)
  routes/
    consumer/           # api + pagine pubbliche (download, vista carta)
    merchant/           # api + auth + pagine merchant (login, scanner, gestione)
  templates/            # Jinja2 (consumer/, merchant/)
scripts/                # reset_db, seed_db, smoke_test_prod
tests/                  # pytest + conftest (fixture SQLite in-memory)
```

## Regole di lavoro

1. **Semplicità prima di tutto**: è una micro-SaaS, non un'architettura enterprise. Niente dipendenze o astrazioni non necessarie.
2. **Layer separati**: route → service → crud → modello. La business logic NON vive nelle route.
3. **Il progetto deve restare funzionante dopo ogni modifica**: gira `python -m pytest` prima di ogni commit.
4. **Branch**: parti sempre da `develop` (`feature/<nome>`), mai lavorare direttamente su `main`. Il push su `main` **deploya automaticamente in produzione**. Dettagli: [.agents/workflows/development.md](.agents/workflows/development.md).
5. **Niente segreti nel codice**: tutto passa da `.env` (locale) / env vars DigitalOcean (prod). `.env.example` documenta le variabili obbligatorie.
6. **Prima di una release**: segui [.agents/checklists/pre-release.md](.agents/checklists/pre-release.md).
7. **Decisioni architetturali importanti**: fermati e chiedi conferma all'utente prima di implementare.
8. **Aggiorna il planner**: a inizio lavoro leggi [.agents/planner/current.md](.agents/planner/current.md) e aggiornalo a fine sessione.

## Vincoli e trade-off accettati (non "sistemarli" senza chiedere)

- **Password merchant cifrate con Fernet** (reversibili), non hashate: scelta consapevole finché non esiste un flusso di recupero password. Nel roadmap.
- **Niente Alembic**: lo schema è gestito da `create_all()` all'avvio; il DB si resetta con gli script. Alembic tornerà quando i dati di produzione andranno preservati.
- **Tree Points rimossi dalla release 1**: la logica storica di piantumazione alberi (Digital Humani/Ecologi) vive nel branch di archivio `feature/trees` e andrà **re-implementata** sopra il nuovo `develop`, non mergiata.

## Approfondimenti

| Documento | Contenuto |
|---|---|
| [.agents/architecture/overview.md](.agents/architecture/overview.md) | Architettura, modello dati, flussi, auth |
| [.agents/workflows/development.md](.agents/workflows/development.md) | Git flow, ciclo di sviluppo di una feature |
| [.agents/workflows/deploy.md](.agents/workflows/deploy.md) | Deploy DigitalOcean, env vars, verifica Neon |
| [.agents/checklists/pre-release.md](.agents/checklists/pre-release.md) | Checklist prima del merge su main |
| [.agents/planner/roadmap.md](.agents/planner/roadmap.md) | Backlog e feature future |
| [.agents/planner/current.md](.agents/planner/current.md) | Stato corrente del lavoro |
