# 05 — Ecologi di piattaforma e chiusura del periodo (`close_period`)

## Obiettivo
Piantare gli alberi del mese con la **chiave Ecologi unica del founder**, tramite uno script manuale con **anteprima, conferma e idempotenza**. Il codice deve essere riusabile dal futuro endpoint admin/cron.

## Contesto
`ecologi_service.purchase_trees(api_key, number, name)` usa oggi la chiave del merchant e genera un `Idempotency-Key` casuale a ogni chiamata (un retry dopo timeout potrebbe piantare due volte). `validate_api_key` serviva alla registrazione merchant e non serve più. Decisioni: il founder lancia la chiusura a mano; cap globale sforato → lo script si ferma e chiede; un errore su un negozio non blocca gli altri.

## Dipendenze
03, 04.

## Modifiche
1. **`app/services/ecologi_service.py`**:
   - `purchase_trees(number, name=None, idempotency_key=None)` usa `settings.ECOLOGI_API_KEY`; se vuota → `EcologiError("Chiave Ecologi di piattaforma non configurata")`.
   - `purchase_trees` ritorna la risposta JSON di Ecologi (come oggi); da lì si ricava `ecologi_ref` (identificativo dell'acquisto, se presente nella risposta, altrimenti `None`).
   - L'`Idempotency-Key` è quello passato (default: uuid casuale). Per la chiusura sarà **deterministico e distinto per modalità**: `f"fidelitree-{merchant_id}-{period}"` in produzione, `f"fidelitree-test-{merchant_id}-{period}"` con `ECOLOGI_TEST_MODE=true`. Così un retry non pianta due volte, e una prova non "occupa" la chiave della chiusura vera (altrimenti Ecologi potrebbe rispondere con l'esito in cache della prova senza piantare).
   - Rimuovi `validate_api_key` e il parametro `api_key`.
2. **`app/services/tree_service.py`**, sezione shell:
   - `build_pools(session, period) -> list[PoolInput]`: solo merchant **`is_approved`**; punti letti dal contatore con `pool_points(session, merchant_id, period)` (0 se manca la riga; **nessuna `SUM` sul registro**); soglie via `resolve_thresholds` con default da `settings.TIER_*` e override del merchant.
   - `closed_merchant_ids(session, period, test: bool) -> set[int]`: merchant con una riga `TreePlanting` per quel `(period, test)`. Una chiusura di prova **non** esclude la chiusura vera (e viceversa).
   - `pool_mismatches(session, period) -> list[PoolMismatch]` (`PoolMismatch`: `merchant_id`, `counter`, `ledger`): confronta `MerchantPool.points` con `SUM(delta)` dei movimenti `kind='scan'` con quel `period`, per i merchant approvati. Il registro è la fonte di verità: ogni differenza è una deviazione da segnalare.
   - `close_period(session, period, *, global_cap, confirm: Callable[[ClosurePlan], bool], now) -> ClosureReport`: **prima controlla `pool_mismatches`: se non è vuoto non pianta nulla** e il report contiene le divergenze (si spendono soldi veri, non si agisce su un contatore dubbio). Poi costruisce il piano con `plan_period_closure`; **se `exceeds_cap` e la callback `confirm` non lo autorizza non pianta nulla**; per ogni riga con `trees > 0` chiama Ecologi e, **solo a successo**, scrive `TreePlanting(period, level, tree_count, pool_points=<punti della riga del piano>, ecologi_ref, test=settings.ECOLOGI_TEST_MODE)` con commit per riga (`pool_points` è lo snapshot: il contatore può cambiare dopo la chiusura per una correzione tardiva). Errore Ecologi su un negozio → riga marcata `failed` nel report, si continua con gli altri. `ClosureReport` (Pydantic) elenca per negozio `planted` / `failed` / `skipped` e le eventuali `mismatches`.
3. **`scripts/close_period.py`** (shell sottile, stile degli script esistenti): `python -m scripts.close_period [--month YYYY-MM] [--cap N] [--yes]`.
   - Default mese = mese precedente (`previous_period(utc_now().date())`).
   - Se ci sono `pool_mismatches`: li stampa in evidenza (negozio, contatore, registro) ed esce con codice ≠ 0 **senza piantare**, anche con `--yes`.
   - Stampa tabella anteprima (negozio, punti, livello, alberi) + totale alberi + costo stimato a 0,80 €/albero + cap.
   - Se `exceeds_cap`: stampa lo sforamento in evidenza e **richiede** `--cap N` (nuovo cap per questa esecuzione) o conferma esplicita; senza, esce con codice ≠ 0 senza piantare.
   - Chiede conferma interattiva (`--yes` la salta ma **non** salta il blocco cap).
   - Se `ECOLOGI_TEST_MODE=true` lo dice chiaramente ("nessun addebito reale").
4. `.env.example` / `deploy.md`: `ECOLOGI_API_KEY`, `ECOLOGI_GLOBAL_MONTHLY_CAP`, `TIER_*`.

## File coinvolti
`app/services/ecologi_service.py`, `app/services/tree_service.py`, `scripts/close_period.py` (nuovo), `tests/test_close_period.py` (nuovo), `tests/conftest.py` (mock Ecologi aggiornato, fixture `approved_merchants`), `.env.example`, `.agents/workflows/deploy.md`.

## Test da superare
**Ecologi (httpx mockato, nessuna rete):**
- `purchase_trees(5)` invia `Authorization: Bearer <ECOLOGI_API_KEY>`, payload `{"number": 5}` + `"test": true` solo se `ECOLOGI_TEST_MODE`; l'`Idempotency-Key` passato viene usato, altrimenti è un uuid.
- Chiave piattaforma vuota → `EcologiError`; HTTP 500 → `EcologiError`; errore di rete → `EcologiError`.

**Chiusura (SQLite + Ecologi mockato):**
- 3 merchant approvati con pool 700 / 350 / 40 (soglie default 100/300/600; i pool sono prodotti da scan reali, quindi contatore e registro coincidono): piantano 5 / 3 / 1 alberi; sono create 3 righe `TreePlanting` con `period`, `level` (enum `Level`), `pool_points` (700/350/40) ed `ecologi_ref` corretti; chiamate Ecologi: 3, con `idempotency_key` `fidelitree-<id>-<period>` (con `ECOLOGI_TEST_MODE=true`: `fidelitree-test-<id>-<period>`).
- Merchant **non approvato** con pool 900: escluso, nessuna chiamata, nessuna riga.
- Merchant con pool sotto il bronzo: nessuna chiamata Ecologi, nessuna riga.
- **Idempotenza**: eseguire due volte la stessa chiusura → la seconda non effettua chiamate né righe nuove (`skipped`).
- **Prova e chiusura vera**: una chiusura con `test=True` per un mese non impedisce la chiusura reale (`test=False`) dello stesso mese; una seconda chiusura reale invece sì (`skipped`).
- **Divergenza contatore/registro**: alterando a mano `MerchantPool.points` di un merchant approvato, `close_period` non effettua **nessuna** chiamata Ecologi, non scrive righe e il report elenca la divergenza (contatore vs registro); lo script esce con codice ≠ 0 anche con `--yes`. Senza divergenze `pool_mismatches` ritorna lista vuota.
- **Snapshot**: dopo la chiusura, un movimento successivo che cambia `MerchantPool.points` **non** modifica `TreePlanting.pool_points`.
- Errore Ecologi sul secondo di tre negozi: primo e terzo piantati e registrati, secondo `failed` **senza** riga `TreePlanting`; una successiva riesecuzione pianta solo il secondo.
- Override soglie del merchant rispettato (es. bronzo=50: pool 60 → 1 albero).
- Pool letto solo dal mese richiesto (righe `MerchantPool` di altri `period` ignorate; uno scan del 1° del mese dopo non entra nel mese chiuso); la conversione cashback non riduce il pool.
- **Cap**: totale 24 con cap 20 e `confirm` che rifiuta → nessuna chiamata, report con `exceeds_cap`; con cap alzato a 24 → pianta tutto.
- Script: con `--yes` e cap sforato senza `--cap` esce con codice ≠ 0 (test sul `main(argv)` della funzione, non sul processo).
- Mese di default dello script = mese precedente alla data UTC (con `now` iniettato: `2026-11-01 00:10 UTC` → default `2026-10`).

## Fuori scope
Endpoint admin e cron (futuro), ripartizione automatica del cap, pagina pubblica contatore alberi.

## Definition of Done
Test verdi, suite verde, `python -m scripts.close_period --help` funziona, nessun riferimento residuo a chiavi Ecologi per-merchant nel codice.
