# Storico di v0.2.0 (pool del negozio, auth, wallet cliente)

> Registro breve del lavoro svolto, spostato qui da `planner/current.md` il 2026-10-23 quando il lavoro è passato a
> v0.3.0. Serve a chi vuole ripercorrere i passi. La specifica dei singoli ticket è nei file `NN-*.md` di questa
> cartella; le decisioni sono in AGENTS.md.
>
> **Esito**: v0.2.0/v0.2.1 (0.2.1 = logo e icone PWA) è rimasta su `develop` e **non è mai stata rilasciata né
> taggata**: è assorbita da v0.3.0 (decisione 2026-10-22). Dei ticket 08, 09 e 10 restano in uso solo alberi, pool,
> cashback, auth merchant e PWA merchant; OTP cliente, wallet e `/join` vengono rimossi dal ticket 09 di v0.3.0.

## Cronologia

- **2026-10-09** — fase di analisi e pianificazione completata: decisioni in AGENTS.md, 11 ticket.
- Ticket **01 (versionamento)**: `pyproject.toml`, `app/version.py`, `version` in `/health`.
- Ticket **02 (modelli dati, config ed errori di dominio) — 2026-10-12**: nuovo schema (`Customer`, `PointTransaction`,
  `MerchantPool`, `TreePlanting` ridefinita, centesimi, UTC aware), `enums`/`money`/`clock`/`errors`, handler
  `DomainError`, config nuova; 100 test verdi.
- Ticket **03 (core puro: livelli, periodi, piano di chiusura) — 2026-10-12**: `app/services/tree_service.py` solo core;
  `tests/unit/test_pool.py`; 141 test. `update_tree_points` (transitoria) spostata in `card_service`.
- Ticket **04 (scan: registro movimenti e conversione) — 2026-10-12**: `card_service` con core (`compute_conversion`,
  `apply_*_delta`) e shell (`add_tree_points` transazionale con pool atomico, `update_cashback`),
  `tree_service.pool_points`/`current_pool_progress`, `ScanResponse`; 164 test.
- Ticket **05 (Ecologi di piattaforma e `close_period`) — 2026-10-12**: `ecologi_service` con chiave unica e idempotency
  key deterministica, `tree_service.close_period` (blocco su divergenze contatore/registro e su cap, snapshot, commit
  per riga), `scripts/close_period.py`; 192 test.
- Ticket **06 (interfaccia auth e provider dev) — 2026-10-12**: `app/core/auth.py` (`AuthProvider`, `DevAuthProvider`,
  stub `SupabaseAuthProvider`, `get_auth_provider`), `AuthError` → 401, dependency `get_auth_identity`/
  `get_current_merchant`/`get_current_customer`; `cryptography` rimosso (poi tornato in v0.3.0); 210 test.
- Ticket **07 (auth merchant, approvazione e admin) — 2026-10-13**: `merchant_service` (core `validate_registration` +
  shell), `POST /merchant/register`, login email+password via provider, `/me` con `is_approved` e soglie effettive,
  `POST /api/merchant/{id}/approve`, override soglie con controllo di coerenza; `ConflictError` (409) e
  `InvalidInputError` (400); 246 test. Variabili Ecologi di test distinte (poi riviste dal ticket 12).
- Ticket **08 (backend cliente: OTP, join, wallet, proprietà carta) — 2026-10-13**: `customer_service`, OTP cliente,
  `join`, wallet, `/api/card/{id}` solo al proprietario; rimossi `/api/get-card`, `/download_card`, WhatsApp e cliente
  segnaposto; 287 test. *(Sostituito da v0.3.0.)*
- Ticket **09 (frontend merchant) — 2026-10-13**: registrazione, impostazioni con stato approvazione, anteprima
  conversione, soglie in sola lettura e QR del negozio, blocco "Pool del negozio" in `update_card.html`; 301 test.
- Ticket **10 (frontend cliente e PWA) — 2026-10-13**: pagine cliente `login/join/wallet/card`, partial condivisi
  `pwa/toast/levels`, manifest e service worker, `card_service.conversion_progress`; 326 test. *(Parte cliente
  sostituita da v0.3.0; la PWA resta solo per il merchant.)*
- Ticket **11 (seed, smoke test, documentazione, release) — 2026-10-13**: `seed_db` riscritto (iniettabile, solo
  `AUTH_PROVIDER=dev`, idempotente), `DEV_AUTH_PASSWORD`, `smoke_test_prod` con client iniettabile, `run_test_flow.py`
  rimosso, `.env.example` versionato, docs riallineate; 339 test. Provato a mano su SQLite + uvicorn. Tutto il lavoro
  01–11 in un commit su `rinascimento`.
- **2026-10-14** — aggiunti i ticket 12–13 dopo il confronto con la documentazione Ecologi (non esiste un sandbox:
  il test è il flag `"test": true` sullo stesso URL).
  - Ticket **12 (Ecologi: ambienti e nome del negozio)**: un solo URL e due chiavi scelte da `ECOLOGI_TEST_MODE`,
    `extract_ref` = `treeUrl`, `tree_service.planting_name` ("Bar Demo · ottobre 2026"); 354 test.
  - Ticket **13 (script `ecologi_check`)**: chiamata sempre con `test=true`, chiave solo con ultimi 4 caratteri; 360 test.
- **2026-10-20** — logo vero (`feature/logo`, mergiato su `develop`): loghi in `app/static/loghi/`, icone PWA; versione
  0.2.1.
- **2026-10-22** — il merge di v0.2.1 su `main` viene **annullato**: parte v0.3.0.

## Debiti e collaudi rimasti aperti alla chiusura

- Collaudo manuale di `ecologi_check` (chiave di test e reale) e di `close_period` in test mode con `treeUrl` salvato:
  **ancora da fare**, a cura del founder (riportato nel planner corrente).
- Collaudo manuale della checklist `pre-release.md`, inclusa la PWA su telefono (serve HTTPS o tunnel).
- Un merchant creato dall'admin non ha `auth_user_id` e la sua email non si può registrare (409): si risolve con
  Supabase (roadmap).
- `create_all()` non migra i DB esistenti: serve `scripts.reset_db`.
- `reset_db`/`seed_db` agiscono sul `DATABASE_URL` del `.env`: per il collaudo usare un SQLite usa-e-getta.
- La vecchia "Release 2 — Tree Points per-merchant" non è mai stata rilasciata: assorbita da v0.2.0 (codice su
  `rinascimento` dal commit `544fb4e`).
