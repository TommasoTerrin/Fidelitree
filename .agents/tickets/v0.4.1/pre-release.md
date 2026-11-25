# Pre-release v0.4.1 — campagne pilota

> Checklist di `/release` (2026-11-25). Il push su `main` deploya in produzione: nessuna voce bloccante aperta prima del merge.

## Codice
- [x] `python -m pytest` verde (1140 test, 2026-11-25, su `develop`)
- [ ] CI verde sul commit da mergiare (PR `develop` → `main`)
- [x] Dipendenze: `requirements.txt` invariato rispetto a v0.3.0
- [x] `import app.main` senza errori
- [x] Nessun segreto hardcoded nel diff (controllo con grep sul diff da v0.3.0)
- [x] Nessuna env var nuova: `.env.example` e spec DO invariati
- [x] Versione `pyproject.toml` = `0.4.1` = `EXPECTED_VERSION` di `scripts/smoke_test_prod.py`
- [ ] Tag `v0.4.1` identico alla versione

## Schema (migrazione `migrations/0001_campagne.sql`)
- [x] Branch di backup di `production` creato (`backup-2026-11-25`, `br-dark-dawn-aljzsdfc`)
- [x] Script provato su Neon `development` (12 colonne, indice `ix_campaign_merchant_id`, app avviata) — ticket 07
- [x] Su `production` (2026-11-25): 8 tabelle senza `campaign`; script applicato; 12 colonne, `campaign_pkey` e `ix_campaign_merchant_id` presenti (prima del merge)
- [ ] Rollback chiaro: codice v0.3.0 ignora `campaign`; `DROP TABLE campaign` solo accettando di perdere campagne e contatori

## Collaudo manuale (sezione «v0.4.1 — campagne» di `collaudo.md`)
Eseguito il 2026-11-25 su Instagram vero (ticket 07), esiti in `zernio-notes.md`.
- [x] 1-9 dashboard e DM · [x] 11-13 commenti e risposta privata · [x] 15-19, 21 scanner «Applica» · [x] 24 log senza testi/id
- [ ] 10 e 25 (ricollegamento) saltati: da fare per ogni merchant già collegato dopo il deploy
- [ ] 14 non follower, 22 storie, 20 negozio in attesa: rinviati (decisione del founder)
- [ ] 23 replay commento: saltato
- [x] Collaudo già fatto accettato dal founder il 2026-11-25 (opzione 1): non si ripete da `develop`; passi rinviati = rischi accettati

## Rischi accettati (review gate 3)
F-01 (AC-23, standby sui commenti, messaggio non follower, negozio in attesa con campagne), F-02 b-c, F-03, F-04 (AC-22, commento non stringa).

## Dopo il deploy
- [ ] Deploy `ACTIVE`, `/health` con versione 0.4.1, log di avvio senza segreti
- [ ] Smoke test passato
- [ ] Tabella `campaign` su Neon `production` (9 tabelle)
- [ ] Campagna di prova creata e applicata
- [ ] Merchant già collegati: scollega e ricollega per sottoscrivere `comment.received`
- [ ] Log DO senza testi dei clienti, id di commento o di post
- [ ] Tag `v0.4.1` pushato
- [ ] `develop` riallineato a `main`
