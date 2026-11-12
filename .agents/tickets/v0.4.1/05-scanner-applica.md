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
⬜ da fare
