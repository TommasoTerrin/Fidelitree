# Checklist pre-release (prima del merge su main)

> Il push su `main` **deploya AUTOMATICAMENTE in produzione**. Completa tutto prima.
> Valida per v0.3.0 (carta via DM Instagram). Le voci spuntate sono quelle verificate; le altre vanno fatte e spuntate.

## Codice
- [x] `python -m pytest` → tutti verdi (1049 test al 2026-10-27)
- [x] `python -c "import app.main"` → nessun errore di import (serve il `.env` con le tre chiavi di cifratura)
- [ ] Nessun segreto hardcoded nel diff (`git diff main..develop`)
- [x] Nuove env vars aggiunte a `.env.example` e documentate in `.agents/workflows/deploy.md`
- [x] Versione in `pyproject.toml` = `0.3.0`, uguale a `EXPECTED_VERSION` in `scripts/smoke_test_prod.py` (un test le confronta); il tag `vX.Y.Z` sarà identico (vedi `.agents/workflows/development.md`)
- [ ] In produzione `ENVIRONMENT=production` e `AUTH_PROVIDER=local` (con `dev` l'app rifiuta di partire, `supabase` è ancora uno stub); `ADMIN_SECRET_KEY` impostata, lunga e casuale (è anche la password di `/admin`)
- [ ] In produzione `DEV_AUTH_PASSWORD` non impostata (serve solo al provider `dev`)
- [ ] `ENCRYPTION_KEY`, `IGSID_HMAC_KEY` e `CARD_LINK_KEY` **generate da zero** (tre valori diversi, salvate nel password manager); la vecchia `ENCRYPTION_KEY` Fernet di v0.1.0 non va riusata
- [ ] `PUBLIC_BASE_URL` = dominio https di produzione

## Test manuale del flusso completo (in locale, DB usa-e-getta e tunnel: «Collaudo end-to-end» in `deploy.md`)
Prerequisito: SQLite usa-e-getta (`DATABASE_URL=sqlite:///...` solo nel terminale), `python -m scripts.reset_db --force`, server con `PUBLIC_BASE_URL` del tunnel cloudflared.
- [ ] Onboarding con una **chiave Zernio vera**: webhook visibile su Zernio, voce di menu «🌳 La mia carta» sull'account di prova
- [ ] **DM di prova** (`CARTA` da un profilo che segue il negozio): arriva la card, lo stato del negozio diventa `attivo`
- [ ] **Card su mobile**: titolo = nome del negozio, sottotitolo, bottone «Apri la carta» (non si vede su Instagram desktop: atteso)
- [ ] **Pagina carta** `/c/<token>`: QR, saldo, «Ancora X punti per € Y», livello del pool; link invariato a ogni nuovo messaggio; token inventato → 404
- [ ] **Scan** dalla PWA merchant installata sul telefono (HTTPS o tunnel): redirect a manage, **+60 tree points** → toast di conversione → pool aggiornato nella pagina e nella carta
- [ ] Voce di menu «🌳 La mia carta» → stessa card, stesso link
- [ ] Non follower: invito a seguire senza carta; dopo il follow e un nuovo `CARTA` arriva la card
- [ ] Evento duplicato (`replay_webhook --event-id` due volte): un solo invio
- [ ] `python -m scripts.zernio_check accounts --merchant-id N` OK (stato del negozio, chiave mascherata)
- [ ] **Log del server senza segreti**: né chiave Zernio, secret, IGSID, token del link, né testo dei messaggi (`/c/***` e `/webhooks/zernio/***` mascherati)
- [ ] «Scollega» → il webhook sparisce da Zernio
- [ ] Merchant: login (password giusta e sbagliata) → `/merchant/scanner`; aggiunta/rimozione cashback, tentativo sotto zero (respinto), «usa intero cashback»
- [ ] Merchant non approvato: registra un nuovo account, verifica che lo scanner si apra ma non aggiunga nulla (403, banner «In attesa di approvazione», pulsanti di aggiunta disattivati; togliere funziona) e che **non** compaia nell'anteprima di `close_period`; un cliente nuovo di quel negozio vede `/carta-di-prova`
- [ ] `python -m scripts.close_period --month AAAA-MM` (mese del seed, `ECOLOGI_TEST_MODE=true`): anteprima corretta, conferma, **seconda esecuzione senza effetti**; con `--cap` basso vedi il blocco
- [ ] `python -m scripts.ecologi_check` lanciato con la chiave di test (`ECOLOGI_TEST_MODE=true`) e con quella reale (`ECOLOGI_TEST_MODE=false`): entrambe OK, nulla sul profilo Ecologi
- [ ] Logout del merchant
- [ ] **Dashboard admin** (`/admin`): login con `ADMIN_SECRET_KEY`; il merchant appena registrato compare «In attesa»; «Avvia» → «Attivo» (lo scanner aggiunge, un cliente nuovo riceve `/c/<token>`); «Metti in pausa» → lo scanner solo toglie e la pagina carta del cliente resta identica; «Riattiva»; sesto tentativo di password sbagliata → 429; «Esci» chiude la sessione
- [ ] **Reset password dalla dashboard**: la password temporanea compare una volta sola con «Copia»; il merchant accede con quella e non con la vecchia, la sua sessione aperta decade, la cambia da Impostazioni; un merchant fermato dal 429 rientra subito dopo il reset; nessuna password né `ADMIN_SECRET_KEY` nel log del server

> Verifica parziale del 2026-10-27 (ticket 14, via HTTP su un processo vero con SQLite usa-e-getta, non nel browser): stato in attesa/attivo/pausa dello scanner, azioni della dashboard (con controllo `Origin`), reset password, cambio password, freni 429 di merchant e admin, nessun segreto nel log. Le voci sopra restano da spuntare dal founder nel browser e con Instagram.

## Produzione
- [ ] Env vars su DigitalOcean allineate (vedi `deploy.md`), **prima** del merge
- [ ] DB di produzione resettato (i dati di v0.1.0 non si migrano: «Primo deploy di v0.3.0» in `deploy.md`)
- [ ] Dopo il deploy: smoke test (`scripts/smoke_test_prod.py`) passato (include `/admin/login` e l'API admin)
- [ ] Dashboard in produzione verificata con un negozio di prova (passo 4b di «Primo deploy di v0.3.0»), poi negozio di prova eliminato
- [ ] Verifica dati su console Neon/Supabase (tabelle `merchant`, `card`, `pointtransaction`, `merchantpool`, `treeplanting`, `processedwebhookevent`, `zerniosendcounter`)
- [ ] Onboarding di un merchant pilota in produzione con la sua chiave Zernio e DM di prova riuscito
- [ ] **`/privacy` verificata dal founder** (il testo è una bozza) prima di dare il link ai clienti
- [ ] Nei **log di DigitalOcean** nessuna chiave, secret, IGSID o testo dei messaggi (il token `/c/<token>` e l'`hook_id` nel percorso dei log di accesso della piattaforma sono un trade-off accettato)
- [ ] Tag `vX.Y.Z` creato e pushato (stesso valore di `pyproject.toml`)
- [ ] `/health` riporta la versione attesa
- [ ] `develop` riallineato a `main`

## Documentazione
- [x] AGENTS.md / .agents/ allineati al codice di v0.3.0 (ticket 14)
- [ ] `.agents/planner/current.md` aggiornato (item completati → changelog roadmap)

## Esito collaudo
- v0.3.0: da compilare con gli esiti del collaudo end-to-end (tabella «Collaudo finale del ticket 14» in `.agents/architecture/zernio-notes.md`).
- Storico, v0.2.0 (2026-10-13, API, SQLite usa-e-getta; il flusso cliente con OTP e wallet non esiste più): pytest 339 verdi, API merchant, pool e conversione, registrazione non approvata e `close_period --cap 2` verificati; restavano `close_period` con Ecologi e PWA da telefono.
