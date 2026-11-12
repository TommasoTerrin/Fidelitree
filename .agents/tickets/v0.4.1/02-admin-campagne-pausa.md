# Ticket 02 — Dashboard admin: campagne e pausa che archivia

> v0.4.1. Dipende da: 01. Criteri: AC-01..08; I1, I2, I5.
> Priorità: bloccante. Chi lo fa: agente. Rischio esterno: nessuno.
> Contract congelato: [contracts.md](contracts.md). Spec: [README.md](README.md).

## Obiettivo
Il founder crea, modifica, archivia, ripristina ed elimina le campagne di un negozio da `/admin`, con le regole di
sicurezza di oggi della dashboard. Mettere in pausa un negozio (dashboard o `PUT /api/merchant/{id}`) archivia le sue
campagne nella stessa transazione.

## Da fare
- `campaign_crud` (nuovo) e shell admin di `campaign_service`: `list_campaigns`, `create_campaign`,
  `get_campaign_for_merchant`, `update_campaign`, `archive_campaign`, `restore_campaign`, `delete_campaign` (§5).
- `archive_on_pause` (§5) e il suo uso in `merchant_service.set_merchant_state` e `update_merchant_as_admin` (§8),
  con un solo commit e nessuna archiviazione se la modifica fallisce.
- `app/schemas/campaign.py` (`CampaignRequest`, risposta della lista) e i 6 endpoint di §9 in `app/routes/admin.py`,
  con gli header privati e `require_admin_action` su POST, PUT e DELETE.
- Sezione «Campagne» in `admin/dashboard.html` (§9): solo `textContent`, `confirm()` prima di «Elimina».
- Aggiornare il docstring di `app/routes/admin.py` (elenco degli endpoint) e la «Mappa del codice» di AGENTS.md
  (`campaign_service.py`, `campaign_crud`).
- Spec vive: crea `.agents/specs/admin.md` (dashboard di oggi più le campagne e la pausa che archivia, schede 0001 e
  0003) con la nota «da v0.4.1, non ancora in produzione».

## File coinvolti
- **Modifica**: `app/services/campaign_service.py`, `app/services/db_crud/campaign_crud.py` (nuovo),
  `app/services/merchant_service.py`, `app/schemas/campaign.py` (nuovo), `app/routes/admin.py`,
  `app/templates/admin/dashboard.html`, `tests/` (nuovi), `AGENTS.md` (mappa), `.agents/specs/admin.md`.
- **Solo lettura** (contesto): `app/core/dependencies.py`, `app/routes/merchant/api.py` (`PUT /{merchant_id}`),
  `app/services/db_crud/merchant_crud.py`, `tests/test_admin.py` (stile dei test della dashboard).

## Collaudo
Passi da aggiungere in fondo a `.agents/workflows/collaudo.md` (sezione «v0.4.1 — campagne»):
1. `/admin` → «Campagne» di un negozio attivo → crea `NATALE` (testo, importo 2,50 €, nessun limite): compare
   «attiva» con contatori a 0.
2. Crea una seconda campagna `natale!` → errore 409 leggibile; crea `CARTA` → 409; nome di 2 caratteri → 400.
3. Modifica importo e limite; «Archivia» → «archiviata»; «Ripristina» → «attiva»; «Elimina» → conferma → sparisce.
4. «Metti in pausa» il negozio → le sue campagne risultano archiviate; «Riattiva» → restano archiviate.

## Metodo
- TDD con `/implement 02`: `ft-test-writer` scrive UN test da UN criterio e il coordinatore osserva il rosso;
  `ft-implementer` scrive il minimo senza leggere il test; il contract è l'unico canale; `ft-referee` solo se test e
  codice sono entrambi difendibili.
- Commenti italiani precisi e completi (regola 4 di AGENTS.md), anche in test e script.
- `python -m pytest` verde prima del commit; commit in italiano «… (ticket 02)»; aggiorna `planner/current.md`.
- A fine ticket: riepilogo di 3 righe e attesa dell'ok. Niente push né PR.

## Stato
⬜ da fare
