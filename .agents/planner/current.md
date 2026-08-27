# Stato corrente

> Aggiorna questo file a inizio e fine sessione di lavoro.
> Item completati → spostali nel changelog di `roadmap.md`.

## In corso

- **Release 2 — Tree Points** completata. Test manuali browser e API passati (15/15 test UI, 9/9 test API).
- Merge su `develop` completato in attesa di test su DigitalOcean (ambiente di staging) prima del passaggio a `main`.

  **⏭️ PROSSIMO — test su DigitalOcean:**
  1. Verificare il deploy di `develop` su DigitalOcean (se esiste un'app collegata a quel branch).
  2. Testare il flusso live.
  3. Merge su `main` per il deploy in produzione.
  4. Su DigitalOcean (produzione): aggiungere env var `ECOLOGI_TEST_MODE` (true).
  5. Reset + seed DB Neon di produzione.

## Prossimo

- Pagina pubblica contatore alberi + guida onboarding Ecologi per merchant (fase 2 pre-lancio).
- Poi lancio build-in-public e caccia ai primi 3-5 negozi pilota.

## Note per chi riprende il lavoro

- Decisioni architetturali tree points (Ecologi-only, account per-merchant, alberi
  obbligatori, cap mensile): vedi AGENTS.md "Vincoli e trade-off" e roadmap release 2.
- Gli errori Ecologi NON devono mai bloccare lo scan: punti conservati + warning.
- La vecchia logica alberi/Telegram è in `feature/trees` (branch di archivio, non mergiare).
- I test girano offline (SQLite in-memory, Ecologi mockato): `python -m pytest`.
