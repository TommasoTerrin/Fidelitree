# v0.4.1 — Campagne pilota: promo via DM e commenti Instagram

> **Stato: GRILLING CHIUSO il 2026-11-12** (avviato il 2026-11-12). Branch `feature/campagne-pilota` da `develop` (creato il 2026-11-12,
> contiene il processo a skill).
>
> **Numero di versione**: patch per scelta del founder anche se la versione aggiunge una tabella e una migrazione (la
> regola della skill vorrebbe una minore): `v0.4.0` resta all'archivio `feature/campagne` e non si riusa. Il primo
> ticket porta `pyproject.toml` e `EXPECTED_VERSION` di `scripts/smoke_test_prod.py` a `0.4.1`.

## Richiesta iniziale

Copia del brief [`.agents/planner/brief-campagne-pilota.md`](../../planner/brief-campagne-pilota.md) (commit `90cf9ca`),
scritto con il founder il 2026-11-12. Indicazione del founder all'avvio: «Le decisioni 1-11 del brief sono prese; il
grilling copre i punti A-I, i rischi da verificare e i quattro temi.»

> Scritto il 2026-11-12 con il founder, prima di `/new-feature`. È la «richiesta iniziale» del grilling: le decisioni
> qui sotto sono già prese, il grilling chiude solo i punti aperti e i quattro temi della skill. Dopo il grilling
> questo file si può eliminare (il contenuto finisce nel `README.md` della versione).

### Contesto

Rifà le campagne in forma ridotta per partire con i primi pilota. La versione precedente (v0.4.0: adesioni salvate
nella carta, pagina `/p/<token>`, secondo QR, promozioni multiple, limiti per cliente) è **archiviata** sul branch
`feature/campagne`: non si mergia, si copia solo ciò che serve. Motivo: troppa logica e troppo DB per un pilota; ora
conta partire con le cose più spettacolari e avere i primi pilota.

### Obiettivo

Il negozio pubblica una campagna su Instagram («commenta o scrivici NATALE»). Chi scrive la parola chiave riceve in
DM il testo della promo: **quel DM è il coupon** da mostrare in cassa. Il merchant scansiona la carta del cliente e
preme «Applica»: cashback accreditato e utilizzo contato. Le campagne rendono più interattivo il rapporto
negozio-clienti su Instagram (seguire, guardare i post, commentare).

### Decisioni già prese

1. **Campagna** = negozio, nome, parola chiave, testo della promo, importo di cashback, primo e ultimo giorno (ora di
   Roma), archiviata sì/no, contatori. **Una sola tabella nuova**, nessuna modifica alle tabelle esistenti.
2. **Crea, modifica, archivia solo il founder** da `/admin`. Il merchant non ha UI per crearle.
3. **Campagna attiva** = non archiviata e oggi tra il primo e l'ultimo giorno compresi. Archiviare la spegne subito.
4. **Parola chiave**: normalizzata come `CARTA`, diversa da `CARTA` (`INSTAGRAM_CARD_KEYWORD`), **unica tra le
   campagne attive** del negozio.
5. **Attivazione** da due canali: DM (risposte alle storie comprese) con la parola chiave, e **commento** a un
   qualsiasi post che contiene la parola chiave.
6. **La risposta è sempre e solo un DM di testo**, mai una risposta pubblica sotto il post. Per il commento è la
   «risposta privata» di Instagram, che arriva al cliente come DM (una sola per commento, entro 7 giorni, mai
   ritentata). Un commento con la parola chiave produce **un** invio, che arriva solo in DM: sotto il post non
   compare niente. Se la risposta privata conti nella quota Zernio come un DM è **da verificare** (il nostro
   `ZERNIO_MONTHLY_SEND_LIMIT`, 10.000, è solo il contatore per l'avviso, non la regola di Zernio).
7. **Contenuto del DM**: testo della promo + «Valida dal GG/MM al GG/MM» + (da confermare il testo esatto) «Per
   usarla devi seguirci e avere la carta: scrivici CARTA». Niente card, niente bottoni, niente link: il testo arriva
   anche a chi non segue.
8. **`CARTA` invariata**: card solo a chi segue, come oggi. Serve la carta per usare il coupon, quindi nessun
   controllo in più sulle campagne.
9. **Il coupon è il DM**: niente promo salvata nella carta, nessun limite per cliente, decide il merchant in cassa.
   Accettato: uno screenshot si può girare (è passaparola).
10. **Scanner**: la gestione della carta (dopo lo scan del QR della carta) mostra le campagne attive del negozio con
    «Applica <nome> (+X €)» → cashback sulla carta e contatori, in una transazione. Bloccato con negozio in attesa o
    in pausa, come ogni aggiunta di cashback. Tree points e pool non cambiano. La pagina carta del cliente non cambia.
11. **Contatori** visibili in `/admin`: richieste da DM, richieste da commento, utilizzi («Applica»). In più,
    proposto dall'agente e da confermare: cashback erogato.

### Da decidere nel grilling (con la raccomandazione dell'agente)

- **A. Parola chiave di una campagna finita o non ancora iniziata.** Consiglio: in DM un breve testo «promozione
  terminata / non ancora iniziata»; ai commenti nessuna risposta (non si spreca l'unica risposta). Archiviata = come
  una parola qualsiasi, ignorata.
- **B. Importo facoltativo?** Senza importo «Applica» conta solo l'utilizzo (promo in omaggio). Consiglio: facoltativo.
- **C. «Unica tra le attive»**: contano anche le campagne programmate (non ancora iniziate)? Consiglio: sì, unica tra
  le non archiviate e non finite, così due campagne con la stessa parola non si sovrappongono mai.
- **D. Modifiche**: tutto modificabile in ogni momento; il contatore del cashback erogato conserva gli importi già
  dati. Consiglio: sì.
- **E. Limiti dei campi**: nome, parola chiave, testo della promo (un DM Instagram ha al massimo 1000 caratteri),
  importo.
- **F. Richieste**: contano i messaggi, non le persone (chi scrive NATALE 3 volte conta 3). Va bene?
- **G. «Applica»**: conferma prima di accreditare? annullare un utilizzo sbagliato? Consiglio: conferma sì, annulla no
  (il cashback si toglie con il pulsante di oggi; il contatore resta).
- **H. Quota**: serve un avviso al merchant quando le campagne consumano molti invii?
- **I. Commenti dell'account stesso e commenti con più parole chiave**: ignorati / vale la prima nel testo?

### Rischi da verificare per primi (primo ticket: collaudo su Instagram vero)

- `comment.received` arriva al webhook del negozio, firmato come i DM, con l'**account Zernio gratuito** e il
  collegamento Instagram di oggi (se i negozi devono ricollegarsi o pagare: fermarsi e decidere);
- risposta privata di solo testo consegnata a un **non follower**; `{postId}` = `comment.platformPostId`;
- come riconoscere i commenti dell'account stesso (`isOwner` o altro);
- campo del testo nella risposta a una storia (`metadata.storyReply`);
- se la risposta privata a un commento consuma la quota Zernio come un DM;
- cambiare gli eventi dei webhook dei negozi già collegati senza farli ricollegare (`PUT /v1/webhooks/settings`,
  dalla spec Zernio, non ancora provato).

Se i commenti non funzionano con l'account gratuito: **piano B** = solo DM e storie, i commenti in roadmap.

### Riuso dall'archivio (`feature/campagne`)

Si copia nel ticket che ne ha bisogno, con `git cherry-pick` o `git show feature/campagne:<file>`, citandolo:
- `5d8a4d9` (ticket 01): `tzdata`, cartella `migrations/`, `normalize_text` in `app/core` (la versione va riallineata);
- `7e070ff` (ticket 02): finestra in giorni italiani, validazione e normalizzazione della parola chiave (da sfoltire:
  il resto riguarda promozioni e adesioni);
- `f681bd6` (ticket 03): sezione «Campagne» della dashboard admin e CRUD (da sfoltire);
- `621a278` (ticket 04, parziale): `zernio_service.send_private_reply`, `build_private_reply_body`, comando
  `send-private-reply` di `zernio_check`, test; note di collaudo in `zernio-notes.md` dell'archivio.
- Migrazione nuova `migrations/0001_campagne.sql` con **una sola** `CREATE TABLE`.

Attenzione: Neon `development` potrebbe avere le 4 tabelle della vecchia v0.4.0 (create da `create_all` durante un
collaudo). Prima del primo collaudo vanno controllate e, con l'ok del founder, eliminate: altrimenti
`CREATE TABLE IF NOT EXISTS campaign` lascerebbe le colonne vecchie.

### Fuori scope (da registrare in roadmap o in `.agents/fuori-scope.md` nel grilling)

Promo salvata nella carta, utilizzo unico o N volte per cliente, pagina `/p/` e QR della promo, più promozioni per
campagna, «porta un amico» (affiliazione), campagne create dal merchant, dati per cliente, risposta pubblica ai
commenti.

## Grilling

### Fatti verificati prima del giro 1 (2026-11-12)

- `detect_trigger` riconosce `CARTA` solo se il messaggio normalizzato è **esattamente** la parola chiave
  (`normalize_text`: NFKD senza accenti, `casefold`, punteggiatura ed emoji → spazi, spazi compattati; quindi
  `black-friday` diventa `black friday`).
- Il cashback non ha un registro: esiste solo il saldo `Card.cashback_cents` (il registro `PointTransaction` è dei soli
  tree points).
- `ProcessedWebhookEvent.outcome` è un enum Postgres (`WebhookOutcome`): un valore nuovo richiede `ALTER TYPE`.
- Archivio `feature/campagne` (`621a278`): la risposta privata accetta **solo testo** (`accountId` + `message`, mai
  bottoni o card); endpoint, `PUT /v1/webhooks/settings`, `isOwner`, `comment.received` sull'account gratuito e
  testo della risposta a una storia sono **da spec / da verificare**, mai provati dal vivo.

### Giro 1 (2026-11-12)

| # | Domanda | Raccomandazione | Risposta del founder |
|---|---|---|---|
| D1 | Come si riconosce la parola chiave | Parola intera ovunque per le campagne; `CARTA` esatta | Una sola parola (al limite `black-friday`), maiuscole indifferenti. Nei commenti «basta che sia contenuta», poi **superato da D11**: parola esatta anche nei commenti |
| D2 | A. Campagna finita / non iniziata / archiviata | DM «terminata / inizia il…», commenti nessuna risposta, archiviata ignorata | **Archiviata: nessuna risposta** (così il nome si può riusare). Finita / non iniziata: vedi giro 2 |
| D3 | B. Importo facoltativo | Sì | **Sì** (es. promo a percentuale: il merchant aggiunge il cashback a mano e la campagna conta l'utilizzo) |
| D4 | C. Unicità della parola chiave | Unica tra non archiviate e non finite, diversa da `CARTA` | **Unica tra tutte le non archiviate** (finite comprese: prima si archivia la vecchia, poi si riusa la parola) |
| D5 | D. Modifiche | Tutto modificabile sempre | **Confermato** (controlla il founder; serve anche a correggere errori) |
| D6 | E. Limiti dei campi | Nome 3-40, parola 3-30, testo 1-700, importo 0-50 €, date coerenti | **Vanno bene per ora**; da restringere se un giorno le promo non le crea più il founder |
| D7 | F. Cosa contano le richieste | Messaggi, anche con invio fallito, dedup sugli eventi ripetuti | **Confermato**, riusando i meccanismi che ci sono già |
| D8 | G. Conferma / annulla di «Applica» | Conferma sì, annulla no | **Finestra di conferma sì/no**; solo dopo «sì» cashback + utilizzo. Contatori delle richieste da commento e da DM con la parola chiave giusta (per confrontarli con gli utilizzi in negozio) |
| D9 | Contatore «cashback erogato» | Sì | **No**: importo × utilizzi lo calcola il founder |
| D10 | H. Quota Zernio | Contatore + vista in `/admin` | **Blocco solo manuale del founder**: limite facoltativo, vuoto di default, impostato se il merchant lo chiede (dettagli nel giro 2) |
| D11 | I. Commenti dell'account, risposte, più parole | Ignorati / valgono / prima parola / `CARTA` ignorata | **Parola esatta anche nei commenti** (emoji escluse), niente ricerca nel testo. **`CARTA` vale anche nei commenti** (come, nel giro 2) |
| D12 | Testo del DM | Promo + validità + invito a `CARTA` | Proposta del founder: «Valida dal … al …» (o «Valida il …», o niente se le date non ci sono) + «Per utilizzare questa offerta devi avere la nostra carta fedeltà. Se non l'hai ricevuta o non la ritrovi nella chat scrivi 'CARTA'» + testo della promo. Date facoltative (giro 2) |
| D13 | Negozio in attesa / in pausa | Campagne solo con negozio attivo | «Se archivio o metto in pausa la campagna non parte»: da chiarire nel giro 2 |
| D14 | Esiti nella tabella di dedup | Riusare i valori esistenti | Non chiara: rispiegata nel giro 2 |
| D15 | «Applica» dopo l'ultimo giorno | Niente bottone | **Il bottone resta**: se il merchant applica una campagna scaduta è una sua scelta |
| D16 | Collaudo anticipato | Ticket 01 = collaudo su Instagram vero | **Collaudo alla fine della feature**: i problemi si ricostruiscono dopo. Rischio accettato (codice dei commenti scritto prima di sapere se `comment.received` arriva) |
| D17 | Fuori scope | Roadmap / fuori-scope come proposto | **Dove è più comodo**, purché non si implementino ora |

Quattro temi (risposte del founder):
- **Dati non aggiornati**: lo scanner mostra le campagne attive, qualunque esse siano; la scadenza la guarda il merchant
  nel DM, l'archiviazione la fa il founder su richiesta.
- **Contesa**: ogni «Applica» chiede conferma; due conferme sulla stessa carta = due utilizzi.
- **Fallimento a metà**: ci si fida di Zernio; «al più tre tentativi» su errori vari (da conciliare con la regola di
  oggi «nessun nuovo tentativo», giro 2). Nel pilota si accetta il rischio.
- **Volumi e privacy**: confermati (pochi dati, nessun dato personale nuovo); si sistema strada facendo.

### Giro 2 (2026-11-12)

Fatto aggiunto: la risposta privata accetta solo testo (archivio `621a278`, `build_private_reply_body`).

| # | Domanda | Raccomandazione | Risposta del founder |
|---|---|---|---|
| R1 | A cosa servono le date | Regolano solo le risposte su Instagram; scanner mostra tutte le non archiviate; entrambe o nessuna | Le date serviranno se il progetto va avanti; per il pilota potrebbe anche scriverle a mano nel testo della promo, oppure tenerle come proposto: **scelta aperta, giro 3** |
| R2 | Pausa di una campagna | Solo «Archivia» + «Ripristina» (che ricontrolla l'unicità della parola) | **D'accordo** |
| R3 | Negozio in pausa / in attesa | Parole chiave delle campagne senza risposta | **Mettere in pausa il negozio archivia in automatico tutte le sue campagne non archiviate** |
| R4 | `CARTA` in un commento | (a) risposta privata «scrivici CARTA qui in chat», poi il flusso DM di oggi | **(a)** |
| R5 | Limite manuale | Limite facoltativo sulle richieste (DM + commenti); raggiunto → la parola tace, lo scanner continua; risposte private nel contatore quota | **Sì**, ma oltre la soglia il DM è: «Le offerte disponibili sono terminate. Per essere informato più velocemente la prossima volta attiva la campanella delle notifiche al profilo!!» |
| R6 | Etichette degli esiti | Riusare quelle esistenti | **Nessun salvataggio nuovo dell'esito di ogni invio**: bastano log chiari (stdout → log di runtime di DigitalOcean, terminale / `collaudo.log` in locale) |
| R7 | Tre tentativi sugli invii | Regola di oggi: nessun nuovo tentativo | **Come oggi con `CARTA`** (nessun nuovo tentativo) |
| R8 | Ordine del testo del DM | Promo in cima, poi validità e invito a `CARTA` | **Ok** |
| R9 | Formato della parola chiave | Una parola (lettere, cifre, trattini), corrispondenza esatta dopo la normalizzazione, DM e commenti | **Esatto** |
| R10 | Negozi veri in produzione | — | **Solo i profili del founder**: se il `PUT` dei webhook non funziona si ricollega lui |

### Giro 3 (2026-11-12)

| # | Domanda | Raccomandazione | Risposta del founder |
|---|---|---|---|
| S1 | Date nel pilota | (a) Senza date: la validità la scrive il founder nel testo; date in roadmap | **(a)** |
| S2 | Negozio in attesa | Campagne creabili ma senza risposta finché non è avviato; in pausa idem; riattivare non ripristina | **Ok** (il founder crea le campagne dopo aver avviato il negozio) |

Assunzioni sui quattro temi (risposta finale): **dati non aggiornati** — «Applica» **non** ricontrolla che la campagna sia
ancora attiva: se il bottone c'è e il merchant conferma, funziona (anche se nel frattempo è stata archiviata); restano
solo i controlli di sempre (campagna del negozio, negozio attivo). **Contesa**, **fallimento a metà** e **volumi**:
confermati come nel riepilogo.

## Decisioni (riepilogo confermato il 2026-11-12, diventano le `Dn` della spec)

1. **Campagna** = negozio, nome, parola chiave, testo della promo, importo di cashback facoltativo, limite di
   richieste facoltativo, archiviata sì/no, contatori (richieste da DM, richieste da commento, utilizzi). **Nessuna
   data** nel pilota. Una sola tabella nuova con la sua migrazione; nessuna modifica alle tabelle o agli enum esistenti.
2. **Gestione solo del founder da `/admin`**: crea, modifica tutto in ogni momento, archivia, ripristina. Mettere in
   pausa un negozio archivia in automatico tutte le sue campagne non archiviate; riattivarlo non le ripristina.
3. **Attiva** = non archiviata e negozio attivo (approvato e non in pausa). Negozio in attesa: le campagne si possono
   creare ma non rispondono.
4. **Parola chiave**: una sola parola (lettere e cifre, trattini ammessi, es. `black-friday`), diversa da `CARTA`
   (`INSTAGRAM_CARD_KEYWORD`), unica tra le campagne **non archiviate** del negozio (controllo anche al ripristino).
5. **Riconoscimento**: il testo normalizzato (maiuscole, accenti, punteggiatura, emoji ignorati; trattino = spazio)
   deve essere **esattamente** la parola chiave, in DM (risposte alle storie comprese) e nei commenti (anche risposte
   ad altri commenti). Commenti dell'account del negozio ignorati.
6. **Risposta = un solo DM di testo** (risposta privata per i commenti, mai pubblica):
   `<testo della promo>` + riga vuota + «Per utilizzare questa offerta devi avere la nostra carta fedeltà. Se non l'hai
   ricevuta o non la ritrovi nella chat scrivi CARTA.» (parola = `INSTAGRAM_CARD_KEYWORD`).
7. **Limite raggiunto** (richieste da DM + da commento ≥ limite): la risposta diventa «Le offerte disponibili sono
   terminate. Per essere informato più velocemente la prossima volta attiva la campanella delle notifiche al
   profilo!!».
8. **Campagna archiviata o negozio non attivo**: nessuna risposta, né in DM né nei commenti.
9. **`CARTA` in un commento**: risposta privata «Per ricevere la tua carta scrivici CARTA qui in chat»; il DM `CARTA`
   resta com'è oggi (card solo a chi segue).
10. **Contatori e invii**: le richieste contano i messaggi (anche con invio fallito; un evento ripetuto da Zernio una
    volta sola, con la dedup di oggi); ogni risposta privata entra nel contatore della quota Zernio; **nessun nuovo
    tentativo** sugli invii, come oggi; esiti con le etichette esistenti e nei log (senza testo né id del cliente).
11. **Scanner**: dopo lo scan della carta mostra tutte le campagne non archiviate con «Applica <nome> (+X €)» o
    «Applica <nome>» senza importo; conferma sì/no; al «sì», nella stessa transazione, cashback sulla carta +
    1 utilizzo. Bloccato con negozio in attesa o in pausa (come ogni aggiunta di cashback). Tree points, pool e pagina
    carta del cliente non cambiano.
12. **Limiti dei campi** (per ora; da restringere se le promo non le crea più il founder): nome 3-40 caratteri, parola
    chiave 3-30, testo 1-850 (DM completo < 1000, verificato nel core), importo 0-50 € in centesimi, limite intero
    positivo o vuoto.
13. **Collaudo su Instagram vero alla fine della feature** (non anticipato, rischio accettato); prima, con l'ok del
    founder, pulizia delle tabelle della vecchia v0.4.0 su Neon `development`. Se i commenti non funzionano con
    l'account Zernio gratuito: piano B, solo DM e storie. Se `PUT /v1/webhooks/settings` non funziona, il founder
    ricollega i suoi profili (unici collegati in produzione).

Assunzioni sui quattro temi:
- **Dati non aggiornati**: lo scanner mostra le campagne lette allo scan; «Applica» confermato funziona anche se la
  campagna è stata archiviata nel frattempo, con l'importo letto al momento della conferma.
- **Contesa**: due conferme = due utilizzi; contatori e cashback con `UPDATE` atomico (`n = n + 1`), non
  leggi-modifica-scrivi.
- **Fallimento a metà**: nessun nuovo tentativo sugli invii (il cliente riscrive; la risposta a un commento può
  andare persa); «Applica» è una sola transazione DB senza servizi esterni.
- **Volumi**: poche centinaia di righe l'anno; il limite vero è la quota Zernio, gestito con il limite manuale.
- **Privacy**: nessun dato personale nuovo (né testo dei commenti né id o username di chi scrive).

Fuori scope: rimandate in [roadmap](../../planner/roadmap.md) (date di inizio e fine, campagne create dal merchant,
promo salvata nella carta / limite per cliente, «porta un amico», dati per cliente, card inviata da un commento);
scartate in [fuori-scope.md](../../fuori-scope.md) (pagina `/p/` e QR della promo, più promozioni per campagna,
risposta pubblica ai commenti).
