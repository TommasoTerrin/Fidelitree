# Checklist pre-release (prima del merge su main)

> Il push su `main` deploya AUTOMATICAMENTE in produzione. Completa tutto prima.

## Codice
- [ ] `python -m pytest` → tutti verdi
- [ ] `python -c "import app.main"` → nessun errore di import
- [ ] Nessun segreto hardcoded nel diff (`git diff main..develop`)
- [ ] Nuove env vars aggiunte a `.env.example` e documentate in `.agents/workflows/deploy.md`
- [ ] Versione aggiornata in `pyproject.toml` (`[project] version`) e tag `vX.Y.Z` identico (vedi `.agents/workflows/development.md`)
- [ ] In produzione `ENVIRONMENT=production` e `AUTH_PROVIDER` **≠ `dev`** (con `dev` l'app rifiuta di partire)
- [ ] In produzione `DEV_AUTH_PASSWORD` non impostata (serve solo al provider `dev`)

## Test manuale del flusso completo (in locale, su un DB usa-e-getta: vedi "Collaudo locale" in `deploy.md`)
Prerequisito: `python -m scripts.reset_db` → `python -m scripts.seed_db` → `python local_main.py`.
- [ ] Cliente: `/join/{id}` → login OTP (`000000`) → la carta compare nel `/wallet`
- [ ] Cliente: apertura della carta → QR, saldo personale, "Ancora X punti per € Y", blocco "Il progetto del negozio"
- [ ] PWA da telefono: installazione in schermata Home e apertura in standalone (serve HTTPS o tunnel; l'icona è provvisoria)
- [ ] Merchant: login (password giusta e sbagliata) → `/merchant/scanner` → scan QR carta → redirect a manage
- [ ] Merchant: **+60 tree points** → toast di conversione → pool aggiornato nella pagina e nella carta del cliente
- [ ] Merchant: aggiunta/rimozione cashback, tentativo sotto zero (respinto), "usa intero cashback"
- [ ] Merchant non approvato: registra un nuovo account, verifica che lavori ma **non** compaia nell'anteprima di `close_period`
- [ ] `python -m scripts.close_period --month AAAA-MM` (mese del seed, `ECOLOGI_TEST_MODE=true`): anteprima corretta, conferma, **seconda esecuzione senza effetti**; con `--cap` basso vedi il blocco
- [ ] Logout (merchant e cliente)

## Produzione
- [ ] Env vars su DigitalOcean allineate (vedi deploy.md)
- [ ] Dopo il deploy: smoke test (`scripts/smoke_test_prod.py`) passato
- [ ] Verifica dati su console Neon/Supabase
- [ ] Tag `vX.Y.Z` creato e pushato (stesso valore di `pyproject.toml`)
- [ ] `/health` riporta la versione attesa
- [ ] `develop` riallineato a `main`

## Documentazione
- [ ] AGENTS.md / .agents/ aggiornati se cambiati comandi, endpoint o architettura
- [ ] `.agents/planner/current.md` aggiornato (item completati → changelog roadmap)
