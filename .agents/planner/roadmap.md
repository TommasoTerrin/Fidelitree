# Roadmap Fidelitree

## Release 1 — MVP Cashback (v0.1.0) ✅ in rilascio

Login merchant, carte fedeltà con QR, aggiunta/rimozione cashback, WhatsApp share.

## Backlog (in ordine di priorità indicativa)

### Dashboard merchant
Pagina post-login con elenco carte, saldi e statistiche di base.
Oggi lo scanner è l'unica destinazione dopo il login (il vecchio bottone
"dashboard" puntava a una pagina inesistente ed è stato rimosso).

### Tree Points (re-implementazione)
La logica storica (soglia punti → albero piantato via Digital Humani/Ecologi)
vive nel branch di archivio `feature/trees`. Va **ri-progettata e re-implementata**
sopra il nuovo develop, non mergiata. Problemi noti della vecchia implementazione
da non ripetere: URL di produzione Humani rotto, credenziali di fallback hardcoded,
`project_id` hardcoded.

### Sicurezza password
Passare da Fernet (reversibile) a hashing bcrypt richiede prima un flusso di
recupero/reset password (decisione presa il 2026-07-07: Fernet finché non
esiste il recovery).

### Registrazione merchant self-service
Oggi i merchant si creano via script/API admin. Servirà onboarding con
verifica del numero di telefono.

### Alembic (migrazioni DB)
Reintrodurre quando ci saranno dati di produzione da preservare tra release
(oggi lo schema si ricrea con `create_all()` + reset script).

### Tooling qualità
ruff (lint) + mypy (type check) in pre-commit o CI GitHub Actions.

## Changelog

- **2026-07-07** — Refactoring completo per release 1: rimossi Tree Points,
  Telegram bot, server MCP stub e Alembic; API messe in sicurezza (admin key,
  endpoint pubblici chiusi); test isolati su SQLite in-memory; script
  consolidati in `scripts/`; creato harness `.agents/` + AGENTS.md.
  Archiviata la logica alberi in `feature/trees`.
