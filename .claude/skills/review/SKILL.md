---
name: review
description: "Fidelitree — gate 3: quando tutti i ticket della versione sono fatti, controlla suite e tracciabilità, lancia in parallelo le due review (ft-reviewer sulla spec, ft-standards sulle regole e sugli smell), la discute con il founder e, con il suo ok esplicito a ogni passo, fa push, PR e merge su develop."
argument-hint: "[vX.Y.Z]"
disable-model-invocation: true
---

# /review — review insieme e merge su `develop` (gate 3 di 3)

Versione: **$ARGUMENTS** (se vuoto: quella del blocco «Harness» di `current.md`).

**Il verde è necessario, non sufficiente.** Una suite verde dimostra che i test scritti passano, non che siano
stati scritti i test giusti, né che il codice sia ancora pulito.

## Passo 1 — Controlli automatici

1. Tutti i ticket `bloccante` e `consigliato` della versione sono `✅` (quelli `opzionale` non fatti: proponi di
   spostarli in roadmap; un ticket senza triage vale come `bloccante`). Se no, fermati.
2. `git status` pulito; `python -m pytest -q` verde (annota il numero di test).
3. **Tracciabilità**: per ogni `AC-NN` della spec non marcato `superseded` (compresi quelli delle voci `F-NN`), c'è
   almeno un test che lo cita. Gli id `AC-NN` ricominciano a ogni versione, quindi conta solo una citazione:
   - in un file di test **toccato dalla versione** (`git diff develop...HEAD --name-only -- tests/`);
   - e, se quel file contiene anche test di altre versioni, in un test la cui docstring (o quella del modulo) nomina
     `vX.Y.Z`.

   Usa Grep sugli id dentro quei file. Elenca i criteri scoperti.
4. Il diff della versione: `git diff develop...HEAD --stat`.

## Passo 2 — Le due review, in parallelo

Avvia **nello stesso messaggio** due subagenti, ciascuno con un contesto pulito:
- **`ft-reviewer`** (asse spec): versione, percorsi di `README.md`, `domain-model.md`, `contracts.md`, cartella dei
  ticket, e l'elenco dei criteri scoperti del passo 1;
- **`ft-standards`** (asse regole): punto fisso `develop`, branch corrente.

Non unire e non riordinare i due rapporti: un asse non deve nascondere l'altro.

## Passo 3 — Smista i rilievi

Vanno in posti diversi, e mescolarli è il modo in cui il lavoro si perde:
- **buchi nei test** → tornano a `/implement`: una voce `/fix` con il criterio da coprire meglio (o un criterio
  nuovo), un ticket, un ciclo per criterio. **Non scrivere tu i test mancanti tutti insieme**;
- **codice non richiesto** → o diventa un criterio nuovo con `/fix`, o si toglie (ticket);
- **violazioni delle regole e refactoring proposti** → ticket di refactoring con `/fix` (priorità dal rapporto); il
  refactoring si fa con la suite verde prima e dopo, senza cambiare comportamento;
- **rischi non coperti dalla spec** → decide il founder: diventano voci `/fix`, roadmap, `fuori-scope.md` o
  assunzioni accettate scritte nella spec.

## Passo 4 — La review insieme

Presenta al founder, compatto:
- **diff della spec**: criteri iniziali, voci `F-NN`, criteri `superseded`;
- **tabella di tracciabilità**: `AC-NN | test | ticket`;
- **i due rapporti**, separati, con la tua proposta di smistamento per ogni rilievo (bloccanti per primi);
- **test**: numero di partenza della versione → numero di oggi;
- cosa resta per il rilascio: passi di `collaudo.md` della versione, migrazioni, env var, documentazione viva da
  completare.

Decidete insieme. Se nascono ticket (rilievi bloccanti o consigliati accettati), si fanno con `/implement` e poi
si rilancia `/review`. Si va avanti solo con **zero bloccanti aperti**.

## Passo 5 — Push e merge su `develop` (ogni passo con l'ok esplicito)

Prima del push, un ultimo commit sul branch della feature, così il merge porta con sé lo stato giusto:
- spec: `> **Stato: REVIEW APPROVATA il AAAA-MM-GG** (gate 3)`;
- `current.md`: blocco «Harness» → fase `collaudo`, branch `develop`, prossimo comando `/release`; «Dove siamo»;
- `HANDOFF.md` aggiornato.

Poi chiedi l'ok **separatamente** per ciascun passo, mostrando prima il comando:
1. **push** del branch: `git push -u origin <branch>`;
2. **PR** verso `develop`: `gh pr create --base develop` con titolo `vX.Y.Z — <titolo>` e corpo: obiettivo, ticket,
   tabella di tracciabilità, sintesi dei due rapporti e come sono stati risolti, test, passi di collaudo da fare,
   migrazioni ed env var, piano di rollback. In fondo la riga di attribuzione indicata dal sistema;
3. aspetta la **CI verde** (`gh pr checks <n> --watch`); se fallisce, fermati e mostra perché;
4. **merge**: `gh pr merge <n> --merge`, poi `git checkout develop` e `git pull`.

Un rifiuto a qualunque passo ferma la skill: nessun passo si fa «intanto».

## Fine

Riepilogo al founder: PR e commit di merge, numero di test, rilievi rimandati (in roadmap o `fuori-scope.md`).
Prossimo comando: `/release`, per il collaudo in locale da `develop`.
