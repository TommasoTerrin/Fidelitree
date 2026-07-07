# Checklist pre-release (prima del merge su main)

> Il push su `main` deploya AUTOMATICAMENTE in produzione. Completa tutto prima.

## Codice
- [ ] `python -m pytest` → tutti verdi
- [ ] `python -c "import app.main"` → nessun errore di import
- [ ] Nessun segreto hardcoded nel diff (`git diff main..develop`)
- [ ] Nuove env vars aggiunte a `.env.example` e documentate in `.agents/workflows/deploy.md`

## Test manuale del flusso completo (python local_main.py)
- [ ] `/download_card?m=1` → crea carta → link WhatsApp corretto
- [ ] Apertura `/card/{uuid}` → QR visibile, saldo corretto
- [ ] Login merchant (password giusta e sbagliata)
- [ ] `/merchant/scanner` → scan/redirect a manage
- [ ] Aggiunta cashback, rimozione, tentativo sotto zero (respinto), "usa intero cashback"
- [ ] Logout

## Produzione
- [ ] Env vars su DigitalOcean allineate (vedi deploy.md)
- [ ] Dopo il deploy: smoke test (`scripts/smoke_test_prod.py`) passato
- [ ] Verifica dati su console Neon
- [ ] Tag `vX.Y.Z` creato e pushato
- [ ] `develop` riallineato a `main`

## Documentazione
- [ ] AGENTS.md / .agents/ aggiornati se cambiati comandi, endpoint o architettura
- [ ] `.agents/planner/current.md` aggiornato (item completati → changelog roadmap)
