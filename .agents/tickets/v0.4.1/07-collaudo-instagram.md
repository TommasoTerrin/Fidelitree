# Ticket 07 — Prova dello script SQL e collaudo su Instagram vero (insieme al founder)

> v0.4.1. Dipende da: 06. Criteri: AC-30 (prova dello script su Neon `development`); verifica dal vivo di AC-09..20,
> di AC-22 e dei passi dello scanner (ticket 05), e dei rischi aperti di [domain-model.md](domain-model.md).
> Priorità: bloccante. Chi lo fa: founder, con l'agente. Rischio esterno: Zernio/Meta (è il ticket in cui si verificano).
> Contract congelato: [contracts.md](contracts.md). Spec: [README.md](README.md).
> **Nato il 2026-11-13** dalla divisione del vecchio ticket 06 «misto» (vedi [06](06-documentazione-collaudo.md)):
> qui sta la parte da fare insieme. Il founder lo tiene per lunedì 2026-11-16.

## Obiettivo
Provare lo script SQL su Neon `development` e fare il collaudo su Instagram vero. Se Zernio o Meta si comportano
diversamente dal contract ci si ferma e si apre una voce `/fix` (piano B per i commenti).

## Da fare
**Founder**
1. Controllare su Neon `development` l'elenco delle tabelle (le 4 della vecchia v0.4.0 sono già state eliminate,
   commit `9c3e081`) e applicare lo script; avviare l'app e verificare che parta.
2. Collaudo locale con tunnel (`collaudo.md`): passi della sezione «v0.4.1 — campagne» su Instagram vero, compresi
   un profilo che segue e uno che non segue, una risposta a una storia, un commento `NATALE` e uno `CARTA`.
3. Riportare gli esiti, in particolare: `comment.received` arriva con l'account gratuito? la risposta privata arriva
   a un non follower? conta nella quota? un testo con molte emoji vicino a 1000 caratteri passa?
4. Se i commenti non funzionano: decidere il piano B (`/fix`).

**Agente**
- Esiti del collaudo in `zernio-notes.md` («Collaudo v0.4.1»), dettati dal founder.

## File coinvolti
- **Modifica**: `.agents/architecture/zernio-notes.md` (esiti), eventualmente `.agents/workflows/collaudo.md`.
- **Solo lettura** (contesto): `migrations/0001_campagne.sql`, `scripts/run_collaudo.py`, `.agents/workflows/deploy.md`.

## Collaudo
È il ticket del collaudo: i passi stanno in `collaudo.md` (sezione «v0.4.1 — campagne»).

## Dopo questo ticket
`/review` (gate 3: review, push e merge su `develop`, ognuno con l'ok esplicito), poi `/release` (checklist,
collaudo da `develop`, script SQL su `production` dopo il branch di backup, PR verso `main`, deploy su DigitalOcean,
tag). Il deploy non è dentro questo ticket: lo fa `/release`, passo per passo con l'ok del founder.

## Metodo
- Si avvia con `/implement 07` (ticket «founder»: passi numerati con URL completi ed esito atteso, comandi PowerShell
  uno per riga, segreti solo nel terminale del founder, esiti solo ok / non ok e tempi).
- Se un servizio esterno si comporta diversamente dalla spec: fermarsi e chiedere, nessun adattamento del codice da solo.
- Commit in italiano «… (ticket 07)»; aggiorna `planner/current.md`.
- A fine ticket: riepilogo di 3 righe e attesa dell'ok. Niente push né PR. Push e merge solo in `/review`.

## Stato
✅ con riserve, 2026-11-25. Eseguiti: script SQL su `development` (12 colonne), collaudo dashboard, DM, commenti, scanner, log. Rinviati: passo 14 (profilo che non segue, con il messaggio «devi prima seguire la pagina» da chiarire), passo 20 (negozio in attesa), passo 22 (storie). Saltati: 10, 23, 25. Esiti in `.agents/architecture/zernio-notes.md`.
