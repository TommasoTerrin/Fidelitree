# 02 — Modelli dati, config ed errori di dominio

## Obiettivo
Portare lo schema al modello target (vedi README dei ticket), aggiungere le nuove impostazioni di config e creare gli errori di dominio con il loro handler HTTP. **Nessuna nuova logica di business**: solo fondamenta.

## Contesto
Stato attuale: `Merchant` ha `password` (Fernet), `phone_number` unico, `mode`, `ecologi_api_key`, `tree_threshold`, `monthly_tree_cap`; `Card` ha `trees_planted` e nessun cliente; `TreePlanting` è per carta. I validatori pydantic su `table=True` **non girano sul costruttore** (usare `model_validate`, come fa `merchant_crud`). I services oggi sollevano `HTTPException`: questo ticket introduce l'alternativa pulita per il core.

## Dipendenze
01.

## Modifiche
1. **`app/models/models.py`** — vedi "Modello dati target" nel README. Dettagli:
   - `Merchant`: rimuovi `password`, `phone_number`, `mode`, `ecologi_api_key`, `tree_threshold`, `monthly_tree_cap`; aggiungi `email` (unique, index; il validatore la **normalizza in minuscolo e senza spazi ai lati**), `auth_user_id`, `contact_phone` opzionale (validazione `+39` mantenuta solo se valorizzato), `is_approved`, `conversion_enabled`, `conversion_threshold`, **`conversion_value_cents`** (int, default 200), gli override `*_threshold`. Validatori: `conversion_threshold >= 1`, `conversion_value_cents > 0`, override se presenti `>= 1`, `type` invariato.
   - Nuove tabelle `Customer` (email normalizzata come sopra), `PointTransaction` (con `period`, **nessun indice aggiuntivo**: il pool non si legge da qui) e **`MerchantPool`** (PK composta `(merchant_id, period)`, `points` int default 0); `TreePlanting` ridefinita (`period`, `level` come enum `Level`, `tree_count`, **`pool_points`**, **`ecologi_ref`** opzionale, **`UNIQUE(merchant_id, period, test)`**).
   - `Card`: aggiungi `customer_id` (FK), `UNIQUE(merchant_id, customer_id)`; **sostituisci `cashback_point` (float) con `cashback_cents` (int, default 0)**; rimuovi `trees_planted`.
   - **Timestamp**: tutti i `created_at` usano `utc_now()` (aware) con colonna `DateTime(timezone=True)`; nessun `datetime.utcnow`. Nota: SQLite restituisce datetime naive in lettura, quindi i test non devono confrontare naive con aware.
   - **FK**: `ondelete="CASCADE"` su tutte le FK verso `merchant`/`customer`, oltre al cascade ORM. SQLite non applica le FK di default: nei test conta il cascade ORM, `ondelete` serve per Postgres.
   - Cascade: eliminare un merchant elimina carte, movimenti, `MerchantPool`, piantumazioni; eliminare un customer elimina le sue carte.
   - **Nuovo `app/core/enums.py`** (solo stdlib): `PointTransactionKind` (`scan`, `conversion`) e `Level` (`none`, `bronze`, `silver`, `gold`) come `str, Enum`. `Level` sta qui (non in `tree_service`) perché lo importano sia i modelli sia il core del ticket 03, che non può dipendere da SQLModel.
   - **Nuovo `app/core/money.py`** (solo stdlib): `euro_to_cents(euro: float) -> int` (arrotonda al centesimo, `ValueError` se non finito) e `cents_to_euro(cents: int) -> float`. Usati solo ai bordi.
   - **Nuovo `app/core/clock.py`**: `utc_now() -> datetime` (aware, UTC). Unico punto in cui la shell legge l'orologio.
2. **`app/core/errors.py`** (nuovo): `DomainError(Exception)` base; sottoclassi `NotFoundError`, `ForbiddenError`, `InsufficientBalanceError`, `InvalidThresholdsError`, `PeriodAlreadyClosedError`. Docstring in italiano. **Nessun import da fastapi.**
3. **`app/main.py`**: exception handler per `DomainError` → JSON `{"detail": str(e)}`; mapping: `NotFoundError`→404, `ForbiddenError`→403, tutti gli altri→400.
4. **`app/core/config.py`**: aggiungi
   - `ECOLOGI_API_KEY: str = ""` (chiave di piattaforma; vuota consentita in dev/test),
   - `ECOLOGI_GLOBAL_MONTHLY_CAP: int = 20`,
   - `TIER_BRONZE_POINTS: int = 100`, `TIER_SILVER_POINTS: int = 300`, `TIER_GOLD_POINTS: int = 600`,
   - `AUTH_PROVIDER: Literal["dev", "supabase"] = "dev"`, `ENVIRONMENT: str = "development"`.
   Rimuovi da `Settings` `ENCRYPTION_KEY` e `MERCHANT_PASSWORD` **solo se** nessun altro codice li usa dopo questo ticket; altrimenti lasciali (verranno tolti nel ticket 06/07) e annota il debito in `.agents/planner/current.md`.
5. **Compat transitoria**: `merchant_crud`, `tree_service`, `card_service`, schemas e route che usano campi rimossi vanno adattati al minimo per far tornare avviabile l'app e verde la suite (i comportamenti nuovi arrivano nei ticket successivi). Ciò che non ha più senso (es. validazione chiave Ecologi del merchant) può essere disattivato con `# TODO(ticket NN)` **solo se un ticket successivo lo rimuove esplicitamente**.
6. `.env.example` e `.agents/workflows/deploy.md`: documenta le nuove variabili.

## File coinvolti
`app/models/models.py`, `app/core/errors.py`, `app/core/enums.py`, `app/core/money.py`, `app/core/clock.py` (tutti nuovi), `app/core/config.py`, `app/main.py`, `app/services/db_crud/*`, `app/schemas/*` (le risposte esterne restano in euro: `cashback_point` = `cents_to_euro(cashback_cents)`), `tests/conftest.py` (fixture `merchant`, `card`, nuovo `customer`), `tests/test_models.py`, `tests/test_crud.py`, `tests/unit/test_money.py` (nuovo), `.env.example`, `.agents/workflows/deploy.md`.

## Test da superare
- `tests/test_models.py`: Merchant valido si crea con `model_validate`; `conversion_threshold=0` → errore; `conversion_value_cents=0` → errore; `contact_phone="123"` → errore, `None` → ok; override `bronze_threshold=0` → errore; `email="  Mario@Bar.IT "` → salvata `"mario@bar.it"` (idem `Customer`).
- `Card`: due carte con stesso `(merchant_id, customer_id)` → `IntegrityError`; stesso customer su due merchant diversi → ok; `cashback_cents` è int con default 0.
- `TreePlanting`: due righe con stesso `(merchant_id, period, test)` → `IntegrityError`; stesso `(merchant_id, period)` con `test=True` e `test=False` → ok (la prova non blocca la chiusura vera); `level` accetta solo valori di `Level`.
- `MerchantPool`: due righe con stessa `(merchant_id, period)` → `IntegrityError`; `points` default 0.
- Cascade: eliminare un merchant elimina carte, `PointTransaction`, `MerchantPool` e `TreePlanting` collegati.
- `tests/unit/test_money.py` (senza DB): `euro_to_cents(2.0)=200`, `(0.1+0.2)=30`, `(19.99)=1999`, `(0.005)` arrotonda coerentemente, `NaN`/`inf` → `ValueError`; `cents_to_euro(250)=2.5`; round-trip su 0..10_000 centesimi.
- `utc_now()` ritorna un datetime con `tzinfo` UTC; i `created_at` dei modelli sono aware alla creazione.
- `app/core/enums.py`, `money.py`, `errors.py` non importano `fastapi`/`sqlmodel` (test su `ast`).
- `app/core/errors.py` non importa `fastapi` (test che ispeziona i moduli importati o `ast`).
- Handler: una route di test che solleva `NotFoundError` risponde 404, `InsufficientBalanceError` 400, `ForbiddenError` 403, tutte con `{"detail": ...}`.
- `Settings()` con le sole variabili obbligatorie istanzia con i default nuovi (`TIER_*`, cap 20, `AUTH_PROVIDER="dev"`).
- `python -c "import app.main"` ok; suite verde.

## Fuori scope
Logica livelli/pool (03), scan (04), auth (06/07), template.

## Definition of Done
Schema nuovo creato da `create_all()` su SQLite in-memory, test sopra verdi, nessun test disattivato con `skip`.
