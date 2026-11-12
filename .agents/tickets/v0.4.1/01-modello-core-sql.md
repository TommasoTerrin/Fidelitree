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
⬜ da fare
