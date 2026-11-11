---
name: fix
description: "Fidelitree — registra nella spec della versione aperta una piccola aggiunta, un bug o una decisione cambiata (voce F-NN con criteri nuovi), sblocca il contract se serve e crea i ticket da implementare dopo con /implement. Senza versione aperta propone una versione patch."
argument-hint: "<descrizione dell'aggiunta, del bug o del cambiamento>"
disable-model-invocation: true
---

# /fix — aggiunte, bug e modifiche al piano

Richiesta: **$ARGUMENTS**

Qui non si scrive codice: si aggiornano spec, contract e ticket. Il codice lo scrive `/implement` dopo.

## Passo 0 — Dove va

1. Leggi `AGENTS.md`, `current.md` (blocco «Harness»), la spec della versione aperta e `contracts.md`.
2. **C'è una versione aperta**: la voce va nella sua spec.
3. **Nessuna versione aperta** (per esempio un bug in produzione): proponi una versione patch (`v0.4.1`) con il
   motivo e un branch (`fix/<nome>` da `develop`, oppure da `main` se è urgente e `develop` contiene lavoro non
   rilasciato: spiega la differenza), **e aspetta** la scelta del founder. Poi crea `.agents/tickets/vX.Y.Z/README.md`
   minimo (obiettivo, voci F-NN, rollback) e un `contracts.md` solo per le firme toccate; i gate restano, in forma
   breve.
4. Controlla `.agents/fuori-scope.md`: se la richiesta è stata scartata in passato, dillo con il motivo.

## Passo 1 — Classifica e chiarisci

Classifica la richiesta e dillo al founder:
- **aggiunta**: comportamento nuovo piccolo, dentro lo scopo della versione (se è grande o fuori scopo, proponi una
  versione nuova con `/new-feature` o la roadmap);
- **bug**: il comportamento di oggi contraddice un criterio, un invariante o una regola vigente;
- **decisione cambiata**: una `Dn` o una decisione del grilling non vale più.

Per un **bug**, prima di tutto **riproducilo**: dai i passi (o un test esplorativo che poi butti) e scrivi cosa
succede e cosa dovrebbe succedere. Se non si riproduce, fermati e chiedi più dettagli.

Se servono decisioni, fai un giro di domande nel formato di `/new-feature` (priorità, raccomandazione, esempio
concreto per i rischi), comprese le domande dei quattro temi se la voce tocca concorrenza, servizi esterni o dati.

## Passo 2 — La voce nella spec

In fondo al `README.md` della versione, sezione `## Modifiche e correzioni` (creala se manca):

```markdown
### F-NN — <titolo> (AAAA-MM-GG) — aggiunta | bug | decisione cambiata

- **Cosa**: <descrizione>
- **Perché**: <motivo; per un bug: passi per riprodurlo, osservato, atteso>
- **Criteri nuovi**: AC-NN <testo> …
- **Criteri superati**: AC-NN → `superseded` da AC-NN (motivo)
- **Contract**: invariato | sbloccato (§N: <cosa cambia>)
- **Ticket**: NN
```

Regole sugli id:
- i criteri nuovi prendono **id nuovi** (il primo numero libero della versione): mai riusare un id e mai cambiare il
  significato di uno esistente, perché i test li citano;
- un criterio vecchio non si cancella: nel suo testo si aggiunge `— superseded da AC-NN (F-NN)`;
- un invariante nuovo prende il primo `I-N` libero.

Se la voce cambia una regola vigente: scheda nuova in `.agents/decisions/` (o la vecchia diventa «sostituita da»), e
riga in «Aree toccate».

## Passo 3 — Contract

Se la voce tocca firme, errori, endpoint, modelli o testi fissi:
1. `contracts.md` → `> **Stato: SBLOCCATO il AAAA-MM-GG per F-NN**`; scrivi le modifiche marcandole `(F-NN)`;
2. presenta al founder **solo** le parti cambiate e aspetta l'ok (gate 2 ridotto);
3. con l'ok → di nuovo `CONGELATO il AAAA-MM-GG (dopo F-NN)`.

Se un ticket è `🔶 in corso` e la modifica lo tocca, fermalo: prima si riapprova il contract, poi si riprende.

## Passo 4 — Ticket

- Crea i ticket con i **numeri successivi** all'ultimo (`10-…`, `11-…`), nel formato di `/spec`, con il triage
  completo (priorità, chi lo fa, dipendenze, rischio esterno) e i criteri `F-NN`.
- **Ticket di un bug**: il primo criterio è il test che **riproduce il bug** e deve essere rosso prima della
  correzione. Se il codice da toccare non ha test, il ticket comincia con i test che **fissano il comportamento
  attuale** delle parti che non devono cambiare (devono essere verdi subito: proteggono dalle regressioni).
- Un ticket già fatto che la voce rende sbagliato non si riscrive: il ticket nuovo lo corregge e lo cita.
- Un ticket non ancora fatto e reso inutile → stato `⛔ superato da NN (F-NN)`.

## Fine

1. `current.md`: tabella dei ticket e «Dove siamo»; `HANDOFF.md`: decisioni aperte e ticket nuovi.
2. Commit locale `vX.Y.Z: F-NN <titolo> (spec e ticket)`.
3. Riepilogo al founder: voce, criteri nuovi e superati, contract (invariato o riapprovato), ticket creati con
   triage. Prossimo comando: `/implement NN` quando vuole.
