---
name: improve-architecture
description: "Fidelitree — esame periodico dell'architettura: cerca dove il codice si sta aggrovigliando (moduli troppo grandi, core impuro, layer violati, duplicazioni), presenta 2-3 opportunità con le opzioni e fa il grilling su quella scelta dal founder. Non modifica il codice: il risultato diventa una voce /fix, roadmap o decisione."
argument-hint: "[modulo o area, facoltativo]"
disable-model-invocation: true
---

# /improve-architecture — dove il codice si sta aggrovigliando

Ambito: **$ARGUMENTS** (se vuoto: tutto `app/`).

Va lanciata ogni tanto: a fine versione (la propone `/release`), quando un modulo supera ~600 righe, o quando una
modifica piccola ha costretto a toccare molti file. **Non modifica il codice.**

## Passo 1 — Fatti

Raccogli da solo, senza chiedere:
- dimensioni: `wc -l app/services/*.py app/routes/**/*.py app/services/db_crud/*.py`, ordinate;
- per i moduli più grandi: numero di funzioni pubbliche, chi le chiama (Grep), dove passa il confine tra
  `# --- Core puro ---` e `# --- Shell ---`;
- import tra service (cicli o quasi-cicli), regole di business finite nelle route, query fuori da `db_crud`;
- duplicazioni evidenti tra service;
- i ticket recenti che hanno toccato molti file (`git log --stat` delle ultime versioni);
- rilievi `ft-standards` rimandati nelle ultime `/review` (spec e `STORICO.md` delle versioni).

Per un esame approfondito puoi avviare `ft-standards` con l'elenco dei moduli da esaminare al posto del diff.

## Passo 2 — 2-3 opportunità

Scegli le **2-3 opportunità** che rendono più facile il prossimo lavoro previsto in `roadmap.md` (non le più
eleganti). Per ciascuna:

```
O1 — <titolo> [consigliata | opzionale]
Dove: <file e righe>
Problema concreto: <cosa è diventato difficile o rischioso, con un esempio di modifica recente o prevista>
Opzioni:
  a) <refactoring> — costa <ticket stimati>, rende più facile <...>, rischio <...>
  b) <alternativa> — ...
  c) lasciare così — cosa succede se non si fa nulla
→ Consiglio: <la tua scelta e perché>
```

Il criterio guida è quello del progetto: **semplicità prima di tutto**, deep module con interfacce piccole, core
puro separato dalla shell nello stesso modulo. Niente astrazioni per un secondo uso che non esiste, niente pattern
enterprise. Un refactoring si giustifica solo con una difficoltà concreta.

Presenta e **aspetta** che il founder ne scelga una (o nessuna).

## Passo 3 — Grilling sull'opportunità scelta

Giri di domande nel formato di `/new-feature` (frontiera, priorità, raccomandazione), finché è chiaro:
- confine nuovo dei moduli e loro responsabilità;
- cosa **non** deve cambiare nel comportamento (i test esistenti devono restare verdi senza essere modificati;
  quelli che si devono spostare si dicono uno per uno);
- in quanti ticket piccoli si fa, ciascuno lasciando il progetto funzionante.

## Fine

Il risultato va in uno di questi posti, deciso dal founder:
- **versione aperta**: voce `/fix` (tipo «aggiunta», con i ticket di refactoring);
- **più avanti**: voce nel backlog di `roadmap.md`;
- **regola nuova** (per esempio un limite di dimensione o un confine tra moduli): scheda in `.agents/decisions/` e,
  se vale per tutti, una riga nelle regole di `ft-standards`;
- **scartata**: riga in `.agents/fuori-scope.md` con il motivo.

Aggiorna `current.md` («Dove siamo») e chiudi con un riepilogo di 3 righe.
