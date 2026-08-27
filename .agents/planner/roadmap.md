# Roadmap Fidelitree

## Release 1 — MVP Cashback (v0.1.0) ✅ rilasciata

Login merchant, carte fedeltà con QR, aggiunta/rimozione cashback, WhatsApp share.

## Release 2 — Tree Points 🌳 (in corso su `feature/tree-points`)

Re-implementazione pulita (decisioni advisory 2026-07-09):
- **Solo Ecologi** (€0,80/albero, EUR, test mode nativo); DigitalHumani scartato.
- **Account Ecologi per-merchant**: il merchant paga i propri alberi, chiave cifrata nel DB.
- **Alberi obbligatori**: modalità merchant `trees` o `trees_cashback` (niente solo-cashback).
- **Registrazione self-service** `/merchant/register` gated dalla chiave Ecologi valida.
- Soglia punti→albero e **cap mensile** (spend cap) configurabili da `/merchant/settings`.
- `ECOLOGI_TEST_MODE` env: default true, false solo in produzione.

Fase 2 (dopo il lancio): pagina pubblica contatore alberi + guida onboarding Ecologi.

### Test con chiave Ecologi reale (fine release 2)
Completare i 3 test API rimasti: registrazione con validazione chiave,
cambio chiave da settings, piantumazione reale al superamento soglia.
Serve account pay-as-you-go su Ecologi (gratuito), tenere `ECOLOGI_TEST_MODE=true`.
Vedi [current.md](.agents/planner/current.md) "⏭️ PROSSIMO".

## Backlog (in ordine di priorità indicativa)

### Fallback scanner: codice numerico
Se il QR code fallisce (camera assente, problemi HTTPS, mancanza permessi),
il merchant deve poter inserire manualmente un codice numerico (shortcode o
UUID abbreviato della carta). Fallback robusto per ambienti difficili.

### Frontend: redirect intelligente per non autenticati
Oggi l'app ritorna 401 a chi non è loggato. Migliorare UX: redirect a
`/merchant/login` con messaggio "Accedi per continuare" oppure `/merchant/register`
se nuovo. Vale per `/merchant/settings`, `/merchant/scanner`, `/merchant/card/.../manage`.

### Contatore alberi pubblico

### Contatore alberi pubblico
Pagina che mostra il totale alberi piantati (da `TreePlanting`, esclusi i test)
con link ai profili Ecologi pubblici dei merchant. Chiave per il build-in-public.

### Dashboard merchant
Pagina post-login con elenco carte, saldi e statistiche di base.
Oggi lo scanner è l'unica destinazione dopo il login (il vecchio bottone
"dashboard" puntava a una pagina inesistente ed è stato rimosso).

### Sicurezza password
Passare da Fernet (reversibile) a hashing bcrypt richiede prima un flusso di
recupero/reset password (decisione presa il 2026-07-07: Fernet finché non
esiste il recovery).

### Integrazione Clerk (Autenticazione Esterna)
Valutare l'integrazione di Clerk per l'autenticazione dei merchant. Questo delegherebbe la sicurezza delle password e fornirebbe il recupero password/email out-of-the-box (tramite il dominio/mail di default di Clerk), evitando di dover configurare server SMTP proprietari o flussi di reset manuali.

### Verifica del numero di telefono
La registrazione self-service esiste (release 2, gated dalla chiave Ecologi).
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
