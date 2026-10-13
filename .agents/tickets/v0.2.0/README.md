# Ticket v0.2.0 — Pool del negozio, auth, wallet cliente

Obiettivo della versione: sostituire gli alberi "per carta, pagati dal merchant" con un **pool mensile per negozio, pagato dal founder**, e introdurre **iscrizione cliente + wallet PWA** e **auth merchant per email** (interfaccia pronta per Supabase). Contesto di business e regole: [AGENTS.md](../../../AGENTS.md) — leggilo PRIMA.

## Come usare i ticket (modalità goal)

Si passa **un ticket alla volta**, nell'ordine. Un ticket è chiuso solo quando **tutti** i test della sezione "Test da superare" esistono e passano e `python -m pytest` è verde sull'intera suite.

Ogni ticket contiene: contesto, dipendenze, modifiche, file coinvolti, test da superare (ipotesi: l'agente può affinarle, ma non ridurne la copertura), fuori scope, definition of done.

## Ordine e dipendenze

| # | Ticket | Dipende da |
|---|---|---|
| 01 | [Versionamento pyproject](01-versionamento.md) | — |
| 02 | [Modelli dati, config ed errori di dominio](02-modelli-config-errori.md) | 01 |
| 03 | [Core puro: livelli e piano di chiusura](03-core-pool-livelli.md) | 02 |
| 04 | [Scan: registro movimenti e conversione in cashback](04-scan-conversione.md) | 02, 03 |
| 05 | [Ecologi di piattaforma e script close_period](05-ecologi-close-period.md) | 03, 04 |
| 06 | [Interfaccia auth e provider dev](06-auth-interfaccia.md) | 02 |
| 07 | [Auth merchant, approvazione e admin](07-merchant-auth-admin.md) | 02, 06 |
| 08 | [Backend cliente: join, wallet, proprietà carta](08-cliente-backend.md) | 04, 06 |
| 09 | [Frontend merchant](09-frontend-merchant.md) | 04, 07 |
| 10 | [Frontend cliente e PWA](10-frontend-cliente-pwa.md) | 08 |
| 11 | [Seed, smoke test, documentazione, release](11-seed-docs-release.md) | tutti |

I ticket 03–05 (logica alberi) e 06–07 (auth) sono indipendenti tra loro: si possono invertire, ma tenere l'ordine numerico evita conflitti nei file condivisi (`models.py`, `conftest.py`).

## Convenzioni valide per TUTTI i ticket

1. **Stile**: imita il codice esistente (naming, struttura dei service, stile dei template Tailwind, fixture dei test).
2. **Docstring in italiano** su ogni modulo, classe e funzione aggiunta o modificata (cosa fa, parametri non ovvi, ritorno, errori sollevati). Commenti inline in italiano.
3. **Functional core / imperative shell** nello stesso modulo (regola 3 di AGENTS.md):
   - sezione `# --- Core puro ---`: solo Pydantic + stdlib, niente `Session`/`httpx`/`fastapi`/`datetime.now()`, errori di dominio da `app/core/errors.py`;
   - sezione `# --- Shell ---`: I/O, DB, rete, orologio; sottile.
   - test del core in `tests/unit/` **senza DB e senza mock**; test della shell/route in `tests/` con le fixture esistenti.
4. **Test esistenti che descrivono il vecchio comportamento** (alberi per carta, `mode`, chiave Ecologi del merchant) vanno **riscritti o rimossi**, non lasciati rossi né disattivati con `skip`.
5. **Il progetto deve restare avviabile** (`python -c "import app.main"`) dopo ogni ticket.
6. Nuove env var → `.env.example` e `.agents/workflows/deploy.md`.
7. A fine ticket: aggiorna `.agents/planner/current.md` (una riga di stato). Commit in italiano, al presente, **solo se richiesto**.
8. Gli errori nelle shell/route mantengono i messaggi `detail` in italiano già in uso, dove il caso esiste ancora.
9. **Denaro in centesimi interi** (decisione 2026-10-12): nel DB e nel core i soldi sono `int` in centesimi (`*_cents`), mai `float`. La conversione euro ↔ centesimi avviene **solo ai bordi** (schemi/route/template) con gli helper di `app/core/money.py`; le API pubbliche continuano a parlare in euro.
10. **Tempo** (decisione 2026-10-12): i timestamp sono sempre **UTC aware** (`app/core/clock.py: utc_now()`, mai `datetime.utcnow()`). Il **mese è quello UTC** (accettato: lo scarto di 1-2 ore col mese italiano a cavallo del 1° è irrilevante per l'uso reale), calcolato **una volta sola in scrittura** con `period_for(moment)` e salvato come `period` ('YYYY-MM'); non si ricostruiscono mai i confini del mese in lettura. Niente fusi orari né `zoneinfo`/`tzdata`. Il core riceve il tempo come argomento.

## Modello dati target (riferimento unico per tutti i ticket)

```
Merchant      id, business_name, email (unique, minuscolo), auth_user_id (unique, nullable), contact_phone (opz., +39),
              type ('test'|'free'|'pro'), is_approved (default False),
              conversion_enabled (default True), conversion_threshold (int ≥1, default 50),
              conversion_value_cents (int >0, default 200),
              bronze_threshold / silver_threshold / gold_threshold (int opz.: override admin)
Customer      id, email (unique, minuscolo), auth_user_id (unique), created_at (UTC)
Card          id (UUID), merchant_id, customer_id, cashback_cents (int, centesimi), tree_points (saldo cliente)
              UNIQUE(merchant_id, customer_id)        # niente più trees_planted
PointTransaction  id, merchant_id, card_id (UUID, non FK), kind ('scan'|'conversion'), delta (int),
              period ('YYYY-MM', mese UTC, fissato in scrittura), created_at (UTC)
              # registro = FONTE DI VERITÀ e audit; la conversione NON entra nel pool
MerchantPool  merchant_id, period ('YYYY-MM'), points (int)       # PK (merchant_id, period)
              # contatore del pool del mese = cache del registro: SUM(delta) dei soli kind='scan' di quel (merchant, period).
              # Si incrementa nella STESSA transazione dello scan; mai ricalcolato in lettura.
TreePlanting  id, merchant_id, period ('YYYY-MM'), level (enum Level), tree_count, pool_points (snapshot alla chiusura),
              ecologi_ref (opz.), test (bool), created_at (UTC)
              UNIQUE(merchant_id, period, test)       # idempotenza della chiusura; una prova non blocca la chiusura vera
```

Vincoli trasversali: le FK verso `merchant`/`customer` hanno `ondelete="CASCADE"` oltre al cascade dell'ORM (serve su Postgres/Supabase per cancellazioni fuori dall'app); `Level` e `PointTransactionKind` sono enum `str, Enum` in `app/core/enums.py` (solo stdlib, importabili dal core e dai modelli).
