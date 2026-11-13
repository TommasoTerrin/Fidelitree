# Ticket 01 — Versione 0.4.1, modello `Campaign`, script SQL e core delle campagne

> v0.4.1. Dipende da: —. Criteri: AC-03 (core), AC-27, AC-28, AC-29; I2 (regola pura), I7, I8.
> Priorità: bloccante. Chi lo fa: agente. Rischio esterno: nessuno.
> Contract congelato: [contracts.md](contracts.md). Spec: [README.md](README.md).

## Obiettivo
Mettere le fondamenta senza cambiare nulla di visibile: versione 0.4.1, `normalize_text` in `app/core/text.py`,
tabella `campaign` con il suo script SQL a mano e tutto il core puro di `campaign_service` (validazioni, parola
chiave, testi dei DM, limite, stato, etichette dello scanner, inizio della pausa).

## Da fare
- `pyproject.toml` e `EXPECTED_VERSION` di `scripts/smoke_test_prod.py` a `0.4.1` (§1).
- `app/core/text.py` con `normalize_text` (spostata, identica) e `INSTAGRAM_TEXT_MAX`; ri-export in
  `instagram_service` (§2). Base dall'archivio: `git show 5d8a4d9 -- app/core/text.py` (senza la parte sul fuso).
- Modello `Campaign` e `Merchant.campaigns` (§3).
- `migrations/0001_campagne.sql` e `tests/test_migrations.py` (§10). La cartella `migrations/` locale esiste vuota e
  non tracciata: il file nuovo la porta in git.
- `app/services/campaign_service.py`, sezione `# --- Core puro ---` completa (§4): `RequestChannel`, `CampaignStatus`,
  `CampaignInput`, `CampaignKey`, `validate_campaign_input`, `keyword_conflict`, `campaign_status`, `match_campaign`,
  `is_within_limit`, `pause_begins`, `scanner_label`, i testi, `CampaignRow`, `campaign_row`, `ScannerCampaign`.
  Nessuna shell in questo ticket.
- Spec vive: crea `.agents/specs/campagne.md` (campagna, campi, parola chiave, testi: «da v0.4.1, non ancora in
  produzione») e `.agents/specs/dati-e-segreti.md` (migrazioni con script SQL a mano, scheda 0005; nessun dato dei
  clienti nelle campagne, I6), partendo da AGENTS.md; aggiorna la tabella di `.agents/specs/README.md`.

## File coinvolti
- **Modifica**: `pyproject.toml`, `scripts/smoke_test_prod.py`, `app/core/text.py` (nuovo),
  `app/services/instagram_service.py` (solo l'import di `normalize_text`), `app/models/models.py`,
  `app/services/campaign_service.py` (nuovo), `migrations/0001_campagne.sql` (nuovo), `tests/unit/` (nuovi),
  `tests/test_migrations.py` (nuovo), `.agents/specs/*`.
- **Solo lettura** (contesto): `app/core/money.py`, `app/core/enums.py`, `app/core/errors.py`,
  `app/services/card_service.py`, `tests/test_version.py`.

## Collaudo
Nessuno (nessuna modifica visibile).

## Metodo
- TDD con `/implement 01`: `ft-test-writer` scrive UN test da UN criterio e il coordinatore osserva il rosso;
  `ft-implementer` scrive il minimo senza leggere il test; il contract è l'unico canale; `ft-referee` solo se test e
  codice sono entrambi difendibili.
- Commenti italiani precisi e completi (regola 4 di AGENTS.md), anche in test e script.
- `python -m pytest` verde prima del commit; commit in italiano «… (ticket 01)»; aggiorna `planner/current.md`.
- A fine ticket: riepilogo di 3 righe e attesa dell'ok. Niente push né PR.

## Stato
✅ fatto il 2026-11-12 (1066 test verdi, partenza 1056; attende l'ok).

**Fatto**: versione 0.4.1 (AC-29); `app/core/text.py` con `normalize_text` e `INSTAGRAM_TEXT_MAX` (ri-esportata da
`instagram_service`); modello `Campaign` e `Merchant.campaigns`; `migrations/0001_campagne.sql` con il suo test
(AC-28); tutto il core puro di `campaign_service` (AC-03, AC-27, parte pura di AC-04, AC-08, AC-01, AC-21, AC-23);
spec vive `campagne.md` e `dati-e-segreti.md`. Nessuna shell, nessuna modifica visibile (nessun passo di collaudo).

**Scelte dove il contract lasciava libertà**: un `float` senza parte decimale (`5.0`) è ammesso come limite; il
test-writer non fissa le parole dei messaggi d'errore (il contract dice solo «campo e regola, mai il valore»), quindi i
test controllano solo che il messaggio non sia vuoto e non contenga il valore inviato.

**Limiti noti**: lo script SQL non è eseguito su Postgres (collaudo nel ticket 06); `ScannerCampaign` si costruisce
nella shell di `scanner_campaigns` (ticket 05), qui è provata solo l'etichetta; il legame con `campaign_row`
nella pagina admin si vede nel ticket 02.

### Registro TDD
- AC-29 → tests/test_version.py::test_versione_0_4_1_in_pyproject_e_nello_smoke_test — rosso asserzione, verde al tentativo 1 (suite: 1057)
- AC-28 → tests/test_migrations.py::test_script_contiene_ogni_colonna_e_vincolo_del_modello_senza_alter — rosso import, verde al tentativo 1 (suite: 1058)
- AC-03 (fetta nome e parola chiave) → tests/unit/test_campaign_core.py::test_nome_e_parola_chiave_validati_con_strip_e_senza_normalizzazione — rosso import, verde al tentativo 1 (suite: 1059)
- AC-03 (fetta testo e importo) → tests/unit/test_campaign_core.py::test_testo_promo_e_importo_validati_ai_limiti_della_decisione_12 — rosso asserzione, verde al tentativo 1 (suite: 1060)
- AC-03 (fetta limite e corpo non dict) → tests/unit/test_campaign_core.py::test_limite_richieste_e_corpo_non_dict_validati_ai_limiti_della_decisione_12 — rosso asserzione, verde al tentativo 1 (suite: 1061). Scelta: un `float` senza parte decimale (`5.0`) è ammesso come limite, il contract vieta solo quelli con decimali.
- AC-27 (fetta testo promo ed «esauriti») → tests/unit/test_campaign_texts.py::test_testo_promo_ha_la_riga_fissa_e_con_850_caratteri_sta_sotto_il_limite — rosso import, verde al tentativo 1 (suite: 1062). L'implementer ha scritto già anche gli errori di `build_promo_text`, `campaign_reply_text` e `is_within_limit`: i test della fetta successiva possono passare subito (vanno letti come copertura, non come prova del rosso).
- AC-27 (fetta errori e limite) → tests/unit/test_campaign_texts.py::test_errori_dei_testi_e_scelta_tra_promo_e_offerte_terminate_al_limite — passa subito (codice già scritto nel verde precedente): segnato `coperto`; test controllato con una mutazione (`<=` → `<` nel limite) che lo fa fallire, poi ripristinata (suite: 1063)
- AC-04 (parte pura: `keyword_conflict`, `match_campaign`) → tests/unit/test_campaign_rules.py::test_parola_chiave_confrontata_in_forma_normalizzata_con_carta_e_altre_campagne — rosso import, verde al tentativo 1 (suite: 1064)
- AC-08 (regola `pause_begins`), AC-01/AC-21 (`campaign_status`), AC-23 (`scanner_label`) → tests/unit/test_campaign_rules.py::test_stato_campagna_inizio_pausa_ed_etichetta_scanner — rosso import, verde al tentativo 1 (suite: 1065)
- AC-01 / AC-21 / AC-23 (parte pura: `campaign_row`, `RequestChannel`, `ScannerCampaign`) → tests/unit/test_campaign_rows.py::test_riga_campagna_con_tutti_i_campi_stato_derivato_e_data_in_utc — rosso import, verde al tentativo 1 (suite: 1066)
- (senza criterio) `normalize_text` spostata in `app/core/text.py` con ri-export in `instagram_service`: suite invariata a 1058.

