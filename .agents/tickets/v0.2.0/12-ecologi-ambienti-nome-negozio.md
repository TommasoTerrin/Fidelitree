# 12 — Ecologi: ambienti test/produzione corretti e nome del negozio nella foresta

## Obiettivo
Allineare `ecologi_service` alla documentazione ufficiale dell'Impact API ([docs.ecologi.com/#impact-trees](https://docs.ecologi.com/#impact-trees)) e far comparire **il nome del negozio** sulla tessera degli alberi nella foresta Ecologi, così il merchant si ritrova e può usarlo nei post social.

## Contesto
Dalla doc di `POST https://public.ecologi.com/impact/trees`:
- **Non esiste un URL sandbox**: la prova si fa sullo **stesso URL** con `"test": true` nel body (risposta realistica, nessun addebito, nulla sul profilo). Oggi il codice in test mode legge `ECOLOGI_TEST_BASE_URL`, vuoto di default → **in test mode la chiusura fallisce sempre** con "URL Ecologi di test non configurato".
- Il founder ha **due chiavi distinte**: una di test (dev/collaudo) e una di produzione.
- `name` (stringa, facoltativo) è l'etichetta "funded by" mostrata **accanto agli alberi nella foresta** (pubblica se il profilo è pubblico). Richieste con lo **stesso `name` entro 24 ore si accumulano sulla stessa tessera**. Oggi mandiamo `"Fidelitree {period} negozio {id}"`, che al merchant non dice nulla.
- La risposta `201` contiene `amount`, `currency`, `treeUrl`, `name`, `projectDetails`: **nessun `id`**. Il riferimento utile è `treeUrl` (link alla tessera); oggi `extract_ref` cerca prima `id`/`purchaseId`.
- Endpoint: si resta su `/impact/trees` (alberi standard, il più economico, ~0,80 €). `local-trees` costa di più ed è fuori scope.

Decisioni del founder (2026-10-14):
- un solo `ECOLOGI_BASE_URL`, due chiavi (`ECOLOGI_API_KEY` reale, `ECOLOGI_TEST_API_KEY` di prova), scelte da `ECOLOGI_TEST_MODE`;
- formato del nome: **`<nome negozio> · <mese in italiano> <anno>`** (es. `Bar Demo · ottobre 2026`);
- **nessuna gestione del consenso** alla pubblicazione del nome (i merchant sono pochi e conosciuti; lo si dice a voce);
- dalla risposta si salva **solo `treeUrl`** in `TreePlanting.ecologi_ref` (niente `amount`/`currency`), **nessuna UI** per ora;
- **nessun blocco** tra `ENVIRONMENT` e `ECOLOGI_TEST_MODE`: decide solo `ECOLOGI_TEST_MODE`.

## Dipendenze
05 (ecologi_service, close_period).

## Modifiche
1. **`app/core/config.py`**: rimuovi `ECOLOGI_TEST_BASE_URL`. `ECOLOGI_BASE_URL` (default `https://public.ecologi.com`) vale per entrambe le modalità.
2. **`app/services/ecologi_service.py`**:
   - `_credentials()` ritorna `(api_key, base_url)`: chiave di test con `ECOLOGI_TEST_MODE=true`, reale con `false`; URL sempre `ECOLOGI_BASE_URL`. Chiave dell'ambiente attivo vuota → `EcologiError` con l'etichetta giusta ("di test" / "di piattaforma"). **Nessun fallback** dalla chiave di test a quella reale (né viceversa).
   - Payload: `{"number": n}`, `"name"` se presente, `"test": true` se `ECOLOGI_TEST_MODE`. Nuovo parametro keyword `force_test: bool = False` che aggiunge `"test": true` anche con `ECOLOGI_TEST_MODE=false` (serve al ticket 13 per verificare la chiave reale senza addebito).
   - `extract_ref` ritorna `treeUrl` (unico identificativo documentato), `None` se assente; elimina `_REF_KEYS`.
   - Docstring di modulo riallineata (stesso URL, flag `test`, due chiavi).
3. **`app/services/tree_service.py`**:
   - Core puro: `planting_name(business_name: str, period: str) -> str` → `"Bar Demo · ottobre 2026"`. Mesi italiani minuscoli da una tupla costante (niente `locale`, solo stdlib). Normalizza gli spazi del nome (strip + spazi multipli → uno); se il nome normalizzato è vuoto usa `"Negozio Fidelitree"`. Tronca il nome del negozio a **60 caratteri** (la doc non dà un limite: scelta prudente). `period` non valido → errore di dominio già usato per i periodi (riusa la validazione esistente di `period`).
   - Shell: `close_period` passa `name=planting_name(line.business_name, period)` al posto della stringa attuale.
   - Accettato: due negozi con **lo stesso nome** chiusi nello stesso mese finiscono sulla stessa tessera Ecologi (accumulo entro 24 ore). Caso improbabile, nessuna gestione.
4. **`.env.example`** e **`.agents/workflows/deploy.md`**: rimuovi `ECOLOGI_TEST_BASE_URL`; documenta che le due chiavi usano lo stesso URL e che in produzione serve `ECOLOGI_TEST_MODE=false` + `ECOLOGI_API_KEY`, in locale `ECOLOGI_TEST_MODE=true` + `ECOLOGI_TEST_API_KEY`.
5. **`AGENTS.md`** (vincoli e trade-off): nuova riga datata 2026-10-14: nome del negozio pubblico su Ecologi senza gestione del consenso; due chiavi e un solo URL; `ecologi_ref` = `treeUrl`.
6. **`.agents/architecture/overview.md`**: riallinea la sezione Ecologi (URL unico, flag test, formato del nome, `treeUrl`).

## File coinvolti
`app/core/config.py`, `app/services/ecologi_service.py`, `app/services/tree_service.py`, `tests/test_close_period.py`, `tests/test_core_infra.py`, `tests/unit/test_pool.py` (o nuovo `tests/unit/test_planting_name.py`), `.env.example`, `.agents/workflows/deploy.md`, `.agents/architecture/overview.md`, `AGENTS.md`.

## Test da superare
**Core (`tests/unit/`, niente DB né mock):**
- `planting_name("Bar Demo", "2026-10") == "Bar Demo · ottobre 2026"`; gennaio e dicembre corretti.
- `"  Forno   del Borgo "` → `"Forno del Borgo · …"`; nome vuoto/solo spazi → `"Negozio Fidelitree · …"`; nome di 100 caratteri → parte negozio lunga 60.
- `period` non valido (`"2026-13"`, `"ottobre"`) → errore di dominio.

**Ecologi (httpx mockato, nessuna rete):**
- `ECOLOGI_TEST_MODE=true`: richiesta a `{ECOLOGI_BASE_URL}/impact/trees` con `Authorization: Bearer <ECOLOGI_TEST_API_KEY>` e `"test": true`.
- `ECOLOGI_TEST_MODE=false`: stesso URL, `Bearer <ECOLOGI_API_KEY>`, **senza** chiave `"test"` nel payload.
- `ECOLOGI_TEST_MODE=false` + `force_test=True`: chiave reale **e** `"test": true`.
- Test mode con `ECOLOGI_TEST_API_KEY` vuota → `EcologiError`, **anche se** `ECOLOGI_API_KEY` è valorizzata (nessun fallback); e viceversa in modalità reale.
- `extract_ref({"treeUrl": "https://ecologi.com/x?tree=1", "amount": 1.8})` → l'URL; risposta senza `treeUrl` → `None`.
- `Settings` non ha più `ECOLOGI_TEST_BASE_URL` (aggiorna `test_core_infra`).

**Chiusura (SQLite + Ecologi mockato):**
- Il `name` inviato per ogni negozio è `planting_name(business_name, period)` (es. `"Bar Demo · settembre 2026"` per `--month 2026-09`).
- `TreePlanting.ecologi_ref` = `treeUrl` della risposta mockata.
- I test esistenti di `test_close_period.py` restano verdi (adeguati al nuovo `extract_ref` e al config senza URL di test).

## Fuori scope
Link alla foresta nelle UI merchant/cliente, salvataggio di `amount`/`currency`, `recipientEmail`, gestione consenso/opt-out, blocchi `ENVIRONMENT` ↔ `ECOLOGI_TEST_MODE`, Reporting API (`GET /users/{username}/trees`), altri endpoint Impact.

## Definition of Done
Test verdi, suite verde, `grep ECOLOGI_TEST_BASE_URL` vuoto (eccetto changelog storico), `close_period` in test mode funziona con la sola `ECOLOGI_TEST_API_KEY` configurata.
