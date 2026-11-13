# Ticket 05 — Scanner: campagne nella gestione della carta e «Applica»

> v0.4.1. Dipende da: 01 (02 consigliato prima, per creare campagne a mano nel collaudo). Criteri: AC-21..26; I1, I4.
> Priorità: bloccante. Chi lo fa: agente. Rischio esterno: nessuno.
> Contract congelato: [contracts.md](contracts.md). Spec: [README.md](README.md).

## Obiettivo
Dopo lo scan della carta il merchant vede le campagne non archiviate del negozio; «Applica» chiede conferma e, al
«sì», accredita l'importo della campagna sul cashback e conta un utilizzo, in una transazione. Senza campagne la
pagina è identica a oggi.

## Da fare
- Shell scanner di `campaign_service`: `scanner_campaigns`, `ApplyResult`, `apply_campaign` (§5), con l'ordine dei
  controlli 404 → 404 → 403 e i due `UPDATE` atomici in un commit.
- `GET /merchant/card/{card_id}/manage`: `campaigns` nel contesto (§9).
- `POST /api/merchant/card/{card_id}/campaigns/{campaign_id}/apply` e `ApplyCampaignResponse` (§9).
- `merchant/update_card.html`: blocco `id="campaigns-section"` solo con campagne, un bottone per campagna
  (`data-campaign-id`, `disabled` se importo > 0 e negozio non attivo), finestra di conferma esistente con il nome
  inserito solo via `textContent`, aggiornamento del cashback e toast con l'importo accreditato.
- Test: assenza di `campaigns-section` senza campagne; nessuna riga `PointTransaction` e pool invariato dopo
  «Applica»; `/c/<token>` identica prima e dopo (a parte il saldo cashback, che è il punto di «Applica»: si confronta
  la pagina con quella attesa per il nuovo saldo, come nei test di oggi).
- Spec vive: crea `.agents/specs/carta-e-scanner.md` (gestione della carta di oggi più «Applica», scheda 0004) con la
  nota «da v0.4.1, non ancora in produzione».

## File coinvolti
- **Modifica**: `app/services/campaign_service.py`, `app/services/db_crud/campaign_crud.py`,
  `app/routes/merchant/views.py`, `app/routes/merchant/api.py`, `app/schemas/campaign.py`,
  `app/templates/merchant/update_card.html`, `tests/` (nuovi), `.agents/specs/carta-e-scanner.md`.
- **Solo lettura** (contesto): `app/services/card_service.py`, `app/schemas/card.py`, `tests/test_scan.py`,
  `tests/test_service_state.py`, `tests/test_card_page.py`.

## Collaudo
Passi in `collaudo.md` (sezione «v0.4.1 — campagne»):
1. Negozio attivo con la campagna `NATALE` (2,50 €) e una senza importo: scansiona una carta → «Applica NATALE
   (+2,50 €)» e «Applica <nome>».
2. «Applica NATALE» → «no» → nulla cambia; → «sì» → cashback +2,50 € e toast; in `/admin` utilizzi = 1.
3. «Applica» sulla campagna senza importo → cashback invariato, utilizzi +1.
4. Negozio senza campagne → pagina come prima. Negozio in attesa → «Applica» con importo disattivato e banner.
5. La pagina carta del cliente `/c/<token>` mostra solo il nuovo saldo.

## Metodo
- TDD con `/implement 05`: `ft-test-writer` scrive UN test da UN criterio e il coordinatore osserva il rosso;
  `ft-implementer` scrive il minimo senza leggere il test; il contract è l'unico canale; `ft-referee` solo se test e
  codice sono entrambi difendibili.
- Commenti italiani precisi e completi (regola 4 di AGENTS.md), anche in test e script.
- `python -m pytest` verde prima del commit; commit in italiano «… (ticket 05)»; aggiorna `planner/current.md`.
- A fine ticket: riepilogo di 3 righe e attesa dell'ok. Niente push né PR.

## Stato
✅ fatto il 2026-11-13 (1137 test verdi; attende l'ok)

Fatto: shell `scanner_campaigns` e `apply_campaign` (+ `campaign_crud.apply_to_card`), `ApplyCampaignResponse`, route
`POST /api/merchant/card/{id}/campaigns/{cid}/apply`, contesto `campaigns` della pagina di gestione, blocco
`campaigns-section` e JavaScript di «Applica» nel template (dentro `{% if campaigns %}`: senza campagne la pagina non
nomina né `campaigns-section` né `data-campaign-id`). Spec viva `specs/carta-e-scanner.md`, passi 15-21 in `collaudo.md`.

Scelte dove il contract lasciava libertà: la finestra di conferma mostra l'etichetta del bottone («Applica NATALE
(+2,50 €)») con `textContent`; toast «Accreditati € X di cashback» o «Campagna applicata» (importo 0); corpo della
POST assente.

Limiti noti: AC-22 (clic su «ANNULLA») e il JavaScript del template si provano solo a mano (passi 15-17 di
`collaudo.md`, ticket 06); nessun test controlla il JS. Sette dei test del ciclo sono passati subito (`coperto`): la
route e i controlli erano già prodotti nel ciclo di AC-23, senza prova di mutazione; il test di importo 0 prova solo il
ramo «pausa», non «in attesa».

### Registro TDD
- AC-21 (con campagne) → tests/test_scanner_campaigns.py::test_gestione_carta_mostra_solo_le_campagne_non_archiviate_con_la_loro_etichetta — rosso asserzione, verde al tentativo 1 (1124 test)
- AC-23 (importo > 0) → tests/test_scanner_campaigns.py::test_applica_campagna_confermata_accredita_l_importo_attuale_e_conta_un_utilizzo — rosso import (route 404), verde al tentativo 1 dell'implementer; un giro in più sul test (difetto del test: `session.get` su `CampaignRow`, corretto dal test-writer; il tentativo non è stato contato) (1125 test)
- AC-24 (403 API, attesa e pausa) → tests/test_scanner_campaigns.py::test_applica_campagna_con_importo_su_negozio_non_attivo_risponde_403_senza_scrivere — coperto (passa subito, già prodotto dal ticket AC-23; il test distingue 403 da 200 e controlla il DB)
- AC-25 (404) → tests/test_scanner_campaigns.py::test_applica_campagna_con_carta_o_campagna_non_del_negozio_risponde_404_senza_scrivere — coperto (3 casi passano subito; nessuna mutazione provata)
- AC-26 → tests/test_scanner_campaigns.py::test_applica_campagna_non_tocca_tree_points_pool_registro_e_pagina_cliente — coperto (passa subito; confronto esatto della pagina cliente, precondizioni asserite)
- AC-25 (campagna archiviata si applica) → tests/test_scanner_campaigns.py::test_applica_campagna_archiviata_dopo_il_caricamento_della_pagina_si_applica_comunque — coperto (passa subito)
- AC-23 (importo 0) → tests/test_scanner_campaigns.py::test_applica_campagna_senza_importo_conta_solo_l_utilizzo_anche_a_negozio_non_attivo — coperto (passa subito; solo ramo pausa)
- AC-21 (senza campagne) → tests/test_scanner_campaigns.py::test_gestione_carta_senza_campagne_da_mostrare_non_ha_il_blocco_campagne — coperto (passa subito, già prodotto dal primo ciclo di AC-21)
- AC-24 (pagina: bottoni disabilitati) → tests/test_scanner_campaigns.py::test_pagina_disabilita_applica_con_importo_se_il_negozio_non_e_attivo — coperto (3 casi passano subito)
