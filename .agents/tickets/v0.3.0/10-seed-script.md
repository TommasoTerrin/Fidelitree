# 10 — Seed, smoke test e script

## Obiettivo
Riallineare gli script al nuovo flusso:
- `seed_db` crea carte "Instagram" finte e stampa i link `/c/…` per il collaudo;
- `smoke_test_prod` verifica le nuove pagine e che quelle vecchie non esistano più;
- `zernio_check` può usare la chiave salvata di un merchant.

## Contesto
`seed(session)` è iniettabile e idempotente e gira solo con `AUTH_PROVIDER=dev`; scan e pool passano da
`add_tree_points` (v0.2.0, ticket 11). Ora le carte nascono da `get_or_create_card` con IGSID finti, senza chiamate a
Zernio. I merchant del seed restano `NOT_CONNECTED`: l'onboarding vero si fa nel collaudo con la propria chiave.

## Dipendenze
09.

## Modifiche
1. **`scripts/seed_db.py`**:
   - stessi due negozi (Bar Demo a livello oro con conversione, Forno Solo Alberi senza livello);
   - carte create con `instagram_service.get_or_create_card(session, merchant, igsid=f"seed-igsid-{n}")`;
   - stampa, per ogni carta, il link locale `http://127.0.0.1:8001/c/<token>`. È solo locale, il seed non gira in
     produzione;
   - resta idempotente e `pool_mismatches` resta vuoto.
2. **`scripts/smoke_test_prod.py`** (client HTTP iniettabile come oggi):
   - `/health.version == 0.3.0`;
   - `/c/token-inesistente` → 404;
   - `/privacy` → 200;
   - `/merchant/login` → 200;
   - manifest con `start_url` `/merchant/scanner`;
   - `/sw.js` → 200;
   - `POST /webhooks/zernio/hook-inesistente` → 404;
   - `/join/1` e `/wallet` → 404;
   - endpoint admin con e senza chiave come oggi;
   - nessun invio a Zernio, nessun albero piantato.
3. **`scripts/zernio_check.py`**: opzione `--merchant-id N` in alternativa alla chiave da env. Usa
   `zernio_credentials_for` (legge il DB del `.env`) e mostra lo stato del merchant (`instagram_status`, `@username`,
   chiave mascherata, invii del mese).

## File coinvolti
`scripts/seed_db.py`, `scripts/smoke_test_prod.py`, `scripts/zernio_check.py`, `tests/test_scripts.py`.

## Test da superare
- **`seed(session)`**:
  - crea i 2 merchant e le carte con `igsid_hash`;
  - rilanciato non duplica nulla;
  - i link stampati portano a `/c/…` e la pagina risponde 200 con il `TestClient`;
  - `pool_mismatches` è vuoto;
  - il seed rifiuta `AUTH_PROVIDER` diverso da `dev`.
- **`smoke_test_prod`** con un client finto:
  - tutti i controlli passano contro risposte giuste;
  - fallisce (exit ≠ 0) se `/wallet` risponde 200 o se il manifest punta a `/wallet`.
- **`zernio_check --merchant-id`** (`MockTransport`): mostra lo stato e la chiave mascherata; un merchant senza chiave
  → exit 1 con un messaggio chiaro.

## Fuori scope
Documentazione e collaudo end-to-end (11).

## Definition of Done
Suite verde. Prova manuale su SQLite usa-e-getta: `reset_db --force`, `seed_db`, apertura di un link `/c/…`, scan del
merchant del seed.
