---
name: implement
description: "Fidelitree — esegue UN ticket della versione aperta con TDD a due subagenti separati (ft-test-writer e ft-implementer, ft-referee solo per le dispute), rosso osservato, budget di tentativi, poi commit locale e handoff. Usala dopo il gate 2, un ticket per sessione."
argument-hint: "[NN]"
disable-model-invocation: true
---

# /implement — un ticket per sessione, con TDD

Ticket: **$ARGUMENTS** (se vuoto: il primo ticket `⬜ da fare` o `🔶 in corso` della tabella in `current.md`,
rispettando le dipendenze). Un ticket senza triage (scritto prima di queste skill) vale come `bloccante`, `agente`.

Questa skill **coordina**. Non scrivere tu i test e non scrivere tu il codice dei criteri: l'isolamento tra i due
ruoli è il meccanismo, e crolla nel momento in cui un solo contesto fa entrambe le cose.

## Prima di partire

1. Leggi `AGENTS.md`, `current.md` (blocco «Harness»), `.agents/tickets/vX.Y.Z/HANDOFF.md`, il ticket,
   `contracts.md` e i file di `.agents/specs/` delle aree del ticket.
2. Controlli, e fermati se uno fallisce:
   - il contract è `CONGELATO` (gate 2 approvato);
   - le dipendenze del ticket sono `✅`;
   - sei sul branch della versione e `git status` è pulito (o contiene solo il lavoro di questo ticket);
   - `python -m pytest -q` è verde: annota il numero di test di partenza.
3. Stato del ticket → `🔶 in corso (AAAA-MM-GG)`; blocco «Harness» di `current.md` → ticket NN.
4. Dimmi in 3 righe cosa farai: criteri del ticket nell'ordine in cui li prendi, file toccati, eventuali passi del
   founder.

## Ticket «founder» o «misto»: i passi a mano

Per collaudi anticipati, console di DigitalOcean o Neon, chiavi:
- dai i passi come **elenco numerato** con gli URL completi e l'esito atteso;
- comandi PowerShell **uno per riga e corti**, niente blocchi su più righe da incollare, niente `python -c` lunghi
  (meglio uno script in `scripts/`), niente punteggiatura subito dopo un comando;
- i segreti li digita il founder nel suo terminale (`Read-Host -AsSecureString`), mai in chat né come argomenti;
- negli esiti si scrive solo ok / non ok e i tempi misurati, nel ticket e (per Zernio/Meta) in
  `.agents/architecture/zernio-notes.md`;
- se un servizio esterno si comporta diversamente dalla spec: **fermati e chiedi**, non adattare il codice da solo.

Il codice di un ticket misto segue il ciclo qui sotto.

## Il ciclo, un criterio alla volta

Prendi **un** criterio del ticket ancora aperto. Preferisci il più semplice tra quelli che sbloccano gli altri.

### Rosso

Avvia `ft-test-writer` (Agent, `subagent_type: ft-test-writer`) passandogli **solo**:
- il testo del criterio con id e versione;
- il percorso di `contracts.md`;
- il file di test in cui scrivere e il comando per eseguire un test.

Non la spec intera, non i criteri futuri, non il tuo ragionamento.

Quando torna, **il rosso lo osservi tu**: esegui `python -m pytest <file>::<test> -q` e leggi l'output. Non fidarti
del resoconto dell'agente.

| Esito osservato | Cosa fai |
|---|---|
| fallisce all'import o con 404 su una route nuova | Rosso legittimo: il simbolo non esiste. Avanti. |
| fallisce su un'asserzione | Rosso legittimo e migliore. Avanti. |
| **passa subito** | O il criterio è già coperto (segnalo `coperto` e passa al successivo), o il test è troppo permissivo: rimandalo a `ft-test-writer` perché lo stringa. **Non andare avanti.** |
| errore che non capisci (fixture, sintassi) | Guarda l'output prima di spendere un tentativo. |

Se il test-writer dice che il contract è insufficiente: fermati, porta la riga mancante al founder e proponi `/fix`.

Osservato il rosso, **fotografa il lavoro del test-writer nell'indice**: `git add tests/`. Da qui in poi l'indice è
il riferimento per controllare che l'implementer non tocchi i test.

### Verde

Avvia `ft-implementer` (`subagent_type: ft-implementer`) passandogli **solo**:
- il percorso di `contracts.md`;
- percorso e nome del test;
- le righe del fallimento che contano;
- il comando del test.

**Mai** la risposta completa del test-writer, mai la spec, mai i criteri futuri.

Quando torna:
1. Controlla `tests/` **rispetto all'indice** (che contiene il test appena scritto): `git diff --name-only -- tests/`
   (file modificati) e `git status --porcelain -- tests/` (righe `??` = file nuovi). Se l'implementer ha toccato
   qualcosa, ripristina dall'indice con `git checkout -- tests/` (torna alla fotografia, **non** all'ultimo commit:
   il test del test-writer resta) e cancella i file nuovi non tracciati sotto `tests/`. Il tentativo conta come
   fallito e lo rimandi indietro ricordandogli il vincolo.
2. Esegui di nuovo il test tu.

### L'arbitro

Solo per un **fallimento di asserzione ambiguo**: il test pretende una cosa, il codice ne fa un'altra, ed entrambi
sembrano difendibili rispetto al contract (di solito quando l'implementer allega un'obiezione). Non per un errore di
import, non quando la risposta è ovvia.

Avvia `ft-referee` con: testo del criterio, percorso del contract, percorso e nome del test, output del fallimento,
obiezione. **Non** l'implementazione. Verdetti:
- **TEST SBAGLIATO** → torna a `ft-test-writer` con l'appiglio del verdetto;
- **CODICE SBAGLIATO** → torna a `ft-implementer` con l'appiglio;
- **CRITERIO AMBIGUO** → **fermati** e fai al founder la domanda scritta dall'arbitro. La risposta diventa una voce
  `/fix` se cambia spec o contract.

### Chiusura del ciclo

Verde: esegui **tutta** la suite (`python -m pytest -q`): un verde locale non dice nulla sulle regressioni. Poi
aggiungi una riga al registro TDD nella sezione «Stato» del ticket:

```
- AC-NN → tests/<file>::<test> — rosso <import|asserzione>, verde al tentativo N
```

e passa al criterio successivo.

## Budget

**3 tentativi dell'implementer sul core puro, 5 sulla shell** (DB, HTTP, Zernio), per criterio. Li conti tu nel
registro. Esaurito il budget **il ciclo si ferma**: non c'è un quarto tentativo silenzioso. Porta al founder il
criterio bloccato, il verdetto dell'arbitro se c'è stato, e le due o tre ipotesi sul perché il rosso non si chiude.
Se la causa è un contract insufficiente, la risposta non è un altro ciclo: `/fix`, contract sbloccato e riapprovato,
budget azzerato.

## Lavori che non sono criteri

Le parti del ticket che non hanno un `AC-NN` (documentazione, passi di `collaudo.md`, seed, script di supporto
senza regole) le scrivi tu direttamente, con i commenti della regola 4. Se ti accorgi che una di queste ha una
regola da verificare, è un criterio mancante: proponi `/fix`.

## Fine del ticket

1. `python -m pytest -q` verde sull'intera suite (annota il numero di test).
2. **Documentazione viva**:
   - passi del ticket in fondo a `.agents/workflows/collaudo.md` (URL, azione, atteso) se cambia ciò che vede un
     utente;
   - file dell'area in `.agents/specs/` aggiornato se il ticket ha reso vera una regola nuova, con la nota
     «(da vX.Y.Z, non ancora in produzione)»; se il file dell'area non esiste, crealo (vedi `specs/README.md`).
     **Solo da v0.5.0 in poi**: per v0.4.0 si salta questo punto e le regole restano in AGENTS.md;
   - `overview.md`, `zernio-notes.md`, `.env.example`, `deploy.md` se sono cambiati endpoint, flussi, vincoli dei
     servizi esterni o env var.
3. Stato del ticket → `✅ fatto il AAAA-MM-GG (N test verdi; attende l'ok)` con: cosa è stato fatto, scelte fatte
   dove il contract lasciava libertà, limiti noti. Tieni il registro TDD.
4. `current.md`: tabella dei ticket, «Dove siamo», blocco «Harness» (prossimo comando: `/implement <NN successivo>`,
   o `/review` se era l'ultimo).
5. `HANDOFF.md` aggiornato per una sessione che riparte da zero: dove siamo, cosa fare alla ripartenza, decisioni
   aperte, fatti verificati.
6. Commit locale in italiano: `<cosa fa il ticket> (ticket NN)`, con solo i file del ticket. Niente push, niente PR.
7. Riepilogo di 3 righe al founder e **attesa dell'ok** prima del ticket successivo.
