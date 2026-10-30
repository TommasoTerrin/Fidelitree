# 04 — Scan: registro movimenti e conversione automatica in cashback

## Obiettivo
Quando il merchant aggiunge/toglie tree points a una carta: aggiornare il saldo, **registrare il movimento** nel registro, **incrementare il contatore del pool del mese** e, se attiva, **convertire automaticamente** i tree points in cashback a soglia raggiunta. Lo scan **non chiama mai Ecologi**.

## Contesto
Oggi `tree_service.update_tree_points` somma i punti e pianta alberi per carta (rimosso nel ticket 03). `card_service.update_cashback` contiene la regola "mai sotto zero" mescolata con `HTTPException`. Il **registro** (`PointTransaction`) è fonte di verità e audit; il **pool del mese** è il contatore `MerchantPool.points`, una cache del registro (somma dei soli `kind='scan'` di quel `(merchant, period)`) aggiornata **nella stessa transazione** dello scan e **mai ricalcolata in lettura**. La conversione scrive un movimento `kind='conversion'` che **non** tocca il contatore. Il denaro è in **centesimi interi** (README, convenzione 9): niente float e niente tolleranze nel core; l'API pubblica resta in euro, convertita ai bordi con `app/core/money.py`.

## Dipendenze
02, 03.

## Modifiche
1. **Core puro** (in `app/services/card_service.py`, sezione `# --- Core puro ---`):
   ```python
   class ConversionResult(BaseModel): tree_points_left: int; cashback_added_cents: int; conversions: int
   def apply_tree_points_delta(balance: int, delta: int) -> int           # InsufficientBalanceError se < 0
   def apply_cashback_delta(balance_cents: int, delta_cents: int) -> int  # tutto intero, nessuna tolleranza; InsufficientBalanceError se < 0
   def compute_conversion(tree_points: int, threshold: int, value_cents: int) -> ConversionResult
       # conversions = tree_points // threshold; residuo = tree_points % threshold; cashback_added_cents = conversions * value_cents
   ```
2. **Shell** (stesso modulo, `# --- Shell ---`), sostituisce `update_cashback`/`update_tree_points` esistenti:
   - `add_tree_points(session, merchant, card_id, points, now: datetime | None = None) -> ScanResult` (`ScanResult`: carta, `conversions`, `cashback_added_cents`). `now` default `utc_now()` (iniettabile nei test). Passi, in **un'unica transazione con un solo commit**:
     1. carica la carta con **`with_for_update()`** (blocca la riga su Postgres: due scan simultanei sulla stessa carta non perdono aggiornamenti; su SQLite è ignorato) e verifica la proprietà (stesso merchant, altrimenti `NotFoundError("Card non valida per questo merchant")`);
     2. applica il delta al saldo con il core;
     3. calcola `period = period_for(now)` **una sola volta** e scrive `PointTransaction(kind=scan, delta=points, period=period, created_at=now)`;
     4. incrementa il pool: crea la riga `MerchantPool(merchant_id, period)` se manca, poi `UPDATE ... SET points = points + :delta` (**incremento SQL atomico**, non read-modify-write in Python; niente `ON CONFLICT` perché la sintassi differisce tra Postgres e SQLite dei test);
     5. se `merchant.conversion_enabled`, calcola la conversione sul nuovo saldo e, se `conversions > 0`, aggiorna `tree_points` e `cashback_cents` e scrive `PointTransaction(kind=conversion, delta=-(conversions*threshold), period=period)` **senza toccare `MerchantPool`**.
   - `update_cashback(...)`: stessa API di oggi (importo in euro dall'esterno, convertito con `euro_to_cents` al bordo) ma con core puro in centesimi; **rimuovi il vincolo `mode`** (il cashback manuale è sempre disponibile).
   - `pool_points(session, merchant_id, period) -> int` in `tree_service.py` (shell): legge `MerchantPool.points` per chiave `(merchant_id, period)`; `0` se la riga non esiste. **Nessuna `SUM` sul registro e nessun `month_bounds`.**
   - `current_pool_progress(session, merchant, now) -> PoolProgress` in `tree_service.py` (shell): `pool_points` del `period_for(now)` + soglie effettive (`resolve_thresholds` con default `settings.TIER_*` e override del merchant) + `compute_pool_progress`.
3. **Route/schemi**: `POST /api/merchant/add-tree-points/{card_id}` risponde con `ScanResponse`: `card`, `converted` (`{conversions, cashback_added}` con `cashback_added` **in euro** o `null`), `pool` (`PoolProgress` aggiornato del merchant per il mese corrente). Rimuovi `planted_now`/`warning`. Le route non contengono logica: chiamano il service.
4. `CardResponse` perde `trees_planted`; `cashback_point` resta in euro (derivato da `cashback_cents`).

## File coinvolti
`app/services/card_service.py`, `app/services/tree_service.py`, `app/routes/merchant/api.py`, `app/schemas/card.py`, `tests/unit/test_conversion.py` (nuovo), `tests/test_trees.py` → rinominare/riscrivere in `tests/test_scan.py`, `tests/conftest.py`.

## Test da superare
**Unit (`tests/unit/test_conversion.py`, senza DB):**
- `compute_conversion(49, 50, 200)` → 0 conversioni, residuo 49, 0 centesimi;
  `(50, 50, 200)` → 1, residuo 0, 200; `(130, 50, 200)` → 2, residuo 30, 400; `(120, 40, 75)` → 3, residuo 0, 225.
- `apply_tree_points_delta(10, -10)` = 0; `(10, -11)` → `InsufficientBalanceError`; `(0, 5)` = 5.
- `apply_cashback_delta(500, -500)` = 0; `(500, -501)` → `InsufficientBalanceError`; `(0, 30)` = 30; il risultato è sempre `int`.

**Integrazione (SQLite in-memory):**
- Scan +20 con conversione attiva, soglia 50: saldo 20, nessun cashback, 1 movimento `scan` (+20), risposta `converted=None`, `pool.points=20`, riga `MerchantPool` con `points=20`.
- Scan +60 su carta a 0 (soglia 50, valore 200 cent): saldo 10, `cashback_cents=200`, **due** movimenti (`scan` +60, `conversion` −50), `converted={"conversions":1,"cashback_added":2.0}`, **pool = 60** (la conversione non lo riduce).
- Conversione disattivata (`conversion_enabled=False`): saldo cresce, nessun cashback, nessun movimento `conversion`.
- Scan −30 con saldo 20 → 400 "Impossibile portare i tree points sotto 0", **nessun movimento scritto, contatore del pool invariato**, saldo invariato (rollback).
- Scan −10 con saldo 20: saldo 10, movimento `scan` −10, pool diminuito di 10.
- **Periodo in scrittura** (`now` iniettato): scan a `2026-09-30 23:59 UTC` → movimento e `MerchantPool` con `period="2026-09"`; scan a `2026-10-01 00:00 UTC` → `"2026-10"`; scan in due mesi diversi → **due righe** `MerchantPool`, ciascuna con i propri punti.
- `pool_points`: nessuna riga → 0; i pool di altri merchant e di altri mesi non si mescolano.
- **Coerenza contatore/registro**: dopo una sequenza mista (scan positivi, negativo, conversione, due merchant, due mesi) per ogni `(merchant, period)` `MerchantPool.points == SUM(delta) dei movimenti kind='scan'` di quel `(merchant, period)`.
- **Scan ripetuti** (es. 20 scan in sequenza sulla stessa carta/stesso merchant): il contatore finale è esattamente la somma dei delta (nessun aggiornamento perso).
- Carta di un altro merchant → 404 "Card non valida per questo merchant".
- Cashback manuale funziona su un merchant con `conversion_enabled=False` (importo in euro in ingresso, `cashback_cents` in DB); sotto zero → 400; `19.99 €` → 1999 centesimi esatti.
- La risposta della route contiene `pool.level`/`points_to_next` coerenti con le soglie del merchant (override incluso).
- **Nessuna chiamata a Ecologi** durante lo scan (la fixture `mock_ecologi` registra zero chiamate).

## Fuori scope
Piantumazione (05), pagine HTML (09), proprietà carta lato cliente (08).

## Definition of Done
Test sopra verdi, suite verde, `grep` non trova più `trees_planted`, `planted_now`, `mode`, `cashback_point` come colonna, né `month_bounds`, nel codice di servizio e nelle route.
