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
✅ fatto il 2026-11-13 (1074 test verdi; attende l'ok)

Fatto: `campaign_crud` (nuovo), shell admin di `campaign_service` (`list_campaigns`, `create_campaign`,
`get_campaign_for_merchant`, `update_campaign`, `archive_campaign`, `restore_campaign`, `delete_campaign`,
`archive_on_pause`), `schemas/campaign.py`, i 6 endpoint di §9 in `routes/admin.py`, la sezione «Campagne» di
`admin/dashboard.html` e l'archiviazione alla pausa in `merchant_service` (`_update_archiving_on_pause`, usato da
`set_merchant_state` e `update_merchant_as_admin`). Documentazione: `specs/admin.md` (nuovo), `specs/campagne.md`,
`specs/README.md`, mappa di AGENTS.md, passi in `collaudo.md` («v0.4.1 — campagne»).

### Registro TDD
- AC-01 → tests/test_admin_campaigns.py::test_lista_campagne_mostra_campi_stato_e_contatori_nell_ordine_di_d11 — rosso route (404), verde al tentativo 1
- AC-02 → tests/test_admin_campaigns.py::test_creazione_salva_campagna_non_archiviata_con_contatori_a_zero_e_importo_in_centesimi — rosso route (405), verde al tentativo 1
- AC-03 → tests/test_admin_campaigns.py::test_creazione_rifiuta_ogni_valore_fuori_dai_limiti_con_400_senza_eco_e_senza_scrivere — **coperto** (passava subito: validazione già in creazione e nel core del ticket 01; asserzioni verificate non permissive)
- AC-04 → tests/test_admin_campaigns.py::test_parola_chiave_in_conflitto_da_409_senza_scrivere_a_creazione_modifica_e_ripristino — rosso asserzione (PUT 404 invece di 409), verde al tentativo 1
- AC-05 → tests/test_admin_campaigns.py::test_modifica_sostituisce_ogni_campo_e_lascia_invariati_contatori_archiviazione_e_data — **coperto** (passava subito: il PUT del criterio 04 fa già tutto; attesi letterali)
- AC-06 → tests/test_admin_campaigns.py::test_archivia_e_ripristina_cambiano_solo_lo_stato_ed_elimina_cancella_la_riga_e_libera_la_parola — rosso route (DELETE 405), verde al tentativo 1
- AC-07 → tests/test_admin_campaigns.py::test_api_e_pagina_delle_campagne_seguono_le_regole_della_dashboard_admin — rosso asserzione (template senza «Campagne»), verde al tentativo 1; test corretto una volta prima del rosso (vedi sotto)
- AC-08 → tests/test_campaign_pause.py::test_la_pausa_archivia_le_campagne_nella_stessa_transazione_e_nessun_ripristino — rosso asserzione, verde al tentativo 1

Scelte dove il contract lasciava libertà o era ambiguo:
- **Header privati solo sui successi** (decisione del founder, 2026-11-13): il contract §9 dice «ogni risposta», AC-07 «regole di oggi», e oggi i 401/403/404/409 della dashboard non portano `no-store`/`noindex`/`Referrer-Policy`. Scelta: come oggi. Se in futuro si vorranno su ogni risposta, è un `/fix` che tocca tutta la dashboard.
- **`Campaign.__table_args__ = {"sqlite_autoincrement": True}`** (`models.py`, fuori dal contract §3): SQLite riusava l'id di una campagna eliminata e un secondo «Elimina» sul vecchio id cancellava quella nuova invece di dare 404. Postgres non riusa mai gli id e ignora l'opzione: lo script SQL e `test_migrations` non cambiano. Da rivedere in `/review`.
- `create_campaign` accetta un `now` facoltativo (ripiego `utc_now()`): la firma del contract resta valida.
- Gli import della shell di `campaign_service` stanno sotto `# --- Shell ---` (core puro solo stdlib e Pydantic).
- Il controllo «sparisce dallo scanner» di AC-06 è omesso: `scanner_campaigns` è del ticket 05.

Limiti noti: la pagina non è stata provata in un browser (passi 1-4 di `collaudo.md`, a cura del founder); l'atomicità
della pausa è verificata su SQLite, non su Postgres.
