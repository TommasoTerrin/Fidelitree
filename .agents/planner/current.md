# Stato corrente

> Aggiorna questo file a inizio e fine sessione di lavoro.
> Item completati → spostali nel changelog di `roadmap.md`.

## In corso

- **v0.2.0 — Pool del negozio, auth, wallet cliente** (branch `rinascimento`).
  Fase di analisi e pianificazione **completata il 2026-10-09**: decisioni in AGENTS.md,
  11 ticket in [.agents/tickets/v0.2.0/](../tickets/v0.2.0/README.md).
  Ticket **01 (versionamento) completato**: `pyproject.toml`, `app/version.py`, `version` in `/health`.
  Ticket **02 (modelli dati, config ed errori di dominio) completato il 2026-10-12**: nuovo schema
  (`Customer`, `PointTransaction`, `MerchantPool`, `TreePlanting` ridefinita, centesimi, UTC aware), `enums`/`money`/`clock`/`errors`,
  handler `DomainError`, config nuova; 100 test verdi.
  Ticket **03 (core puro: livelli, periodi, piano di chiusura) completato il 2026-10-12**:
  `app/services/tree_service.py` contiene solo il core; `tests/unit/test_pool.py`; 141 test verdi.
  `update_tree_points` (transitoria) è stata spostata in `card_service` (→ sostituita dal ticket 04).
  Ticket **04 (scan: registro movimenti e conversione) completato il 2026-10-12**: `card_service` con core
  (`compute_conversion`, `apply_*_delta`) e shell (`add_tree_points` transazionale con pool atomico, `update_cashback`),
  `tree_service.pool_points`/`current_pool_progress`, `ScanResponse`; `tests/test_scan.py`, `tests/unit/test_conversion.py`; 164 test verdi.
  Ticket **05 (Ecologi di piattaforma e `close_period`) completato il 2026-10-12**: `ecologi_service` con chiave unica
  e idempotency key deterministica, `tree_service.close_period` (blocco su divergenze contatore/registro e su cap,
  snapshot, commit per riga), `scripts/close_period.py`; `tests/test_close_period.py`; 192 test verdi.
  Ticket **06 (interfaccia auth e provider dev) completato il 2026-10-12**: `app/core/auth.py` (`AuthProvider`,
  `DevAuthProvider`, stub `SupabaseAuthProvider`, `get_auth_provider`), `AuthError` → 401, dependency
  `get_auth_identity`/`get_current_merchant`/`get_current_customer` via `auth_user_id` (cookie o Bearer);
  `cryptography` rimosso da requirements e venv (`python-jose` senza extra); 210 test verdi.
  Ticket **07 (auth merchant, approvazione e admin) completato il 2026-10-13**: `merchant_service` (core
  `validate_registration` + shell `register_merchant`/`login_merchant`/update), `POST /merchant/register` e login
  email+password via provider, `/me` con `is_approved` e soglie effettive, `POST /api/merchant/{id}/approve`, override
  soglie con controllo di coerenza, `create_test_merchant` rimosso; nuovi `ConflictError` (409) e `InvalidInputError` (400);
  246 test verdi. Inoltre: variabili Ecologi **di test** distinte (`ECOLOGI_TEST_API_KEY`, `ECOLOGI_TEST_BASE_URL`),
  usate quando `ECOLOGI_TEST_MODE=true`; chiave/URL reali solo con `false`.
  Ticket **08 (backend cliente: OTP, join, wallet, proprietà carta) completato il 2026-10-13**: `customer_service`
  (core `normalize_email`/`safe_next_path`/`build_wallet` + shell `get_or_create_customer`/`join_merchant`/`list_wallet`/`get_owned_card`),
  `POST /api/customer/otp/{request,verify}`, `GET /customer/logout`, `POST /api/customer/join/{id}`, `GET /api/customer/wallet`,
  `/api/card/{id}` e `/card/{id}` solo al proprietario (altrui → 404, anonimo → 401 / redirect 303 al login con `next`),
  `get_current_customer` crea il cliente al primo accesso; rimossi `/api/get-card`, `/download_card`, WhatsApp e cliente segnaposto;
  287 test verdi. Le pagine `join`/`wallet`/`login` sono **segnaposto minimi** (la UI vera è del ticket 10).
  Ticket **09 (frontend merchant) completato il 2026-10-13**: `GET /merchant/register` e template ricreato (email, password,
  telefono facoltativo, senza Ecologi); `settings.html` con stato approvazione, anteprima conversione, soglie effettive in sola lettura
  e QR del negozio (`/join/{id}`, scarica/stampa); `update_card.html` con blocco "Pool del negozio" e toast di conversione;
  le route passano `pool`/`thresholds`/`join_path` dai service; 301 test verdi.
  Ticket **10 (frontend cliente e PWA) completato il 2026-10-13**: `consumer/{login,join,wallet,card}.html` reali
  (login OTP a due passi con toast e promemoria `000000` solo con `AUTH_PROVIDER=dev`; join con redirect alla carta e
  pagina 404 amichevole; wallet con medaglia e mini-barra del negozio; carta con saldo personale, "Ancora X punti per € Y",
  blocco "Il progetto del negozio" e livello massimo), partial condivisi `partials/{pwa,toast,levels}.html`,
  `app/static/{manifest.webmanifest,sw.js,icon.svg,apple-touch-icon.png}`, `GET /sw.js` con scope `/`,
  `card_service.conversion_progress` (core puro); `download.html` rimosso; 326 test verdi.
  Il service worker mette in cache solo la shell statica (nessuna pagina né API autenticata).
  Ticket **11 (seed, smoke test, documentazione, release) completato il 2026-10-13**: `seed_db` riscritto (`seed(session)`
  iniettabile, solo `AUTH_PROVIDER=dev`, idempotente; Bar Demo oro con conversione + Forno Solo Alberi senza livello,
  scan solo via `add_tree_points`, `pool_mismatches` vuoto); `DEV_AUTH_PASSWORD` (env) perché i merchant del seed
  possano accedere dal server (il provider dev tiene le password in memoria del processo); `smoke_test_prod` con client
  HTTP iniettabile, copre `/health.version`, pagine cliente/merchant, `/join/{id}`, PWA, admin con e senza chiave, non pianta
  alberi; `run_test_flow.py` **rimosso** (obsoleto: login per telefono, `add-point`, `planted_now`, UUID fissi);
  `.env.example` ora versionato (`!.env.example` nel `.gitignore`); docs riallineate (AGENTS.md senza banner di transizione,
  overview con diagramma del pool, deploy con `close_period` e collaudo locale, pre-release, roadmap, README);
  `tests/test_scripts.py`; 339 test verdi. Provato a mano su SQLite + uvicorn: reset, seed (rilanciato), login merchant da
  processo diverso, OTP cliente, scan, registrazione non approvata, smoke test, anteprima `close_period`.
  **v0.2.0 pronta al merge.** Tutto il lavoro dei ticket 01–11 è in un unico commit su `rinascimento`.
  **⏭️ PROSSIMO (a mano, in ordine):**
  1. Collaudo manuale della checklist `pre-release.md` (inclusa la **PWA su telefono**: installazione in Home e apertura standalone; serve HTTPS o un tunnel).
  2. Se esiste il logo vero, sostituire l'icona provvisoria (`app/static/icon.svg`, `apple-touch-icon.png`).
  3. Merge su `main` + tag `v0.2.0` secondo `pre-release.md` (il push su `main` deploya in produzione); prima `reset_db` del DB (i dati v0.1.0 non si migrano).
  **Debito noto:**
  - un merchant creato dall'admin non ha `auth_user_id` e la sua email non si può registrare (409): si risolve col collegamento Supabase (roadmap);
  - DB esistenti: `create_all()` non migra, serve `scripts.reset_db`;
  - `reset_db`/`seed_db` agiscono sul `DATABASE_URL` del `.env` (oggi Neon): per il collaudo usa SQLite usa-e-getta (`deploy.md`).
- La vecchia "Release 2 — Tree Points per-merchant" **non verrà mai rilasciata**: è assorbita da v0.2.0
  (il codice su `rinascimento` parte dal commit `544fb4e`, che la contiene).

## Dopo v0.2.0 (dettagli in `roadmap.md`)

- Collegare Supabase (progetto, DB, provider auth reale al posto di `dev`; collegare i merchant creati dall'admin).
- Endpoint admin/cron per `close_period` quando i negozi superano i 10-20.
- Pagina pubblica contatore alberi, poi lancio build-in-public e caccia ai primi 3-5 negozi pilota.

## Note per chi riprende il lavoro

- Regole di business e vincoli: AGENTS.md ("Contesto di business" e "Vincoli e trade-off").
- Convenzioni di codice (functional core / imperative shell, docstring italiane): AGENTS.md regola 3-5 e README dei ticket.
- I test girano offline (SQLite in-memory, Ecologi mockato): `python -m pytest`; il core puro in `tests/unit/`.
- La vecchia logica alberi/Telegram è in `feature/trees` (branch di archivio, non mergiare).
