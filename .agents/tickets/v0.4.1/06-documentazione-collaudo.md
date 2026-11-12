# Ticket 06 — Documentazione, prova dello script SQL e collaudo su Instagram vero

> v0.4.1. Dipende da: 01, 02, 03, 04, 05. Criteri: AC-30; verifica dal vivo di AC-09..20 e dei rischi aperti di
> [domain-model.md](domain-model.md).
> Priorità: bloccante. Chi lo fa: misto. Rischio esterno: Zernio/Meta (è il ticket in cui si verificano).
> Contract congelato: [contracts.md](contracts.md). Spec: [README.md](README.md).

## Obiettivo
Chiudere la documentazione, provare lo script SQL su Neon `development` e fare il collaudo su Instagram vero. Se
Zernio o Meta si comportano diversamente dal contract ci si ferma e si apre una voce `/fix` (piano B per i commenti).

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
- Esiti del collaudo in `zernio-notes.md` («Collaudo v0.4.1»), dettati dal founder.

**Founder**
1. Controllare su Neon `development` l'elenco delle tabelle (le 4 della vecchia v0.4.0 sono già state eliminate,
   commit `9c3e081`) e applicare lo script; avviare l'app e verificare che parta.
2. Collaudo locale con tunnel (`collaudo.md`): passi della sezione «v0.4.1 — campagne» su Instagram vero, compresi
   un profilo che segue e uno che non segue, una risposta a una storia, un commento `NATALE` e uno `CARTA`.
3. Riportare gli esiti, in particolare: `comment.received` arriva con l'account gratuito? la risposta privata arriva
   a un non follower? conta nella quota? un testo con molte emoji vicino a 1000 caratteri passa?
4. Se i commenti non funzionano: decidere il piano B (`/fix`).

## File coinvolti
- **Modifica**: `.agents/workflows/deploy.md`, `.agents/workflows/collaudo.md`, `.agents/architecture/overview.md`,
  `.agents/architecture/zernio-notes.md`, `.agents/checklists/pre-release.md`, `.agents/specs/*.md`, `AGENTS.md`,
  `scripts/replay_webhook.py`, `tests/test_scripts.py`.
- **Solo lettura** (contesto): `migrations/0001_campagne.sql`, `scripts/run_collaudo.py`.

## Collaudo
È il ticket del collaudo: i passi stanno in `collaudo.md` (sezione «v0.4.1 — campagne»).

## Metodo
- Parte dell'agente: TDD con `/implement 06` solo per `replay_webhook` (un test da un criterio, rosso osservato);
  il resto è documentazione verificata contro il codice.
- Commenti italiani precisi e completi (regola 4 di AGENTS.md), anche in test e script.
- `python -m pytest` verde prima del commit; commit in italiano «… (ticket 06)»; aggiorna `planner/current.md`.
- A fine ticket: riepilogo di 3 righe e attesa dell'ok. Niente push né PR. Push e merge solo in `/review`.

## Stato
⬜ da fare
