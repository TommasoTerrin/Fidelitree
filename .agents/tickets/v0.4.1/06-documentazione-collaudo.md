# Ticket 06 — Documentazione e strumenti per il collaudo (parte dell'agente)

> v0.4.1. Dipende da: 01, 02, 03, 04, 05. Criteri: AC-30 (parte documenti: `deploy.md`).
> Priorità: bloccante. Chi lo fa: agente. Rischio esterno: nessuno (Zernio/Meta si verificano nel ticket 07).
> Contract congelato: [contracts.md](contracts.md). Spec: [README.md](README.md).
> **Diviso il 2026-11-13 su richiesta del founder**: il vecchio ticket 06 «misto» è ora 06 (agente, questo file) e
> [07](07-collaudo-instagram.md) (founder: script SQL su Neon e collaudo su Instagram vero). Contenuto invariato,
> solo smistato tra i due.

## Obiettivo
Chiudere la documentazione e preparare gli strumenti del collaudo, così che il ticket 07 sia solo prova dal vivo.

## Da fare
**Agente**
- `deploy.md`: applicazione di `migrations/0001_campagne.sql` (branch Neon di backup di `production`, prova su
  `development`, poi `production`; controllo prima che `campaign` non esista con colonne vecchie) e rollback di schema
  (`DROP TABLE campaign`, si perdono campagne e contatori).
- `collaudo.md`: sezione «v0.4.1 — campagne» completa (passi dei ticket 02-05, risposta a una storia, «Scollega» e
  ricollega per `comment.received`).
- `scripts/replay_webhook`: opzione per un evento `comment.received` firmato (`--comment TESTO --post-id ID`), se
  serve al collaudo locale senza Instagram (con test).
- Riletture: `overview.md` (flusso del webhook con le campagne e i commenti), `.agents/specs/*.md` dei ticket 01-05
  contro il codice, `pre-release.md` (voce sulla migrazione), «Mappa del codice» e «Comandi» di AGENTS.md.

## File coinvolti
- **Modifica**: `.agents/workflows/deploy.md`, `.agents/workflows/collaudo.md`, `.agents/architecture/overview.md`,
  `.agents/checklists/pre-release.md`, `.agents/specs/*.md`, `AGENTS.md`, `scripts/replay_webhook.py`,
  `tests/test_scripts.py`.
- **Solo lettura** (contesto): `migrations/0001_campagne.sql`, `scripts/run_collaudo.py`.

## Collaudo
Nessuno qui: i passi preparati in `collaudo.md` (sezione «v0.4.1 — campagne») si eseguono nel ticket 07.

## Metodo
- TDD con `/implement 06` solo per `replay_webhook` (un test da un criterio, rosso osservato); il resto è
  documentazione verificata contro il codice.
- Commenti italiani precisi e completi (regola 4 di AGENTS.md), anche in test e script.
- `python -m pytest` verde prima del commit; commit in italiano «… (ticket 06)»; aggiorna `planner/current.md`.
- A fine ticket: riepilogo di 3 righe e attesa dell'ok. Niente push né PR. Push e merge solo in `/review`.

## Stato
⬜ da fare
