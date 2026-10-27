# Roadmap Fidelitree

## Dove vogliamo arrivare (app a regime)

Una micro-SaaS **gratuita per i merchant** e a gestione leggera per il founder, che regge qualche decina di negozi:

- **Cliente**: scrive "CARTA" in DM al negozio su Instagram e riceve la sua carta (punti, cashback, alberi). Niente app,
  niente iscrizione. In seguito anche da commento a un post o risposta a una storia.
- **Merchant**: si collega da solo (oggi con la propria chiave Zernio), scansiona il QR dalla PWA, assegna tree points e
  cashback, racconta i risultati del negozio ("questo mese abbiamo piantato 5 alberi").
- **Founder**: approva i negozi, chiude il mese in un comando (poi in automatico) e pianta gli alberi con la chiave
  Ecologi di piattaforma; gestisce tutto da un'unica chiave Zernio. I ricavi arrivano da consulenza social e contenuti IA
  venduti ai merchant (modello agenzia), non dall'app.
- **Pubblico**: un contatore degli alberi piantati, base del build-in-public e della caccia ai primi 3-5 negozi pilota.
- **Tecnica**: auth dei merchant (provider locale nel pilota, Supabase più avanti), migrazioni DB, test in CI, staging separato dalla produzione.

Percorso: **v0.3.0** (carta via DM, pilota con chiave Zernio del merchant) → **pilota reale con 3-5 negozi** →
**v0.4.x** (consolidamento: contatore pubblico, cron di chiusura, dashboard) → **v0.5+** (chiave Zernio unica
del founder, trigger da commenti e storie, privacy/DPA a regime).

## Versioni

### v0.1.0 — MVP cashback ✅ rilasciata
Login merchant, carte fedeltà con QR, aggiunta/rimozione cashback, WhatsApp share.

### v0.2.0 / v0.2.1 — Pool del negozio, auth, wallet cliente (non rilasciata, assorbita da v0.3.0)
Pool mensile per negozio pagato dal founder (chiave Ecologi unica), auth merchant per email dietro un'interfaccia
pronta per Supabase, cashback e conversione tree points, logo e icone PWA. Il flusso cliente con OTP e wallet è sostituito
da v0.3.0. Storico: [`tickets/v0.2.0/STORICO.md`](../tickets/v0.2.0/STORICO.md).

### v0.3.0 — Carta fedeltà via DM Instagram (codice e documentazione completi su `feature/instagram-cards`, in attesa di collaudo e merge)
La carta nasce da un DM Instagram al negozio (parola chiave o voce di menu), ricevuto via **Zernio** e risposto con una
card che apre la pagina carta con un link segreto. Sostituisce OTP cliente, wallet, QR `/join` e la PWA cliente;
alberi, pool, cashback e auth merchant restano. Prima release in produzione dopo v0.1.0.
Decisioni: AGENTS.md; ticket e stato: [`tickets/v0.3.0/`](../tickets/v0.3.0/README.md) e [`current.md`](current.md).

### Dopo v0.3.0: verso la v0.4 di consolidamento
Dopo il rilascio e il pilota, in quest'ordine indicativo: contatore alberi pubblico, endpoint/cron per
`close_period`, dashboard merchant, CI. Le voci sono nel backlog sotto; l'ordine definitivo lo decide l'esito del pilota.

## Estensioni future del flusso Instagram (dopo v0.3.0)

### Trigger da commento a post o storia → DM
Il cliente commenta un post o risponde a una storia con la parola chiave e riceve la card in DM (evento
`comment.received` di Zernio / private reply). Il riconoscitore di trigger di v0.3.0 accetta già nuove sorgenti
(`InboundMessage.source`): si aggiunge la sorgente e l'evento al webhook. Attenzione: per le private reply Meta può
rifiutare bottoni e card ai non follower (errore 2/1545133, vedi `zernio-notes.md`).

### Follow-gate per negozio e QR temporaneo per chi non segue
- **Opzione per singolo negozio** del blocco "carta solo a chi segue" e **testo di invito scelto dal merchant** (in
  v0.3.0 il blocco vale per tutti e il testo è fisso).
- **QR temporaneo** per chi non segue: dà tree points e alberi al pool ma **niente cashback**, così partecipa comunque
  al gioco. Complessità in più, rimandata.
- **QR "apri la chat" in negozio** (`https://ig.me/m/<username>`): oggi fatto a mano dal founder; eventuale
  generazione dal pannello merchant, domande d'apertura (ice breakers) e trigger `referral` (`?ref=`) da verificare.

### Modalità chiave Zernio unica del founder
Una sola chiave di piattaforma, un `profileId` Zernio per negozio, account Instagram collegato con il connect OAuth
(`GET /v1/connect/instagram?profileId=...`) invece della chiave incollata dal merchant. Si cambia solo
`zernio_service.zernio_credentials_for` (oggi restituisce la chiave del merchant) e l'onboarding. Da valutare prima:
la quota di 10.000 invii/mese e il rate limit diventano **condivisi** tra tutti i negozi (sono per team), dal terzo
account Zernio si paga ($6/account/mese nella fascia 3-10), un webhook per negozio o uno unico instradato per `accountId`
(limite di 50 webhook per team).
Con una carta di credito sull'account di piattaforma Zernio **non si ferma** a 10.000 invii (fattura l'eccedenza):
al momento della migrazione va riconsiderato un blocco nostro (oggi c'è solo l'avviso).

### DPA con i merchant
Il negozio è titolare del trattamento, Fidelitree responsabile: serve un accordo di trattamento dati (documento, non
codice) da firmare all'onboarding. Insieme: verifica legale del testo di `/privacy`.

### Segreto del link dopo `#`
Oggi il token è nel percorso (`/c/<token>`): è mascherato nei nostri log ma resta nei log di piattaforma (DigitalOcean).
Quando l'app cresce: link `/c#<token>`, la pagina legge il token in JS e chiede i dati via API (il frammento non arriva
mai al server).

### Comando di cancellazione via DM
"CANCELLA" in DM elimina la carta e risponde con una card di conferma (oggi la cancellazione passa dal merchant).

### Pulizia automatica delle carte inattive
Script periodico (stile `close_period`) che elimina le carte senza movimenti da N mesi; il periodo va scritto
nell'informativa.

### Rotazione della chiave di cifratura
Script che ricifra chiavi Zernio e secret con una nuova `ENCRYPTION_KEY` (il formato salvato porta già l'id della chiave).
L'`IGSID_HMAC_KEY` invece non è ruotabile senza scollegare le carte.

## Backlog (in ordine di priorità indicativa)

### Collegare Supabase (più avanti, opzionale)
Deciso il 2026-10-27: nel pilota i merchant accedono con il provider `local` (ticket 11 di v0.3.0, password in una tabella
del nostro DB su **Neon**, reset dalla dashboard admin). Supabase (Auth e/o DB) si valuta quando i merchant
superano le poche decine (~100): `SupabaseAuthProvider` al posto di `local`, recupero password via email; i merchant
si reinvitano (gli hash non si migrano) e la tabella `AuthCredential` si elimina. Supabase Auth sostituisce anche le voci
"Sicurezza password" e "Integrazione Clerk" (superate).

### Endpoint admin/cron per `close_period`
Quando i negozi superano i 10-20, riusando lo stesso core di `scripts.close_period` (anteprima, idempotenza, cap).

### Ripartizione automatica del cap globale
Oggi, se la chiusura supera `ECOLOGI_GLOBAL_MONTHLY_CAP`, lo script si blocca e chiede al founder.
In futuro: ripartire in modo proporzionale/equo tra i negozi.

### Fallback scanner: codice numerico
Se il QR code fallisce (camera assente, problemi HTTPS, mancanza permessi),
il merchant deve poter inserire manualmente un codice numerico (shortcode o
UUID abbreviato della carta). Fallback robusto per ambienti difficili.

### Frontend: redirect intelligente per non autenticati
v0.3.0 (ticket 08) introduce il redirect semplice a `/merchant/login` per le pagine HTML merchant (serve alla PWA).
Resta da fare: messaggio "Accedi per continuare", ritorno alla pagina richiesta dopo il login (`next`), proposta di
`/merchant/register` ai nuovi.

### Contatore alberi pubblico
Pagina che mostra il totale alberi piantati (da `TreePlanting`, esclusi i test)
con link ai profili Ecologi pubblici dei merchant. Chiave per il build-in-public.

### Dashboard merchant
Pagina post-login con elenco carte, saldi e statistiche di base.
Oggi lo scanner è l'unica destinazione dopo il login (il vecchio bottone
"dashboard" puntava a una pagina inesistente ed è stato rimosso).

### Verifica del numero di telefono
La registrazione self-service del merchant esiste (v0.2.0, con approvazione manuale; il telefono è facoltativo).
La verifica SMS/WhatsApp del numero resta un rafforzamento futuro.

### Alembic (migrazioni DB)
Reintrodurre quando ci saranno dati di produzione da preservare tra release
(oggi lo schema si ricrea con `create_all()` + reset script).

### CI/CD migliorato (GitHub Actions)
Oggi il deploy è manuale: push su `main` → DO rebuilda e deploya (auto).
Aggiungere:
- **Test automatici in CI**: `pytest` a ogni PR (blocca merge se fallisce).
- **Lint + type check**: ruff e mypy in CI.
- **Smoke test post-deploy**: scatta su `main` dopo il deploy DO, verifica `/health` + endpoints base.
- **Status badge** nel README (build, test).
- **Ambiente di staging**: app/DB separati per `develop` e `main` (oggi c'è solo la prod).
  Opzionalmente: review app per PR (environment effimeri). Richiede account DO paid.

### Tooling qualità
ruff (lint) + mypy (type check) in pre-commit locale (vedi CI/CD sopra per il lint in GitHub Actions).

## Changelog

- **2026-10-27** — **v0.3.0** completa su `feature/instagram-cards` (11 ticket, 767 test): carta via DM Instagram con
  Zernio (webhook, card con link segreto `/c/<token>`, invito a seguire per i non follower), onboarding Instagram del
  merchant dal pannello, pagina carta e PWA solo merchant, vecchio flusso cliente (OTP, wallet, `/join`, `Customer`)
  rimosso, script riallineati (`seed_db --links`, `zernio_check --merchant-id`, `replay_webhook --event-id`,
  `smoke_test_prod`). **v0.2.1 assorbita**, mai rilasciata. In attesa del collaudo end-to-end del founder e dell'ok al
  merge. Il 2026-10-27 aggiunti i ticket 11-13 (auth `local` su Neon, stato del servizio con carta di prova e pausa,
  dashboard admin); il vecchio ticket 11 è il 14.
- **2026-10-22** — Avviata **v0.3.0** (carta via DM Instagram con Zernio): analisi, grilling e 11 ticket; **v0.2.x
  non verrà rilasciata**, assorbita da v0.3.0. Storico di v0.2.0 in `tickets/v0.2.0/STORICO.md`.
- **2026-10-13** — **v0.2.0** pronta (branch `rinascimento`, 11 ticket): pool mensile per negozio con livelli
  bronzo/argento/oro, tree points → cashback automatico, registro movimenti + contatore `MerchantPool`,
  `scripts.close_period` (anteprima, idempotente, cap globale) con Ecologi a chiave unica di piattaforma,
  iscrizione cliente (OTP) e wallet PWA, auth merchant per email con approvazione manuale, interfaccia
  `AuthProvider` (provider `dev`, Supabase in arrivo), denaro in centesimi e tempo UTC, seed/smoke test
  riallineati. La "Release 2 per-merchant" (chiave Ecologi del merchant, `mode`) è assorbita e mai rilasciata.
- **2026-07-09** — Feature Tree Points implementata su `feature/tree-points`:
  integrazione Ecologi (chiave per-merchant cifrata), soglia punti→albero,
  cap mensile, registrazione self-service con validazione chiave, pagina
  impostazioni, modalità `trees`/`trees_cashback`, tabella `TreePlanting`
  (audit), 24 nuovi test con Ecologi mockato.
- **2026-07-07** — Refactoring completo per release 1: rimossi Tree Points,
  Telegram bot, server MCP stub e Alembic; API messe in sicurezza (admin key,
  endpoint pubblici chiusi); test isolati su SQLite in-memory; script
  consolidati in `scripts/`; creato harness `.agents/` + AGENTS.md.
  Archiviata la logica alberi in `feature/trees`.
