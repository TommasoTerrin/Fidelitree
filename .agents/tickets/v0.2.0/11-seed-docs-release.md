# 11 — Seed, smoke test, documentazione e preparazione release

## Obiettivo
Chiudere v0.2.0: script di supporto allineati al nuovo modello, documentazione `.agents/` aggiornata, checklist di release e collaudo manuale. **Nessuna nuova funzionalità.**

## Contesto
`scripts/seed_db.py` crea merchant con `MERCHANT_PASSWORD`; `reset_db.py` ricrea lo schema; `smoke_test_prod.py` verifica endpoint pubblici e admin; `run_test_flow.py` nella root è un flusso di prova. Il DB (Neon o Supabase) è resettabile: nessuna migrazione dati.

## Dipendenze
01–10.

## Modifiche
1. **`scripts/seed_db.py`**: crea tramite `DevAuthProvider` (solo se `AUTH_PROVIDER=dev`, altrimenti rifiuta con messaggio chiaro) 2 merchant di test **approvati** (email fittizie, soglie diverse, uno con conversione disattivata), 2 clienti e le carte, e alcuni scan per avere pool ai livelli nessuno/bronzo/oro: i punti si aggiungono **tramite `add_tree_points`** (mai inserendo `PointTransaction` a mano), così registro e contatore `MerchantPool` restano coerenti e `pool_mismatches` è vuoto. Stampa link: `/join/{id}`, `/wallet`, login per ciascuna identità. Idempotente.
2. **`scripts/reset_db.py`**: invariato nel comportamento; verifica che funzioni con il nuovo schema.
3. **`scripts/smoke_test_prod.py`**: aggiorna agli endpoint nuovi (`/health` con `version`, `/customer/login`, `/join/{id}` per un merchant esistente se fornito, `/merchant/login`, endpoint admin con `X-Admin-Key`); rimuovi i riferimenti a `/download_card` e `/api/get-card`. Il test **non** deve piantare alberi.
4. **`run_test_flow.py`**: aggiorna o rimuovi se obsoleto (decidi leggendolo; se rimosso, motiva nel commit/`current.md`).
5. **Documentazione**:
   - `AGENTS.md`: rimuovi il banner di transizione, riallinea mappa del codice, auth, DB; tieni le decisioni;
   - `.agents/architecture/overview.md`: riscrivi modello dati, flussi (cliente: join→wallet; merchant: scan→conversione; chiusura mensile), auth, endpoint, scelte tecniche; aggiungi il diagramma del pool;
   - `.agents/workflows/deploy.md`: variabili nuove (`ECOLOGI_API_KEY`, `ECOLOGI_GLOBAL_MONTHLY_CAP`, `TIER_*`, `AUTH_PROVIDER`, `ENVIRONMENT`), rimosse (`ENCRYPTION_KEY`, `MERCHANT_PASSWORD`), e come lanciare `scripts.close_period` in produzione;
   - `.agents/checklists/pre-release.md`: nuovo test manuale del flusso completo (vedi sotto) e voce di verifica `ENVIRONMENT=production` ≠ `AUTH_PROVIDER=dev`;
   - `.agents/planner/roadmap.md`: release 2 marcata come assorbita in v0.2.0; changelog; backlog aggiornato (provider Supabase reale, endpoint admin/cron per `close_period`, ripartizione automatica del cap, pagina pubblica contatore alberi, dashboard merchant, rimozione voce Clerk e "Sicurezza password" ora superate da Supabase);
   - `.agents/planner/current.md`: stato finale e prossimi passi (collegare Supabase, DB, deploy).
6. **Memoria progetto**: nessuna azione (la gestisce l'assistente a fine sessione).

## File coinvolti
`scripts/*`, `run_test_flow.py`, `AGENTS.md`, `.agents/**`, `tests/test_scripts.py` (nuovo, se serve).

## Test da superare
- `seed()` su SQLite in-memory (engine di test): crea 2 merchant approvati, 2 clienti, carte e movimenti; **rieseguito non duplica nulla**.
- Dopo il seed, `plan_period_closure` sui pool reali del seed produce un piano con almeno un negozio a livello oro e uno senza livello (verifica che il seed sia utile al collaudo).
- Lo smoke test, puntato su un `TestClient`/app locale, passa tutti i controlli e non invoca Ecologi.
- Nessun file del repo contiene più `ENCRYPTION_KEY`, `MERCHANT_PASSWORD`, `download_card`, `get-card`, `trees_planted`, `monthly_tree_cap` (grep di verifica; eccezioni solo nel changelog storico).
- `python -c "import app.main"` e suite completa verdi (`python -m pytest`), versione `/health` = `pyproject.toml`.

## Collaudo manuale (da eseguire e spuntare nella checklist)
1. `python -m scripts.reset_db` → `python -m scripts.seed_db`.
2. Cliente: `/join/{id}` → login OTP (`000000`) → carta compare nel wallet → installa PWA da telefono.
3. Merchant: login → scan QR carta → +60 tree points → toast conversione → pool aggiornato nella pagina e nella carta del cliente.
4. Merchant non approvato: registra nuovo account, verifica che lavori ma **non** compaia in `close_period`.
5. `python -m scripts.close_period` (test mode): anteprima corretta, conferma, seconda esecuzione senza effetti; prova con `--cap` basso per vedere il blocco.

## Fuori scope
Provider Supabase reale, deploy, cron, migrazione DB su Supabase (rilascio successivo).

## Definition of Done
Tutta la suite verde, checklist manuale completata, documentazione coerente con il codice, `pyproject.toml` a `0.2.0`; pronto per merge e tag `v0.2.0` secondo `pre-release.md`.
