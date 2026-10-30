# 03 — Core puro: livelli del pool e piano di chiusura

## Obiettivo
Implementare **solo logica pura** (nessun DB, nessuna rete) per: calcolo livello del pool, avanzamento verso il livello successivo, **attribuzione di un istante al periodo (mese UTC)**, e **piano di chiusura del periodo** con controllo del cap globale. È il cuore della nuova gamification, quindi massima copertura di unit test.

## Contesto
Regole (da AGENTS.md): bronzo = 1 albero, argento = 3, oro = 5 (totali, non cumulativi); mese solare; pool = somma netta dei tree points "scan" del negozio nel mese (può risultare ≤0 → livello nessuno). Il pool **non si ricalcola in lettura**: è il contatore `MerchantPool.points` aggiornato a ogni scan (ticket 04); questo core riceve già il numero di punti. Il mese di appartenenza di uno scan si decide **una volta sola in scrittura** con `period_for` (mese UTC: uno scan fatto tra mezzanotte e le 2 del 1° ora italiana conta nel mese precedente, scarto accettato). Cap globale sforato → **il piano segnala lo sforamento, NON ripartisce** (decisione 2026-10-09). I negozi già chiusi per il periodo vengono esclusi.

## Dipendenze
02 (errori di dominio, config, `Level` in `app/core/enums.py`). Nessuna nuova dipendenza.

## Modifiche
Riscrivi `app/services/tree_service.py` con la sola sezione `# --- Core puro ---` (la shell arriva nei ticket 04/05; il vecchio codice di piantumazione per carta va **rimosso**). Contenuto, tutto con modelli Pydantic e docstring italiane:

```python
from app.core.enums import Level               # definito nel ticket 02, NON ridefinirlo
TREES_PER_LEVEL: dict[Level, int]            # 0 / 1 / 3 / 5

class LevelThresholds(BaseModel):            # bronze < silver < gold, tutti >= 1, altrimenti InvalidThresholdsError
    bronze: int; silver: int; gold: int

def resolve_thresholds(defaults: LevelThresholds, bronze=None, silver=None, gold=None) -> LevelThresholds
    # applica gli override per singolo livello e RIVALIDA la coerenza finale

def compute_level(points: int, thresholds: LevelThresholds) -> Level   # points <= 0 → NONE
def trees_for_level(level: Level) -> int

class PoolProgress(BaseModel):
    points: int; level: Level; trees_at_month_end: int
    next_level: Level | None; points_to_next: int | None; percent_to_next: int   # 0..100; oro → next None, 100

def compute_pool_progress(points: int, thresholds: LevelThresholds) -> PoolProgress

def period_for(moment: datetime) -> str                                  # 'YYYY-MM' del mese UTC di `moment`; ValueError se naive
def period_label(year: int, month: int) -> str                           # 'YYYY-MM'
def previous_period(today: date) -> tuple[int, int]                      # (anno, mese) del mese precedente a `today`

class PoolInput(BaseModel): merchant_id; business_name; points; thresholds: LevelThresholds   # (era `MerchantPool`: rinominato per non collidere con la tabella)
class ClosureLine(BaseModel): merchant_id; business_name; points; level; trees
class ClosurePlan(BaseModel): period; lines; total_trees; global_cap; exceeds_cap: bool; excess: int

def plan_period_closure(period: str, pools: list[PoolInput], already_closed: set[int], global_cap: int) -> ClosurePlan
    # esclude i merchant già chiusi; lines ordinate per merchant_id; excess = max(0, total - cap)
```
Nessun uso di `datetime.now()` nel core: il tempo entra come argomento.

## File coinvolti
`app/services/tree_service.py` (riscritto, solo core), `tests/unit/__init__.py` e `tests/unit/test_pool.py` (nuovi), `tests/test_trees.py` (vecchio: rimuovere i test per carta; quelli di shell tornano nei ticket 04/05).

## Test da superare (`tests/unit/test_pool.py`, nessun DB, nessun mock)
Con soglie 100/300/600:
- `compute_level`: 0→NONE, 99→NONE, 100→BRONZE, 299→BRONZE, 300→SILVER, 599→SILVER, 600→GOLD, 10_000→GOLD, −5→NONE.
- `trees_for_level`: NONE 0, BRONZE 1, SILVER 3, GOLD 5.
- `compute_pool_progress(150)`: BRONZE, next SILVER, `points_to_next=150`, `percent_to_next=25` (50 su 200); `(0)`: NONE, next BRONZE, `points_to_next=100`, percent 0; `(700)`: GOLD, next None, percent 100; `(−10)` tratta come 0.
- `LevelThresholds(100, 100, 600)` e `(300, 100, 600)` e `(0, 1, 2)` → `InvalidThresholdsError`.
- `resolve_thresholds(defaults, bronze=50)` → 50/300/600; `resolve_thresholds(defaults, bronze=400)` → `InvalidThresholdsError` (rompe l'ordinamento); senza override → i default.
- `period_for` (istanti UTC aware): `2026-09-30 23:59:59` → `"2026-09"`; `2026-10-01 00:00:00` → `"2026-10"` (confine incluso nel mese nuovo); `2026-12-31 23:59:59` → `"2026-12"`, `2027-01-01 00:00:00` → `"2027-01"` (cambio anno); `2028-02-29 12:00` → `"2028-02"` (bisestile); un istante aware con altro offset (es. `+02:00`) viene convertito in UTC prima; `datetime` **naive** → `ValueError`.
- `previous_period(date(2026, 1, 15))` = (2025, 12); `previous_period(date(2026, 3, 1))` = (2026, 2); `period_label(2026, 3)` = `"2026-03"`.
- `plan_period_closure`:
  - 3 pool (oro, argento, nessun livello), cap 20 → lines 3, trees 5/3/0, `total_trees=8`, `exceeds_cap=False`, `excess=0`;
  - 6 negozi per 24 alberi con cap 20 → `exceeds_cap=True`, `excess=4`, **le righe restano invariate** (nessuna ripartizione);
  - `already_closed={id}` esclude quel merchant e non conta nel totale;
  - lista vuota → piano vuoto, `total_trees=0`;
  - totale esattamente = cap → `exceeds_cap=False`.
- `Level` è importato da `app.core.enums` (non definito in `tree_service`).
- Il modulo non importa `sqlmodel`, `httpx`, `fastapi` in questa sezione (test su `ast` della sezione core o su import isolato).

## Fuori scope
Query DB, scan, Ecologi, script. Nessuna route.

## Definition of Done
`python -m pytest tests/unit` verde senza DB; suite completa verde; il file contiene solo core e la docstring di modulo spiega le regole di business.
