---
name: spec
description: "Fidelitree — dal grilling chiuso alla spec della versione (gate 1), poi modello di dominio, contract congelato, triage e ticket (gate 2). Usala dopo /new-feature, oppure per riprendere una spec ferma a un gate."
argument-hint: "[vX.Y.Z]"
disable-model-invocation: true
---

# /spec — spec (gate 1), modello, contract e ticket (gate 2)

Versione: **$ARGUMENTS** (se vuoto: quella del blocco «Harness» di `.agents/planner/current.md`).

**Non intervistare.** Questa skill mette insieme, non scopre. Se manca una risposta, torna al grilling: fai le
domande mancanti nel formato di `/new-feature` (frontiera, priorità, raccomandazione) e riprendi da qui.

## Orientamento

Leggi `AGENTS.md`, `current.md`, `.agents/tickets/vX.Y.Z/README.md` (grilling), `.agents/glossario.md`, i file di
`.agents/specs/` e le schede di `.agents/decisions/` delle aree toccate. Modello di riferimento per forma e livello di
dettaglio: la vecchia v0.4.0, archiviata sul branch `feature/campagne` (`README.md`, `domain-model.md`,
`contracts.md`, ticket): si legge con `git show feature/campagne:.agents/tickets/v0.4.0/<file>`.

Riprendi dalla fase indicata nello stato del `README.md`: `GRILLING CHIUSO` → fase A; `SPEC APPROVATA` → fase B.

---

## Fase A — Spec della versione (gate 1 di 3)

Riscrivi `.agents/tickets/vX.Y.Z/README.md` mantenendo in fondo il verbale del grilling. Sezioni, nell'ordine:

1. **Intestazione**: `> **Stato: SPEC IN APPROVAZIONE** (gate 1 di 3)`, data, branch.
2. **Obiettivo**: 2 paragrafi, il perché di business compreso.
3. **Glossario**: solo i termini **nuovi** della versione, con i termini di `.agents/glossario.md`; un termine
   esistente non si ridefinisce con un sinonimo.
4. **Decisioni del grilling**: numerate (1, 2, …) come le ha prese il founder.
5. **Default scelti dall'agente** (`D1`, `D2`, …): ogni scelta che hai fatto tu, da confermare al gate.
6. **Aree toccate** (sostituisce «Vincoli di AGENTS.md che cambiano»): tabella `Area (file di .agents/specs/) | Oggi |
   Con vX.Y.Z | Scheda di decisione`. Una riga per ogni regola vigente che cambia.
7. **Casi d'uso e criteri di accettazione**: `UCn — <titolo>` con attore e flusso in 1-3 righe, poi i criteri
   `AC-NN` numerati di seguito per tutta la versione. Un criterio è verificabile e dice situazione di partenza,
   azione e risultato, compresi gli effetti che **non** devono esserci.
8. **Invarianti** `I1`, `I2`, …: vere in ogni istante, senza condizioni. Una regola condizionale («se il negozio è in
   pausa…») non è un invariante: è un criterio.
9. **Errori di dominio**: tabella `Caso | Errore (app/core/errors.py) | HTTP`. Nel webhook gli errori diventano esiti,
   mai un HTTP diverso da 200/401/404.
10. **Modello dati target**: tabelle e colonne nuove o cambiate; righe «invariati» per le altre; dipendenze nuove.
11. **Assunzioni sui quattro temi** (dati non aggiornati, contesa, fallimento a metà, volumi): una riga ciascuno.
12. **Slice verticali**: tabella `# | Slice | Dipende da`. Ogni slice attraversa tutti i layer che servono e lascia
    il progetto funzionante. Se c'è un servizio esterno non ancora verificato (Zernio, Meta, Ecologi), una slice di
    **collaudo anticipato** viene prima di quelle che ne dipendono, con l'elenco di cosa verificare.
13. **Da decidere nel contract**: le scelte tecniche rimandate al gate 2.
14. **Piano di rollback**: codice (redeploy del tag precedente), schema (branch Neon di backup), enum, dati già
    scritti, effetti già usciti dal sistema (messaggi inviati, alberi piantati, webhook configurati). «Revert del
    commit» non è un piano.
15. **Fuori scope**: rimandato (→ `roadmap.md`) e scartato (→ `.agents/fuori-scope.md`).

### Le tre cose che vanno storte qui

- **Criteri solo sul percorso felice**: ogni riga della tabella degli errori e ogni caso alternativo ha il suo
  criterio con il suo id. Il revisore di `/review` cerca proprio quelli saltati.
- **Invarianti che sono regole di business** (vedi punto 8).
- **Rollback per feature invece che per slice**: dice cosa succede ai dati già scritti e agli effetti già usciti.

### Gate 1 — approvazione della spec (non automatizzabile)

Presenta in forma compatta, **e aspetta**:
- obiettivo e fuori scope in 3 righe;
- decisioni e default `Dn` da confermare, uno per riga;
- le quattro assunzioni, una riga ciascuna;
- elenco dei criteri: solo id e titolo;
- aree toccate e domande ancora aperte (bloccanti per prime).

Con l'ok del founder:
1. stato → `> **Stato: SPEC APPROVATA il AAAA-MM-GG** (gate 1 di 3; <note sulle Dn cambiate>)`;
2. **documentazione viva, subito e non a fine versione**:
   - una scheda in `.agents/decisions/` per ogni riga di «Aree toccate» (formato in `decisions/README.md`) e la
     riga nel suo indice;
   - i termini nuovi in `.agents/glossario.md`;
   - le idee scartate in `.agents/fuori-scope.md`, quelle rimandate in `roadmap.md`;
   - in `AGENTS.md` **solo** la riga «Versione corrente» in cima e, se cambia, «Mappa del codice» o «Comandi». I
     vincoli nuovi **non** vanno in AGENTS.md: stanno nelle schede;
3. `current.md`: blocco «Harness» → fase `contract`, prossimo comando `/spec` (fase B);
4. commit locale `vX.Y.Z: spec approvata (gate 1)`.

Senza l'ok resta qui. Non cominciare la fase B «nel frattempo».

---

## Fase B — Modello di dominio, contract, triage e ticket (gate 2 di 3)

### `domain-model.md`

Come quello della vecchia v0.4.0 (archivio `feature/campagne`):
- **Moduli e responsabilità**: tabella `Modulo | Cosa sa | Cosa NON sa`, e le dipendenze tra moduli (nessun ciclo).
- **Aggregati**: solo dove un invariante richiede atomicità su più righe; altrimenti dirlo («ogni invariante si regge
  su una riga o un vincolo `UNIQUE`»).
- **Regole di business e dove vivono**: tabella `R# | Regola | Sede (core/shell, funzione)`.
- **Scostamenti dalla spec**: ogni differenza, con il motivo. Al gate il founder li accetta uno per uno.

### `contracts.md`

È **l'unico canale** tra `ft-test-writer` e `ft-implementer`: quello che non c'è qui, i due agenti non lo sanno.
Intestazione: `> **Stato: IN APPROVAZIONE** (gate 2)`, convenzioni (docstring italiane, core puro, errori di
dominio, centesimi, UTC). Poi, per ogni modulo toccato:
- costanti e configurazione (env var nuove: nessuna, oppure il passo su DO e in `.env.example`);
- modelli e enum, con vincoli e cascate;
- firme del core puro (tipi, parametri, ritorno, errori sollevati, tempo e settings passati come argomenti);
- firme della shell;
- endpoint: metodo, percorso, autenticazione, corpo, risposte con codici, header;
- testi fissi dei messaggi con i limiti di caratteri;
- **Dove si testa**: per ogni slice, il confine pubblico su cui si verifica ogni criterio (funzione del core in
  `tests/unit/`, funzione della shell o endpoint in `tests/`), con una riga su cosa quel confine cattura e cosa no;
  i finti per i servizi esterni (Zernio, Ecologi) e come si controllano;
- **Cosa NON è congelato**: struttura interna, nomi privati, ordine delle operazioni, testo dei log. Nessun test ci
  può fare asserzioni.

### Triage e ticket

Ogni slice diventa un ticket `NN-slug.md` (due cifre, nell'ordine). Ogni ticket riceve il **triage**:
- **priorità**: `bloccante` (senza, la versione non esce) | `consigliato` (dentro la versione, rimandabile) |
  `opzionale` (va in roadmap se manca tempo);
- **chi lo fa**: `agente` (TDD con `/implement`) | `founder` (collaudo su Instagram vero, console DigitalOcean o
  Neon, chiavi, decisioni) | `misto` (codice dell'agente + passi del founder, elencati);
- **dipendenze**: i ticket che devono essere fatti prima;
- **rischio esterno**: se dipende da Zernio, Meta o Ecologi non ancora verificati, il ticket di collaudo anticipato
  sta prima; se il servizio si comporta diversamente dalla spec, ci si ferma e si chiede.

Ordine proposto: bloccanti prima, poi quelli che sbloccano altri ticket, i collaudi anticipati il prima possibile,
documentazione e rilascio per ultimi.

Formato del ticket:

```markdown
# Ticket NN — <titolo>

> vX.Y.Z. Dipende da: NN, NN. Criteri: AC-NN..NN; I-N.
> Priorità: bloccante | consigliato | opzionale. Chi lo fa: agente | founder | misto. Rischio esterno: nessuno | <servizio>.
> Contract congelato: [contracts.md](contracts.md). Spec: [README.md](README.md).

## Obiettivo
<2-3 righe>

## Da fare
- <puntato, con i rimandi alle sezioni del contract (§N)>

## File coinvolti
- **Modifica**: <file>
- **Solo lettura** (contesto): <file>

## Collaudo
<passi da aggiungere a `.agents/workflows/collaudo.md` se cambia ciò che vede un utente; altrimenti «nessuno»>

## Metodo
- TDD con `/implement NN`: `ft-test-writer` scrive UN test da UN criterio e il coordinatore osserva il rosso;
  `ft-implementer` scrive il minimo senza leggere il test; il contract è l'unico canale; `ft-referee` solo se test e
  codice sono entrambi difendibili.
- Commenti italiani precisi e completi (regola 4 di AGENTS.md), anche in test e script.
- `python -m pytest` verde prima del commit; commit in italiano «… (ticket NN)»; aggiorna `planner/current.md`.
- A fine ticket: riepilogo di 3 righe e attesa dell'ok. Niente push né PR.

## Stato
⬜ da fare
```

Scrivi anche:
- `HANDOFF.md` della versione (formato di `v0.4.0/HANDOFF.md` nell'archivio `feature/campagne`: dove siamo, cosa fare alla ripartenza, decisioni
  aperte, fatti verificati sui servizi esterni, vincoli di sicurezza, file di riferimento);
- in `current.md` la tabella dei ticket `# | Ticket | Priorità | Chi | Dipende da | Stato`.

### Gate 2 — approvazione di modello, contract e ticket

Presenta, **e aspetta**:
- scostamenti dalla spec (uno per riga, da accettare);
- le scelte fatte su «Da decidere nel contract»;
- la tabella dei ticket con il triage e l'ordine proposto;
- cosa farà il founder a mano (ticket `founder` e `misto`).

Con l'ok:
1. `domain-model.md` e `contracts.md` → `> **Stato: APPROVATO il AAAA-MM-GG (gate 2), CONGELATO.**`; stato della
   spec → «gate 2 approvato»;
2. `current.md`: blocco «Harness» → fase `implementazione`, prossimo comando `/implement 01`;
3. commit locale `vX.Y.Z: gate 2 approvato, ticket 01-NN`. Niente push.

Da qui il contract cambia solo con `/fix`, che lo sblocca e lo fa riapprovare.
