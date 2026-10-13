# Roadmap Fidelitree

## Release 1 — MVP Cashback (v0.1.0) ✅ rilasciata

Login merchant, carte fedeltà con QR, aggiunta/rimozione cashback, WhatsApp share.

## v0.2.0 — Pool del negozio, auth, wallet cliente (branch `rinascimento`, pronta al merge)

Assorbe la vecchia "Release 2 — Tree Points per-merchant", **mai andata in produzione** (alberi per carta,
chiave Ecologi del merchant, `mode`): sostituita da un **pool mensile per negozio pagato dal founder** (chiave
Ecologi unica di piattaforma), iscrizione cliente con OTP + wallet PWA, auth merchant per email dietro
un'interfaccia pronta per Supabase. Regole e decisioni: AGENTS.md; dettaglio dei ticket: `.agents/tickets/v0.2.0/`.

## Backlog (in ordine di priorità indicativa)

### Collegare Supabase (prossimo passo dopo v0.2.0)
Progetto Supabase, migrazione del DB da Neon, `SupabaseAuthProvider` reale al posto del provider `dev`
(email+password per i merchant, OTP email per i clienti, recupero password), env `AUTH_PROVIDER=supabase`.
Supabase Auth sostituisce anche le voci "Sicurezza password" e "Integrazione Clerk" (superate).
Da risolvere in quell'occasione: **collegare un merchant creato dall'admin** (senza `auth_user_id`) al suo
account al primo accesso, solo con email verificata (oggi la sua email non si può registrare: 409).

### Endpoint admin/cron per `close_period`
Quando i negozi superano i 10-20, riusando lo stesso core di `scripts.close_period` (anteprima, idempotenza, cap).

### Ripartizione automatica del cap globale
Oggi, se la chiusura supera `ECOLOGI_GLOBAL_MONTHLY_CAP`, lo script si blocca e chiede al founder.
In futuro: ripartire in modo proporzionale/equo tra i negozi.

### Icona PWA vera
L'icona (`app/static/icon.svg`, `apple-touch-icon.png`) è provvisoria, generata a codice: sostituirla col logo.

### Fallback scanner: codice numerico
Se il QR code fallisce (camera assente, problemi HTTPS, mancanza permessi),
il merchant deve poter inserire manualmente un codice numerico (shortcode o
UUID abbreviato della carta). Fallback robusto per ambienti difficili.

### Frontend: redirect intelligente per non autenticati
Oggi l'app ritorna 401 a chi non è loggato. Migliorare UX: redirect a
`/merchant/login` con messaggio "Accedi per continuare" oppure `/merchant/register`
se nuovo. Vale per `/merchant/settings`, `/merchant/scanner`, `/merchant/card/.../manage`.

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
