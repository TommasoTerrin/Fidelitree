---
name: new-feature
description: "Fidelitree — apre una nuova feature, con versione e branch decisi insieme al founder e la cartella .agents/tickets/vX.Y.Z/, poi fa il grilling a giri fino all'allineamento. Usala quando il founder vuole iniziare una feature nuova o una versione nuova."
argument-hint: "<descrizione della feature>"
disable-model-invocation: true
---

# /new-feature — apertura e grilling

Feature richiesta: **$ARGUMENTS**

Qui **non si scrive codice e non si scrive la spec**: si producono solo risposte. La spec la scrive `/spec`.

## La regola che governa tutto

**I fatti sono compito tuo, le decisioni del founder.** Non chiedere mai quello che puoi verificare (codice,
`AGENTS.md`, `.agents/specs/`, `.agents/decisions/`, `.agents/fuori-scope.md`, `roadmap.md`, documentazione di
Zernio/Meta). Non decidere mai quello con cui il founder dovrà convivere.

## Passo 0 — Orientamento

1. Leggi `AGENTS.md`, `.agents/planner/current.md` (blocco «Harness» e «Dove siamo»), `.agents/planner/roadmap.md`,
   `.agents/fuori-scope.md` e i file di `.agents/specs/` delle aree toccate.
2. Se c'è già una versione aperta (fase diversa da «nessuna»), **fermati** e chiedi: chiuderla prima, o la nuova
   feature entra in quella come voce di `/fix`?
3. Se la feature è già in `fuori-scope.md`, dillo subito con il motivo e chiedi se va riaperta.
4. `git status`: con modifiche non committate, fermati e chiedi cosa farne.

## Passo 1 — Nome e versione, decisi insieme

Proponi, con il motivo di ciascuna scelta, e **aspetta la risposta**:
- **versione**: minore successiva (`v0.5.0`) per una feature, patch (`v0.4.1`) per una cosa piccola che non cambia
  il modello dei dati; ricorda che `pyproject.toml` e `EXPECTED_VERSION` di `scripts/smoke_test_prod.py` vanno
  allineati nel primo ticket;
- **nome del branch**: `feature/<nome-breve>` (minuscole, trattini);
- **titolo della versione** per la spec e la roadmap.

Il founder può cambiare tutto: vale la sua scelta.

## Passo 2 — Apertura (dopo l'ok)

1. `git checkout develop`, `git pull`, `git checkout -b feature/<nome>`.
2. Crea `.agents/tickets/vX.Y.Z/README.md` con l'intestazione:
   ```markdown
   # vX.Y.Z — <titolo>

   > **Stato: GRILLING** (avviato il AAAA-MM-GG). Branch `feature/<nome>` da `develop`.

   ## Richiesta iniziale
   <la descrizione del founder, parola per parola>

   ## Grilling
   <verbale dei giri: domanda, raccomandazione, risposta del founder>
   ```
3. Aggiorna `.agents/planner/current.md`: blocco «Harness» (versione, branch, fase `grilling`, prossimo comando
   `/new-feature` in corso) e una riga in «Dove siamo».

## Passo 3 — Grilling a giri

Ogni decisione si ramifica nelle decisioni che ne dipendono. La **frontiera** è l'insieme delle decisioni i cui
prerequisiti sono già risolti. A ogni giro fai **tutta la frontiera**, poi aspetti.

Formato di ogni domanda (domande in un messaggio di testo, non con il dialogo a scelta multipla: deve restare
leggibile tutto il giro):

```
D1 — <titolo> [bloccante | consigliata | opzionale]
<il problema, le opzioni con pro e contro, il rischio concreto>
→ Consiglio: <la tua raccomandazione e perché>
```

- **Bloccante**: senza risposta non si può scrivere la spec. **Consigliata**: ha un default ragionevole che proponi.
  **Opzionale**: dettaglio che si può decidere più avanti.
- Una domanda che dipende da un'altra ancora aperta va al giro **dopo**.
- Per sicurezza, privacy e soldi: prima spiega il rischio con un **esempio concreto** (cosa succede a chi, quando),
  poi le opzioni.
- Dopo ogni giro scrivi nel `README.md`, sezione «Grilling», domande, raccomandazioni e risposte.

### I quattro temi che nessuno solleva da solo

Oltre alle domande della feature, chiudi **esplicitamente** questi quattro. Se il founder dice «non è un problema»,
diventa un'assunzione scritta nella spec, non un silenzio.

- **Dati non aggiornati**: quale lettura può essere vecchia, e per quanto? Cliente e merchant possono vedere valori
  diversi nello stesso momento?
- **Contesa**: due attori toccano la stessa riga nello stesso istante (due webhook, due «Utilizza»): vince l'ultimo,
  il primo, errore esplicito? Serve un `UPDATE` condizionale o un vincolo `UNIQUE`? (Su SQLite `with_for_update` non
  fa nulla: i test non lo vedrebbero.)
- **Fallimento a metà**: l'operazione tocca più sistemi (DB, Zernio, Ecologi). Se il secondo fallisce dopo il primo,
  in che stato resta il mondo? Chi pulisce? Si può ripetere senza danni?
- **Volumi**: quante righe oggi e tra un anno (negozi, carte, eventi del webhook)? La query più pesante nel caso
  peggiore? Quando smette di funzionare il design?

### Anche questi, se la feature li tocca

- **Schema**: serve una migrazione (`migrations/NNNN_*.sql`)? Valori nuovi di enum (`ALTER TYPE`)?
- **Servizi esterni**: cosa va verificato sul servizio vero prima di scrivere il webhook o il client (diventerà un
  ticket di **collaudo anticipato**)?
- **Stato del servizio**: cosa succede con un negozio in attesa o in pausa?
- **Segreti e privacy**: dati nuovi salvati, log, link segreti?
- **Fuori scope**: cosa si esclude esplicitamente. Le idee rimandate vanno in roadmap, quelle scartate in
  `.agents/fuori-scope.md` con il motivo.

## Fine

Il grilling finisce quando la frontiera è vuota. Allora:
1. riepiloga in 10-15 righe le decisioni (numerate, saranno le `Dn` della spec) e le assunzioni sui quattro temi;
2. chiedi al founder **conferma esplicita** di essere allineati;
3. dopo la conferma: stato del `README.md` → «GRILLING CHIUSO il AAAA-MM-GG», blocco «Harness» di `current.md` →
   fase `spec`, prossimo comando `/spec`;
4. commit locale `vX.Y.Z: grilling chiuso` (solo i file di `.agents/`). Niente push.

Non passare a `/spec` da solo: lo lancia il founder.
