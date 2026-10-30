# Checklist pre-release (prima del merge su main)

> Il push su `main` **deploya AUTOMATICAMENTE in produzione**. Completa tutto prima.
> Compilata per v0.3.0 (in produzione dal 2026-10-30, tag `v0.3.0` su `a83cd64`): le voci spuntate sono quelle verificate.
> Per la prossima release: copia l'elenco, togli le spunte, aggiungi le voci della feature.

## Codice
- [x] `python -m pytest` → tutti verdi (1056 test al 2026-10-30)
- [x] CI verde sul commit da mergiare (pytest, build Docker, pip-audit)
- [x] Dipendenze fissate in `requirements.txt`; se sono cambiate, **avvio vero su Neon `development`** (la CI usa SQLite: «Aggiornare le dipendenze» in `deploy.md`)
- [x] `python -c "import app.main"` → nessun errore di import (serve il `.env` con le tre chiavi di cifratura)
- [x] Nessun segreto hardcoded nel diff
- [x] Nuove env vars aggiunte a `.env.example` e documentate in `.agents/workflows/deploy.md`
- [x] Versione in `pyproject.toml` = `0.3.0`, uguale a `EXPECTED_VERSION` in `scripts/smoke_test_prod.py` (un test le confronta); il tag `vX.Y.Z` è identico
- [x] Schema: nessuna modifica rispetto alla produzione, oppure script di migrazione provato su un branch Neon + branch di backup (al primo deploy di v0.3.0: azzeramento ammesso, fatto con backup)

## Produzione: env var (prima del merge)
- [x] `ENVIRONMENT=production` e `AUTH_PROVIDER=local` (con `dev` l'app rifiuta di partire, `supabase` è uno stub)
- [x] `ADMIN_SECRET_KEY` lunga (≥ 20 caratteri): è anche la password di `/admin`, e l'header `X-Admin-Key` non ha freno
- [x] `DEV_AUTH_PASSWORD` non impostata
- [x] `ENCRYPTION_KEY`, `IGSID_HMAC_KEY` e `CARD_LINK_KEY` generate da zero (tre valori diversi, nel password manager), diverse da quelle locali
- [x] `PUBLIC_BASE_URL=https://fidelitree.app`
- [x] `DATABASE_URL` sul branch Neon `production`, endpoint diretto; password diversa da quella di `development`
- [x] Variabili sensibili cifrate (`SECRET`), tutte `RUN_TIME`, variabili morte tolte; health check `/health`
- [ ] `ECOLOGI_TEST_API_KEY` su DO (serve a `ecologi_check`/`close_period` dalla console)
- [ ] «Wait for CI» attivo (da confermare nella console)

## Collaudo manuale (in locale: [collaudo.md](../workflows/collaudo.md))
Fatto il 2026-10-28 (SQLite) e il 2026-10-30 (Neon `development`, `ENVIRONMENT=production`, `AUTH_PROVIDER=local`).
- [x] Onboarding con una chiave Zernio vera: webhook su Zernio, voce di menu «🌳 La mia carta»
- [x] DM di prova `CARTA` da un follower: card, stato del negozio `attivo`
- [x] Card su mobile e pagina carta `/c/<token>` (QR, saldo, livello del pool)
- [x] Scan dalla PWA sul telefono: +60 tree points, conversione, pagina aggiornata
- [ ] Voce di menu «🌳 La mia carta» → stessa card (**bug aperto**: il tocco non produce eventi; si scrive `CARTA`)
- [x] Non follower: invito a seguire senza carta; dopo il follow e un nuovo `CARTA` arriva la card (lento: Richieste)
- [ ] Evento duplicato con `replay_webhook --event-id` (la dedup è coperta dai test e ha scartato retry veri di Zernio)
- [x] Log del server senza segreti (`/c/***` e `/webhooks/zernio/***` mascherati)
- [x] «Scollega» → il webhook sparisce da Zernio
- [x] Negozio in attesa → `/carta-di-prova`; «Avvia» dalla dashboard → carta vera
- [x] Dashboard: login, lista, «Avvia», «Metti in pausa»; 429 al login merchant dopo 6 errori; reset password
- [ ] Dal log non risultano «Riattiva» e il cambio password dalle impostazioni (verificati solo via HTTP il 2026-10-27)
- [ ] `close_period` (`ECOLOGI_TEST_MODE=true`) e `ecologi_check` con chiave di test e reale

## Produzione: dopo il deploy
- [x] Deploy `ACTIVE` sul commit atteso, `/health` con la versione attesa, log di avvio senza segreti
- [x] DB di produzione azzerato con lo schema v0.3.0 (8 tabelle, 0 righe), backup `backup-pre-v0.3.0`
- [ ] Smoke test passato: **14/16 il 2026-10-30**, falliscono i due controlli con `X-Admin-Key` (401/403: chiave digitata diversa da quella su DO, da verificare)
- [ ] Negozio di prova: login e freno, dashboard («Avvia», pausa, reset), poi tenuto come demo o eliminato
- [ ] DM `CARTA` in produzione → card → `https://fidelitree.app/c/<token>`
- [ ] Il negozio di prova compare su Neon `production` e non su `development`
- [ ] Nei **log di DigitalOcean** nessuna chiave, secret, IGSID o testo dei messaggi
- [x] Tag `v0.3.0` creato e pushato
- [x] `develop` riallineato a `main`
- [ ] **`/privacy` verificata dal founder** prima di dare il link ai clienti
- [ ] Onboarding di un merchant pilota con la sua chiave Zernio e DM di prova riuscito

## Documentazione
- [x] AGENTS.md / `.agents/` allineati (deploy reale, rollback, `collaudo.md`)
- [x] `.agents/planner/current.md` aggiornato
