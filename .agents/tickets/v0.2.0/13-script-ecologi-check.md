# 13 — Script `ecologi_check`: verifica reale delle chiavi Ecologi senza addebito

## Obiettivo
Avere un comando manuale che fa **una chiamata vera** a Ecologi con `"test": true` (nessun addebito, nulla sul profilo) per verificare che la chiave configurata funzioni, **prima** della prima chiusura mensile in produzione. Vale per entrambe le chiavi (test e reale).

## Contesto
I test automatici mockano sempre httpx: nessuno verifica che le chiavi siano valide e che URL e payload vadano bene a Ecologi. Con il flag `"test": true` Ecologi valida la richiesta e restituisce una risposta realistica senza addebitare. Il parametro `force_test` di `purchase_trees` (ticket 12) permette di provare anche la chiave reale.

## Dipendenze
12.

## Modifiche
1. **`scripts/ecologi_check.py`** (shell sottile, stile di `close_period.py` con `main(argv) -> int`):
   `python -m scripts.ecologi_check [--trees N] [--merchant-name NOME] [--month AAAA-MM]`
   - Default: `--trees 1`, `--merchant-name "Negozio di prova"`, `--month` = mese corrente UTC.
   - Il `name` inviato è `planting_name(merchant_name, month)`: così si vede l'etichetta esatta che comparirà nella foresta.
   - Chiama `purchase_trees(N, name=..., force_test=True)`: **sempre** `"test": true`, anche con `ECOLOGI_TEST_MODE=false`. Idempotency key casuale.
   - Stampa: quale chiave è in uso (`di test` / `REALE`, solo gli **ultimi 4 caratteri**, mai la chiave intera), URL chiamato, `name` inviato, e dalla risposta `treeUrl`, `amount` + `currency`, progetti (`projectDetails[].name`). Chiude con "Chiave OK — nessun addebito (test=true)".
   - `EcologiError` → messaggio chiaro su stderr ed exit code ≠ 0.
   - Non tocca il DB.
2. **`AGENTS.md`** (comandi essenziali): aggiungi il comando con un commento ("chiamata reale a Ecologi con test=true, nessun addebito").
3. **`.agents/workflows/deploy.md`**: come verificare la chiave reale prima della prima chiusura in produzione (`ECOLOGI_TEST_MODE=false python -m scripts.ecologi_check` dalla console DigitalOcean o in locale con la chiave reale nel `.env`).
4. **`.agents/checklists/pre-release.md`**: voce "lanciato `scripts.ecologi_check` con la chiave di test e con quella reale, entrambe OK". Il file ha già modifiche locali non committate: integrale, non sovrascriverle.

## File coinvolti
`scripts/ecologi_check.py` (nuovo), `tests/test_scripts.py`, `AGENTS.md`, `.agents/workflows/deploy.md`, `.agents/checklists/pre-release.md`.

## Test da superare
(Ecologi mockato come in `test_close_period.py`, nessuna rete; test su `main(argv)`, non sul processo.)
- `main([])` con `ECOLOGI_TEST_MODE=true`: una sola chiamata, payload `{"number": 1, "name": "Negozio di prova · <mese> <anno>", "test": true}`, chiave di test, exit 0; l'output contiene il `treeUrl` mockato e **non** contiene la chiave intera.
- `main([])` con `ECOLOGI_TEST_MODE=false`: chiave reale **e** `"test": true` nel payload; l'output indica `REALE`.
- `--trees 3 --merchant-name "Bar Demo" --month 2026-10` → `number: 3`, `name: "Bar Demo · ottobre 2026"`.
- Chiave dell'ambiente attivo mancante o HTTP 401 → exit ≠ 0, messaggio su stderr.
- Lo script non apre sessioni DB (nessuna riga `TreePlanting` creata).

## Collaudo manuale
1. `.env` locale con `ECOLOGI_TEST_MODE=true` e `ECOLOGI_TEST_API_KEY` → `python -m scripts.ecologi_check` → OK.
2. Stessa cosa con `ECOLOGI_TEST_MODE=false` e `ECOLOGI_API_KEY` → OK, e sul profilo Ecologi **non** compare nulla.
3. `python -m scripts.reset_db` + `seed_db` su SQLite usa-e-getta → `python -m scripts.close_period` in test mode → piantumazione riuscita, `TreePlanting.ecologi_ref` contiene un `treeUrl`.

## Fuori scope
Endpoint HTTP per la verifica, controlli automatici in `smoke_test_prod` (resta senza chiamate a Ecologi), Reporting API.

## Definition of Done
Test verdi, suite verde, `python -m scripts.ecologi_check --help` funziona, collaudo manuale 1–3 eseguito con le chiavi vere.
