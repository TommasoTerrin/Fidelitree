# Stato corrente

> Aggiorna questo file a inizio e fine sessione di lavoro.
> Item completati → spostali nel changelog di `roadmap.md`.

## In corso

- Release v0.1.0: refactoring completato su `develop`, in attesa di:
  1. verifica finale + test manuale del flusso
  2. allineamento env vars su DigitalOcean (aggiungere `ADMIN_SECRET_KEY`,
     `DATABASE_URL` completa; rimuovere `HUMANI_*`, `TELEGRAM_*`, `ECOLOGI_*`,
     `BASE_URL`, `DATABASE_PASSWORD`)
  3. merge `develop` → `main` (= deploy automatico)
  4. reset + seed del DB Neon, smoke test, tag `v0.1.0`

## Prossimo

- Vedi backlog in `roadmap.md` (prima candidata: dashboard merchant).

## Note per chi riprende il lavoro

- La vecchia logica alberi/Telegram è in `feature/trees` (branch di archivio, non mergiare).
- I test girano offline (SQLite in-memory): `python -m pytest`.
