# Claude Code

Leggi **AGENTS.md** nella root del progetto: è il punto di ingresso unico con regole, comandi e mappa del codice. Gli approfondimenti sono in `.agents/`.

## Dove sono nell'harness (leggere a ogni sessione)

1. Apri `.agents/planner/current.md`, blocco **«Harness»** in cima: versione, branch, fase, ticket, prossimo comando.
2. Se c'è una versione aperta, leggi `.agents/tickets/vX.Y.Z/HANDOFF.md` e la spec (`README.md`) di quella cartella.
3. Controlla che il branch corrente sia quello del blocco (`git branch --show-current`) e che `git status` non abbia
   sorprese. Se blocco, branch e stato del ticket non coincidono, **fermati e chiedi** prima di fare qualsiasi cosa.
4. Proponi al founder il prossimo comando del blocco; non avviarlo da solo (le skill partono solo da comando).

## Le skill del progetto, in ordine

Le procedure stanno in `.claude/skills/<nome>/SKILL.md` (markdown semplice: anche un agente diverso da Claude Code
può seguirle a mano). Gli agenti che usano sono in `.claude/agents/ft-*.md`.

| # | Comando | Fase nel blocco «Harness» | Cosa fa | Gate |
|---|---|---|---|---|
| 1 | `/new-feature <descrizione>` | `nessuna` → `grilling` | versione e branch decisi insieme, cartella `.agents/tickets/vX.Y.Z/`, grilling a giri | conferma dell'allineamento |
| 2 | `/spec` | `spec` → `contract` | spec con `AC-NN`, decisioni e documentazione viva; poi modello, contract, triage e ticket | **gate 1** spec, **gate 2** contract e ticket |
| 3 | `/implement [NN]` | `implementazione` | un ticket per sessione, TDD con `ft-test-writer` e `ft-implementer` separati, commit locale | ok a fine ticket |
| — | `/fix <descrizione>` | in ogni fase | aggiunta, bug o decisione cambiata → voce `F-NN` nella spec, contract sbloccato se serve, ticket nuovi | ok sulla voce (e sul contract) |
| 4 | `/review` | `implementazione` → `collaudo` | tracciabilità, review sulla spec (`ft-reviewer`) e sulle regole (`ft-standards`), push e merge su `develop` | **gate 3**, ok a ogni push e merge |
| 5 | `/release` | `collaudo` → `nessuna` | checklist, collaudo manuale da `develop`, migrazioni, PR verso `main`, deploy su DigitalOcean, tag, chiusura | ok a ogni passo verso la produzione |
| — | `/improve-architecture [area]` | fuori dal ciclo | dove il codice si aggroviglia, 2-3 opzioni, grilling su quella scelta | scelta del founder |

Regole che valgono per tutte:
- **Ogni gate è del founder**: nessuna skill lo supera da sola, e un ok vale solo per il passo per cui è stato dato.
- **Niente push, PR, merge o tag** fuori da `/review` e `/release`, e mai senza l'ok esplicito.
- **Stato sempre aggiornato**: `current.md` (blocco «Harness», tabella dei ticket, «Dove siamo»), `HANDOFF.md` e
  stato del ticket a ogni passaggio di fase e a ogni commit.
- **Documentazione viva in `.agents/`, non in AGENTS.md**: decisioni in `.agents/decisions/`, regole vigenti per area
  in `.agents/specs/`, termini in `.agents/glossario.md`, idee scartate in `.agents/fuori-scope.md`. AGENTS.md cambia
  solo per versione corrente, regole di lavoro, comandi e mappa del codice.
- Il plugin globale **lasagna non si usa in questo progetto**: niente `.lasagna/`, niente agenti `lasagna:*`. Gli
  agenti sono i `ft-*` del progetto.

## Prompt di ripartenza (da incollare in una sessione nuova)

```
Leggi CLAUDE.md, poi il blocco «Harness» di .agents/planner/current.md e l'HANDOFF della versione aperta.
Dimmi in 3 righe dove siamo (versione, fase, ticket) e quale comando proponi. Non partire finché non dico ok.
```

Per un lavoro preciso aggiungi una riga, per esempio: `Siamo su v0.4.0, ticket 05: /implement 05`, oppure
`Bug in produzione: <descrizione> → /fix`.
