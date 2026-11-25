# v0.4.1 — Campagne pilota: promo via DM e commenti Instagram

> **Stato: SPEC APPROVATA il 2026-11-12, gate 2 approvato il 2026-11-12** (modello, contract e ticket 01-06:
> [domain-model.md](domain-model.md), [contracts.md](contracts.md); scostamenti accettati, il 3 ammette campagne
> con il negozio in pausa; 04 bloccante con piano B; strumenti di collaudo approvati). Al gate 1: D1-D7, D9,
> D11-D13, D15 confermati; D8 sostituito dalla regola di oggi; D10 cambiato: le campagne si possono anche eliminare;
> D14 e D16 tolti: nessun controllo sui trattini e nessun filtro dei commenti del negozio, che cambia la decisione 5.
> Grilling chiuso il 2026-11-12 (verbale in
> fondo). Branch `feature/campagne-pilota` da `develop` (creato il 2026-11-12, contiene il processo a skill).
>
> **Numero di versione**: patch per scelta del founder anche se la versione aggiunge una tabella e una migrazione (la
> regola della skill vorrebbe una minore): `v0.4.0` resta all'archivio `feature/campagne` e non si riusa. Il primo
> ticket porta `pyproject.toml` e `EXPECTED_VERSION` di `scripts/smoke_test_prod.py` a `0.4.1`.

## Obiettivo

Il founder crea per un negozio una **campagna**: una parola chiave e il testo di una promo, con un importo di cashback
facoltativo. Il negozio la lancia su Instagram («commenta o scrivici NATALE»). Chi scrive la parola chiave in DM,
la usa per rispondere a una storia o la commenta sotto un post riceve **un DM di testo con la promo: quel DM è il
coupon**. In negozio il merchant scansiona la carta del cliente, preme **«Applica»** sulla campagna e conferma: il
cashback entra nella carta e l'utilizzo viene contato.

Il motivo di business: partire con i primi pilota con la funzione più spettacolare e più leggera possibile. Le
campagne rendono il profilo Instagram del negozio più vivo (seguire, guardare i post, commentare) e danno al founder
due numeri da raccontare al merchant: quante persone hanno chiesto la promo e quante l'hanno usata in negozio. La
versione precedente (v0.4.0, adesioni, pagina promozione, secondo QR, limiti per cliente) è archiviata su
`feature/campagne` perché troppo pesante per un pilota; da lì si copia solo il codice che serve (vedi «Riuso
dall'archivio» nel verbale).

## Glossario (termini nuovi)

| Termine | Significato |
|---|---|
| **Campagna** | Promo di un negozio: nome, parola chiave, testo della promo, importo di cashback facoltativo, limite di richieste facoltativo, archiviata sì/no, contatori. La gestisce solo il founder. Nessuna data nel pilota. (Sostituisce la riga provvisoria del glossario.) |
| **Testo della promo** | Testo libero scritto dal founder (validità compresa, se serve); è la prima parte del DM di risposta. |
| **Campagna archiviata** | Spenta: la sua parola chiave è una parola qualsiasi e la campagna non compare nello scanner. Si ripristina dalla dashboard. |
| **Campagna attiva** | Non archiviata, di un negozio attivo (stato del servizio «attivo»). |
| **Richiesta** | Un DM (risposte alle storie comprese) o un commento il cui testo, normalizzato, è esattamente la parola chiave di una campagna attiva. Si conta per canale: richieste da DM, richieste da commento. |
| **Limite di richieste** | Numero facoltativo, impostato dal founder: oltre il limite la risposta diventa il testo «offerte terminate». |
| **Risposta privata** | Il DM con cui Instagram permette di rispondere a un commento (uno per commento, solo testo); per il cliente è un DM come gli altri. |
| **Utilizzo** | Un «Applica» confermato nello scanner: accredita l'importo della campagna sul cashback della carta e incrementa il contatore degli utilizzi. |

## Decisioni del grilling (2026-11-12)

1. **Campagna** = negozio, nome, parola chiave, testo della promo, importo di cashback facoltativo, limite di
   richieste facoltativo, archiviata sì/no, contatori (richieste da DM, richieste da commento, utilizzi). **Nessuna
   data** nel pilota (la validità la scrive il founder nel testo). Una sola tabella nuova con la sua migrazione;
   nessuna modifica alle tabelle o agli enum esistenti.
2. **Gestione solo del founder da `/admin`**: crea, modifica tutto in ogni momento, archivia, ripristina. Mettere in
   pausa un negozio archivia in automatico tutte le sue campagne non archiviate; riattivarlo non le ripristina.
3. **Attiva** = non archiviata e negozio attivo (approvato e non in pausa). Negozio in attesa: le campagne si possono
   creare ma non rispondono.
4. **Parola chiave**: una sola parola, senza spazi (trattini ammessi, es. `black-friday`; nessun altro controllo sui
   caratteri, gate 1), diversa da `CARTA` (`INSTAGRAM_CARD_KEYWORD`), unica tra le campagne **non archiviate** del
   negozio (controllo anche al ripristino).
5. **Riconoscimento**: il testo normalizzato (maiuscole, accenti, punteggiatura, emoji ignorati; trattino = spazio)
   deve essere **esattamente** la parola chiave, in DM (risposte alle storie comprese) e nei commenti (anche risposte
   ad altri commenti). ~~Commenti dell'account del negozio ignorati~~ — **cambiato al gate 1**: i commenti del negozio
   valgono come gli altri (il negozio non commenta con le parole chiave, al più una prova).
6. **Risposta = un solo DM di testo** (risposta privata per i commenti, mai pubblica): testo della promo + riga vuota +
   «Per utilizzare questa offerta devi avere la nostra carta fedeltà. Se non l'hai ricevuta o non la ritrovi nella
   chat scrivi CARTA.» (parola = `INSTAGRAM_CARD_KEYWORD`).
7. **Limite raggiunto**: la risposta diventa «Le offerte disponibili sono terminate. Per essere informato più
   velocemente la prossima volta attiva la campanella delle notifiche al profilo!!».
8. **Campagna archiviata o negozio non attivo**: nessuna risposta, né in DM né nei commenti.
9. **`CARTA` in un commento**: risposta privata «Per ricevere la tua carta scrivici CARTA qui in chat»; il DM `CARTA`
   resta com'è oggi (card solo a chi segue).
10. **Contatori e invii**: le richieste contano i messaggi (anche con invio fallito; un evento ripetuto da Zernio una
    volta sola); ogni risposta privata entra nel contatore della quota Zernio; **nessun nuovo tentativo** sugli
    invii; esiti con le etichette esistenti e nei log (senza testo né id del cliente).
11. **Scanner**: dopo lo scan della carta mostra tutte le campagne non archiviate con «Applica <nome> (+X €)» o
    «Applica <nome>»; conferma sì/no; al «sì», nella stessa transazione, cashback sulla carta + 1 utilizzo. Bloccato
    con negozio in attesa o in pausa. Tree points, pool e pagina carta del cliente non cambiano. «Applica» confermato
    funziona anche se nel frattempo la campagna è stata archiviata.
12. **Limiti dei campi** (per ora): nome 3-40 caratteri, parola chiave 3-30, testo della promo 1-850, importo 0-50 €,
    limite intero positivo o vuoto.
13. **Collaudo su Instagram vero alla fine della feature** (non anticipato: rischio accettato dal founder); prima,
    con il suo ok, pulizia delle tabelle della vecchia v0.4.0 su Neon `development`. Se i commenti non funzionano con
    l'account Zernio gratuito: piano B, solo DM e storie.

## Default scelti dall'agente (da confermare al gate)

- **D1** — **Importo «vuoto» = 0 centesimi** (colonna obbligatoria con default 0): lo scanner mostra «Applica <nome>»
  senza «(+X €)» e l'utilizzo accredita 0.
- **D2** — **Ordine nel webhook dei DM**: dedup → account → solo messaggi in arrivo → standby (nessuna risposta, nessun
  contatore, come oggi) → `CARTA` o voce di menu (flusso di oggi, invariato) → parola chiave di campagna → ignorato.
- **D3** — **Le richieste oltre il limite si contano** (il contatore mostra la domanda reale). Decide il valore dopo
  l'incremento atomico: richieste da DM + da commento ≤ limite → promo; oltre → testo «offerte terminate».
- **D4** — **Finestra di 24 ore** anche per i DM di campagna, come per `CARTA`: fuori finestra nessun invio
  (`OUT_OF_WINDOW`), la richiesta è contata. Per i commenti nessun controllo nostro dei 7 giorni: lo fa Meta
  (rifiuto → `SEND_FAILED`).
- **D5** — **Una risposta privata riuscita vale come un invio in DM**: +1 nel contatore della quota, avviso al 75% e
  passaggio `AWAITING_TEST_DM` → `ACTIVE` del collegamento Instagram (prova che il webhook funziona). Un timeout conta
  nella quota ma non attiva, come oggi.
- **D6** — **Esiti** (etichette esistenti): promo, «offerte terminate» e invito `CARTA` inviati → `SENT`; timeout →
  `SEND_UNCERTAIN`; altri errori → `SEND_FAILED`; fuori finestra → `OUT_OF_WINDOW`; tutto il resto (archiviata, negozio
  non attivo, nessuna parola) → `IGNORED`. Il log aggiunge id della campagna e canale (`dm` /
  `commento`), mai testo, IGSID o id del commento.
- **D7** — **`CARTA` in un commento riceve l'invito in ogni stato del negozio** (in attesa compreso): il DM che segue
  passa dal flusso di oggi (carta di prova se il negozio è in attesa). Non tocca i contatori delle campagne.
- ~~**D8** — «Applica» bloccato anche con importo 0~~ — **sostituito al gate 1**: «Applica» usa lo stesso controllo
  di oggi dell'aggiunta di cashback (`check_balance_change`: 403 per un importo > 0 con negozio in attesa o in pausa).
  Un negozio in pausa non ha campagne non archiviate (decisione 2), quindi il caso non si pone; con importo 0 conta
  solo l'utilizzo.
- **D9** — **Nessuno script per i negozi già collegati**: i collegamenti nuovi sottoscrivono `message.received` e
  `comment.received`; il founder (unico collegato in produzione) fa «Scollega» e ricollega. Niente `PUT` dei webhook.
- **D10** — **Cambiato al gate 1**: oltre ad archivia / ripristina, il founder può **eliminare** una campagna (riga
  cancellata dal DB, sparisce da `/admin` e dallo scanner, contatori compresi), dopo una conferma sì/no. Eliminare un
  negozio elimina le sue campagne (cascata).
- **D11** — **Lista in `/admin`** per negozio: prima le non archiviate, poi le archiviate, dalla più recente; per
  ciascuna nome, parola chiave, importo, limite, stato e i tre contatori.
- **D12** — **Scanner**: campagne non archiviate dalla più recente; senza campagne la gestione della carta è identica
  a oggi. Dopo «Applica» la pagina mostra il cashback aggiornato e l'importo accreditato.
- **D13** — **La pausa archivia da qualunque strada**: oltre a «Metti in pausa» della dashboard, anche
  `PUT /api/merchant/{id}` con `X-Admin-Key` (che oggi può impostare `is_paused`) archivia le campagne quando il negozio
  passa ad «in pausa». La regola sta nel service, non nella route.
- ~~**D14** — Trattini solo tra lettere o cifre~~ — **tolto al gate 1**: nessun controllo sui caratteri oltre a «senza
  spazi», lunghezza e parola normalizzata non vuota.
- **D15** — **Parola condivisa con una campagna archiviata**: l'unicità vale solo tra le non archiviate, quindi
  `NATALE` può esistere sia archiviata sia non archiviata. Nel webhook una campagna archiviata non corrisponde mai:
  vince sempre quella non archiviata.
- ~~**D16** — Commenti dell'account del negozio scartati per primi~~ — **tolto al gate 1**: nessun filtro, i commenti
  del negozio valgono come gli altri (cambia la decisione 5).
- **Nota su D3** (gate 1): il contatore delle richieste segue lo schema dei contatori di oggi (`UPDATE` atomico come
  `ZernioSendCounter` e `MerchantPool`).

## Aree toccate

I file di `.agents/specs/` non esistono ancora: li crea il primo ticket che tocca l'area, partendo da AGENTS.md.

| Area (file di `.agents/specs/`) | Oggi | Con v0.4.1 | Scheda di decisione |
|---|---|---|---|
| `campagne.md` (nuovo) | Nessuna campagna (la v0.4.0 è archiviata) | Campagne pilota: il coupon è il DM, una tabella, gestione solo del founder, nessuna data | 0001 — Campagne pilota: il coupon è il DM |
| `carta-instagram.md` | Trigger solo `CARTA` / voce di menu in DM; commenti e storie → DM fuori scope; webhook sottoscrive solo `message.received` | In più le parole chiave delle campagne (DM e risposte alle storie, corrispondenza esatta); `comment.received` → risposta privata di solo testo (campagna o invito a scrivere `CARTA`); le risposte private contano nella quota | 0002 — Commenti Instagram: risposta privata di solo testo |
| `merchant-auth-stato.md` / `admin.md` | «Metti in pausa» (dashboard) e `PUT /api/merchant/{id}` cambiano solo `is_paused` | Il passaggio ad «in pausa», da entrambe le strade, archivia anche tutte le campagne non archiviate del negozio; «Riattiva» non le ripristina | 0003 — La pausa del negozio archivia le campagne |
| `carta-e-scanner.md` | La gestione della carta aggiunge/toglie tree points e cashback | In più «Applica» per ogni campagna non archiviata, con conferma; stesso blocco di oggi per le aggiunte di cashback | 0004 — «Applica» nello scanner |
| `dati-e-segreti.md` | Niente Alembic, schema da `create_all()`; modifiche allo schema con migrazione preparata prima (regola del 2026-10-29) | Prima migrazione con **script SQL a mano** `migrations/0001_campagne.sql` (una sola `CREATE TABLE`), provato su Neon `development` prima della produzione | 0005 — Migrazioni con script SQL a mano |

## Casi d'uso e criteri di accettazione

Gli id dei criteri (`AC-NN`) sono il riferimento per test, ticket e tabella di tracciabilità.

### UC1 — Il founder gestisce le campagne di un negozio (`/admin`)

Attore: founder con sessione admin (o `X-Admin-Key`). Flusso: dalla dashboard sceglie un negozio, vede le sue
campagne, ne crea una, la modifica, la archivia o la ripristina.

- **AC-01** La lista delle campagne di un negozio mostra, per ciascuna, nome, parola chiave, importo (o «nessun
  importo»), limite (o «nessun limite»), stato (attiva / archiviata / ferma perché il negozio non è attivo) e i tre
  contatori, nell'ordine di D11.
- **AC-02** La creazione salva una campagna non archiviata con contatori a zero. L'importo arriva in euro e si salva
  in centesimi; vuoto → 0 (D1).
- **AC-03** Ogni limite della decisione 12 e il formato della parola chiave (decisione 4) sono verificati nel core: un
  valore non valido → 400 con un messaggio leggibile, niente scritto. Esempi: nome di 2 caratteri, `NATALE 2026`
  (con uno spazio), `!!` (vuota dopo la normalizzazione), testo di 851 caratteri, importo 50,01 €, limite 0.
- **AC-04** Una parola chiave che, normalizzata, è uguale a `INSTAGRAM_CARD_KEYWORD` o a quella di un'altra campagna
  **non archiviata** dello stesso negozio → 409, niente scritto. Vale alla creazione, alla modifica e al ripristino.
  Due negozi diversi possono usare la stessa parola; una campagna archiviata non blocca nessuna parola.
- **AC-05** La modifica può cambiare ogni campo; i contatori non cambiano. Abbassare il limite sotto le richieste già
  contate è ammesso: da lì in poi la risposta è «offerte terminate».
- **AC-06** «Archivia» e «Ripristina» cambiano solo lo stato; ripetere l'azione non cambia nulla. Il ripristino
  rifà il controllo di AC-04. «Elimina», dopo la conferma, cancella la riga: la campagna sparisce da `/admin` e dallo
  scanner e la sua parola torna libera (D10); un secondo «Elimina» → 404.
- **AC-07** Le API e la pagina seguono le regole di oggi della dashboard admin: sessione a cookie o `X-Admin-Key`,
  controllo `Origin` sui POST/PUT con cookie, `Cache-Control: no-store`, `noindex`, DOM costruito solo con
  `textContent`; negozio o campagna inesistenti, o campagna di un altro negozio → 404.

### UC2 — Il founder mette in pausa un negozio

- **AC-08** Quando un negozio passa ad «in pausa» — «Metti in pausa» della dashboard o `PUT /api/merchant/{id}` con
  `is_paused` (D13) — tutte le sue campagne non archiviate si archiviano nella stessa transazione. «Riattiva» e «Avvia»
  non ripristinano nessuna campagna. Una pausa su un negozio già in pausa non cambia nulla; dalla dashboard, su un
  negozio in attesa resta il 409 di oggi e nessuna campagna viene archiviata.

### UC3 — Il cliente scrive la parola chiave in DM o rispondendo a una storia

Attore: cliente su Instagram. Flusso: scrive `NATALE` in DM (o risponde a una storia con `NATALE`); riceve il DM con
la promo.

- **AC-09** Riconoscimento: il testo normalizzato deve essere **esattamente** la parola chiave normalizzata. Con la
  campagna `black-friday` scattano «Black-Friday!», «black friday», «BLACK-FRIDAY 🎄»; non scattano «blackfriday» e
  «black friday per me». `CARTA` e la voce di menu seguono il flusso di oggi, invariato (D2). La risposta a una storia
  segue lo stesso riconoscimento di un DM. Si cerca solo tra le campagne non archiviate del negozio: con `NATALE` sia
  archiviata sia non archiviata risponde la non archiviata e contano solo i suoi contatori (D15).
- **AC-10** Campagna attiva, richieste sotto il limite (o nessun limite): richieste da DM +1 e **un** DM di testo =
  testo della promo + riga vuota + riga fissa della decisione 6. Uguale per chi segue e per chi non segue
  (`isFollower` ignorato). Nessuna carta creata o modificata, nessun tree point, nessun cashback.
- **AC-11** Limite: con limite N e richieste da DM + da commento già a N, la richiesta successiva è contata (D3) e
  riceve il testo della decisione 7. L'incremento e il confronto sono **atomici**: due richieste contemporanee
  sull'ultimo posto non ricevono entrambe la promo.
- **AC-12** Parola chiave di una campagna archiviata, o di un negozio in attesa o in pausa → nessun invio, nessun
  contatore, esito `IGNORED`.
- **AC-13** Valgono le regole di oggi del webhook: firma, dedup per evento (un evento ripetuto da Zernio non manda e
  non conta una seconda volta), standby (nessun invio, nessun contatore), finestra di 24 ore (D4), quota +1 per invio
  riuscito o incerto, nessun nuovo tentativo, risposta 200 per ogni esito, nei log nessun testo, IGSID, chiave o token.

### UC4 — Il cliente commenta un post con la parola chiave

- **AC-14** L'evento `comment.received` arriva allo stesso webhook del negozio, con la stessa firma e la stessa dedup
  dei DM. Il testo del commento si riconosce come un DM (AC-09: corrispondenza esatta). Una risposta a un altro
  commento vale come un commento.
- **AC-15** Parola chiave di una campagna attiva → richieste da commento +1 e **una** risposta privata con lo stesso
  testo di AC-10 (o di AC-11 oltre il limite). Mai una risposta pubblica, nessuna carta.
- **AC-16** Commento uguale a `CARTA` → una risposta privata «Per ricevere la tua carta scrivici CARTA qui in chat», in
  ogni stato del negozio (D7). Nessuna carta creata, nessun contatore di campagna.
- **AC-17** Commenti senza parola chiave esatta, parole di campagne archiviate o di un negozio non attivo → nessun
  invio, nessun contatore, `IGNORED`. I commenti dell'account del negozio seguono le stesse regole degli altri
  (decisione 5 cambiata al gate 1).
- **AC-18** Errori della risposta privata (già usata, commento troppo vecchio, rifiuto di Meta, 4xx/5xx) →
  `SEND_FAILED`; timeout o esito sconosciuto → `SEND_UNCERTAIN` (contato nella quota). Nessun nuovo tentativo,
  risposta 200 a Zernio, richiesta comunque contata.
- **AC-19** Una risposta privata riuscita conta nella quota come un DM (D5).
- **AC-20** Il collegamento Instagram (onboarding) registra il webhook con gli eventi `message.received` e
  `comment.received`; «Scollega» e un nuovo collegamento bastano ad aggiornare un negozio già collegato (D9).

### UC5 — Il merchant applica una campagna in negozio

Attore: merchant con la PWA. Flusso: scansiona il QR della carta, vede le campagne nella gestione della carta, preme
«Applica», conferma.

- **AC-21** La gestione della carta mostra le campagne non archiviate del negozio (D12) con «Applica <nome> (+X €)»,
  o «Applica <nome>» con importo 0. Senza campagne la pagina è identica a oggi.
- **AC-22** «Applica» apre una conferma sì/no; con «no» non parte nessuna richiesta.
- **AC-23** Con «sì»: cashback della carta + importo **attuale** della campagna e utilizzi +1, in **una** transazione,
  con incrementi atomici (due «Applica» confermati = due utilizzi e due accrediti, nessun incremento perso). La
  risposta riporta il cashback aggiornato e l'importo accreditato. Importo 0 → solo l'utilizzo.
  — **accettato come rischio (F-01)**: la parte sugli incrementi atomici in caso di richieste simultanee non è garantita né testata.
- **AC-24** Negozio in attesa o in pausa e importo > 0 → 403 prima di scrivere, con il controllo di oggi
  dell'aggiunta di cashback (D8 sostituito); nello scanner i bottoni «Applica» con importo sono disattivati con il
  banner di oggi. (Un negozio in pausa non ha campagne non archiviate: AC-08.)
- **AC-25** Carta o campagna inesistenti o di un altro negozio → 404, niente scritto. Una campagna archiviata dopo il
  caricamento della pagina si applica comunque (decisione 11).
- **AC-26** «Applica» non tocca tree points, pool del mese, conversione né registro `PointTransaction`; la pagina carta
  del cliente `/c/<token>` resta identica.

### UC6 — Testi dei messaggi

- **AC-27** Il core costruisce i tre testi (promo, «offerte terminate», invito `CARTA` dal commento) e verifica che
  ogni DM resti sotto i 1000 caratteri: con il testo della promo al massimo (850) il DM completo ci sta. La parola
  della riga fissa è `INSTAGRAM_CARD_KEYWORD`, passata come argomento.

### UC7 — Migrazione e rilascio

- **AC-28** `migrations/0001_campagne.sql` contiene **una sola** `CREATE TABLE IF NOT EXISTS` (più i suoi indici):
  nessun `ALTER` su tabelle o tipi esistenti. Un test verifica che ogni colonna del modello nuovo compaia nello script.
- **AC-29** `pyproject.toml` ed `EXPECTED_VERSION` di `scripts/smoke_test_prod.py` valgono `0.4.1`.
- **AC-30** `deploy.md` descrive l'applicazione dello script (branch di backup di `production`, prova su
  `development`, poi produzione); `collaudo.md` ha i passi delle campagne (DM, risposta a una storia, commento,
  `CARTA` da commento, limite, archiviazione, pausa, «Applica»).

## Invarianti

- **I1** Una campagna appartiene a un solo negozio: webhook, dashboard e scanner non leggono né scrivono mai campagne
  di un altro negozio.
- **I2** Tra le campagne non archiviate di un negozio le parole chiave normalizzate sono tutte diverse tra loro e
  diverse da `INSTAGRAM_CARD_KEYWORD` normalizzata.
- **I3** Al massimo un invio per evento del webhook (DM o commento).
- **I4** Il cashback di una carta cresce per una campagna solo con un utilizzo, mai con una richiesta.
- **I5** I contatori di una campagna esistente non diminuiscono mai (l'eliminazione toglie la riga intera).
- **I6** Le campagne non salvano dati dei clienti (né testo, né IGSID, né username, né id del commento) e i log non
  contengono testo dei messaggi, IGSID, chiavi o token.
- **I7** Il core resta puro: le funzioni sulle campagne ricevono la parola di `CARTA` e il tempo come argomenti e non
  leggono le settings.
- **I8** Le tabelle e gli enum esistenti non cambiano.

## Errori di dominio (riuso di `app/core/errors.py`)

| Caso | Errore | HTTP |
|---|---|---|
| Campo non valido (decisioni 4 e 12) | `InvalidInputError` | 400 |
| Parola chiave uguale a `CARTA` o a un'altra campagna non archiviata (creazione, modifica, ripristino) | `ConflictError` | 409 |
| Negozio, campagna o carta inesistenti o di un altro negozio | `NotFoundError` | 404 |
| «Applica» con importo > 0 e negozio in attesa o in pausa | `ForbiddenError` | 403 |
| Pausa di un negozio in attesa (regola di oggi) | `ConflictError` | 409 |

Nel webhook nessun errore diventa un HTTP diverso da 200/401/404: si traducono negli esiti di D6.

## Modello dati target

```
Campaign   id int PK, merchant_id FK merchant.id ON DELETE CASCADE (index),
           name str(40), keyword str(30) (forma salvata: da decidere nel contract), promo_text str(850),
           value_cents int NOT NULL default 0, request_limit int NULL,
           is_archived bool NOT NULL default false,
           dm_requests int default 0, comment_requests int default 0, uses int default 0,
           created_at datetime UTC

Merchant, Card, ProcessedWebhookEvent (enum WebhookOutcome compreso), ZernioSendCounter, PointTransaction,
MerchantPool, TreePlanting, AuthCredential   invariati
```

Dipendenze nuove: nessuna (senza date non serve `tzdata`).

## Assunzioni sui quattro temi

- **Dati non aggiornati**: lo scanner mostra le campagne lette allo scan; «Applica» confermato funziona anche se la
  campagna è stata archiviata nel frattempo e usa l'importo letto alla conferma. I contatori in `/admin` si
  aggiornano ricaricando la pagina.
- **Contesa**: due conferme = due utilizzi; contatori, limite e cashback con `UPDATE` atomici (`n = n + 1`), non
  leggi-modifica-scrivi (su SQLite `with_for_update` non fa nulla: i test devono passare dall'`UPDATE`).
- **Fallimento a metà**: la richiesta si conta prima dell'invio; l'invio non si ritenta (il cliente riscrive, la
  risposta a un commento può andare persa); «Applica» è una sola transazione DB senza servizi esterni.
- **Volumi**: poche centinaia di campagne l'anno, una query per evento (campagne non archiviate del negozio, indice su
  `merchant_id`); il limite vero è la quota Zernio, gestito con il limite manuale.

## Slice verticali (diventano i ticket dopo il gate 2)

| # | Slice | Dipende da |
|---|---|---|
| 01 | Versione 0.4.1, modello `Campaign`, `migrations/0001_campagne.sql` e suo test, core delle campagne (validazioni, normalizzazione e confronto della parola chiave, testi dei DM) — AC-03 (core), AC-27, AC-28, AC-29 | — |
| 02 | Dashboard admin: API e sezione «Campagne» (UC1); la pausa archivia le campagne (UC2) | 01 |
| 03 | Webhook: parola chiave di campagna in DM e risposte alle storie → DM di testo, contatori, limite (UC3) | 01 |
| 04 | Commenti: `comment.received` → risposta privata (campagna o invito `CARTA`), client Zernio dall'archivio, eventi del webhook all'onboarding (UC4) | 03 |
| 05 | Scanner: campagne nella gestione della carta e «Applica» con conferma (UC5) | 01 |
| 06 | Documentazione (`collaudo.md`, `deploy.md`, spec vive), pulizia di Neon `development`, prova dello script SQL, **collaudo su Instagram vero** del founder (AC-30) | tutti |

**Nessuna slice di collaudo anticipato**, per decisione del founder (decisione 13), anche se Zernio e Meta non sono
verificati su: `comment.received` con l'account gratuito, campi del payload del commento (`platformPostId`, autore),
risposta privata di solo testo a un non follower, testo della risposta a una storia,
risposta privata nella quota. Il codice dei commenti (04) si scrive dalla spec di Zernio e dalle note dell'archivio;
se il collaudo finale mostra un comportamento diverso, si apre una voce `/fix`. Piano B: si spegne il ramo dei commenti
e restano DM e storie; in più `WEBHOOK_EVENTS` torna a solo `message.received`, altrimenti, se l'account gratuito
rifiuta la sottoscrizione di `comment.received`, fallirebbe l'intero collegamento Instagram e con lui anche `CARTA`.

## Da decidere nel contract (gate 2)

- Forma salvata della parola chiave: come la scrive il founder più una colonna normalizzata (per l'unicità e il
  confronto) oppure solo la forma normalizzata.
- Incremento atomico con confronto del limite (AC-11): `UPDATE … RETURNING` o `UPDATE` condizionale, verificabile anche
  su SQLite.
- Campi del payload di `comment.received` (dalle note dell'archivio e dalla OpenAPI di Zernio); chiave di idempotenza
  della risposta privata.
- Dove vive `normalize_text` (oggi in `instagram_service`; l'archivio la sposta in `app/core`).
- Equivalenza tra script SQL e modello SQLModel: all'avvio `create_all()` crea `campaign` da solo, quindi script e
  modello devono coincidere anche su default lato DB (`Field(default=0)` è solo lato Python), `ON DELETE CASCADE`,
  lunghezze e `NOT NULL`; come lo verifica il test di AC-28 (oggi controlla solo i nomi delle colonne).
- Forma delle API admin (percorsi, corpi, risposte) e dell'endpoint «Applica» (percorso, corpo, risposta), e se la
  gestione della carta riceve le campagne dal template o da un'API.

## Piano di rollback

- **Codice**: redeploy del tag `v0.3.0` (procedura in `deploy.md`). La tabella `campaign` resta e la vecchia app la
  ignora (`create_all()` non la tocca).
- **Schema**: solo una `CREATE TABLE`; prima di applicarla in produzione si crea il branch Neon di backup. Tornare
  indietro sullo schema non serve; se proprio si vuole, `DROP TABLE campaign` (si perdono campagne e contatori).
- **Enum**: nessuno cambia (I8), nessun passo.
- **Per slice**:
  - 01-02: solo righe in `campaign`; nessun effetto fuori dal DB.
  - 04 (piano B senza rollback del codice): ramo dei commenti spento e `WEBHOOK_EVENTS` di nuovo solo
    `message.received`; il founder scollega e ricollega i suoi profili.
  - 03-04: DM e risposte private **già inviati restano nelle chat dei clienti** e non si possono ritirare. Con la
    vecchia app i coupon restano validi per il merchant, che accredita a mano con «+ cashback». Il webhook con
    `comment.received` sottoscritto non fa danni: la vecchia app ignora ogni evento che non è `message.received`
    (`parse_message_received` → `None` → `IGNORED`); per pulizia il founder può scollegare e ricollegare.
  - 05: i cashback accreditati con «Applica» **restano sulle carte** (credito promesso ai clienti, pagato dal
    merchant): non si tolgono nel rollback. Gli utilizzi restano nei contatori.

## Fuori scope

- **Rimandato** (in [roadmap](../../planner/roadmap.md)): date di inizio e fine, campagne create dal merchant (con
  limiti più stretti), promo salvata nella carta e limite per cliente, «porta un amico», dati per cliente, card
  inviata direttamente da un commento, script per aggiornare gli eventi dei webhook dei negozi già collegati.
- **Scartato** (in [fuori-scope.md](../../fuori-scope.md)): pagina `/p/` e QR della promo, più promozioni per
  campagna, risposta pubblica ai commenti, «comment automations» di Zernio.

---

# Verbale del grilling

## Richiesta iniziale

Copia del brief `.agents/planner/brief-campagne-pilota.md` (commit `90cf9ca`; file eliminato al gate 1),
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

Nel verbale le domande del giro 1 sono G1-G17 (nella conversazione erano D1-D17): le `Dn` della spec sono i default dell'agente.

| # | Domanda | Raccomandazione | Risposta del founder |
|---|---|---|---|
| G1 | Come si riconosce la parola chiave | Parola intera ovunque per le campagne; `CARTA` esatta | Una sola parola (al limite `black-friday`), maiuscole indifferenti. Nei commenti «basta che sia contenuta», poi **superato da G11**: parola esatta anche nei commenti |
| G2 | A. Campagna finita / non iniziata / archiviata | DM «terminata / inizia il…», commenti nessuna risposta, archiviata ignorata | **Archiviata: nessuna risposta** (così il nome si può riusare). Finita / non iniziata: vedi giro 2 |
| G3 | B. Importo facoltativo | Sì | **Sì** (es. promo a percentuale: il merchant aggiunge il cashback a mano e la campagna conta l'utilizzo) |
| G4 | C. Unicità della parola chiave | Unica tra non archiviate e non finite, diversa da `CARTA` | **Unica tra tutte le non archiviate** (finite comprese: prima si archivia la vecchia, poi si riusa la parola) |
| G5 | D. Modifiche | Tutto modificabile sempre | **Confermato** (controlla il founder; serve anche a correggere errori) |
| G6 | E. Limiti dei campi | Nome 3-40, parola 3-30, testo 1-700, importo 0-50 €, date coerenti | **Vanno bene per ora**; da restringere se un giorno le promo non le crea più il founder |
| G7 | F. Cosa contano le richieste | Messaggi, anche con invio fallito, dedup sugli eventi ripetuti | **Confermato**, riusando i meccanismi che ci sono già |
| G8 | G. Conferma / annulla di «Applica» | Conferma sì, annulla no | **Finestra di conferma sì/no**; solo dopo «sì» cashback + utilizzo. Contatori delle richieste da commento e da DM con la parola chiave giusta (per confrontarli con gli utilizzi in negozio) |
| G9 | Contatore «cashback erogato» | Sì | **No**: importo × utilizzi lo calcola il founder |
| G10 | H. Quota Zernio | Contatore + vista in `/admin` | **Blocco solo manuale del founder**: limite facoltativo, vuoto di default, impostato se il merchant lo chiede (dettagli nel giro 2) |
| G11 | I. Commenti dell'account, risposte, più parole | Ignorati / valgono / prima parola / `CARTA` ignorata | **Parola esatta anche nei commenti** (emoji escluse), niente ricerca nel testo. **`CARTA` vale anche nei commenti** (come, nel giro 2) |
| G12 | Testo del DM | Promo + validità + invito a `CARTA` | Proposta del founder: «Valida dal … al …» (o «Valida il …», o niente se le date non ci sono) + «Per utilizzare questa offerta devi avere la nostra carta fedeltà. Se non l'hai ricevuta o non la ritrovi nella chat scrivi 'CARTA'» + testo della promo. Date facoltative (giro 2) |
| G13 | Negozio in attesa / in pausa | Campagne solo con negozio attivo | «Se archivio o metto in pausa la campagna non parte»: da chiarire nel giro 2 |
| G14 | Esiti nella tabella di dedup | Riusare i valori esistenti | Non chiara: rispiegata nel giro 2 |
| G15 | «Applica» dopo l'ultimo giorno | Niente bottone | **Il bottone resta**: se il merchant applica una campagna scaduta è una sua scelta |
| G16 | Collaudo anticipato | Ticket 01 = collaudo su Instagram vero | **Collaudo alla fine della feature**: i problemi si ricostruiscono dopo. Rischio accettato (codice dei commenti scritto prima di sapere se `comment.received` arriva) |
| G17 | Fuori scope | Roadmap / fuori-scope come proposto | **Dove è più comodo**, purché non si implementino ora |

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

## Modifiche e correzioni

### F-01 — AC-23 accettato come rischio e rischi accettati (2026-11-25) — decisione cambiata

- **Cosa**: il founder accetta come rischio che due «Applica» contemporanei sulla stessa carta non garantiscano il conteggio di entrambi. Nessun test di concorrenza per questo caso.
- **Perché**: il caso (due conferme nello stesso istante sulla stessa carta) è molto raro, e il danno è piccolo (il cliente perde al massimo un accredito). Emerso dalla review di gate 3 (ft-reviewer), come bloccante.
- **Criteri nuovi**: nessuno.
- **Criteri superati**: AC-23 → accettato come rischio (F-01). Il criterio resta nel testo, con la nota «accettato come rischio»: nessun test di concorrenza.
- **Rischi accettati** (decisi dal founder il 2026-11-25):
  - **Standby sui commenti**: un commento gestito da un'altra app riceve comunque la risposta privata (la spec parla solo di DM).
  - **Follower e messaggio non chiarito**: il messaggio «per accedere alla promo devi prima seguire la pagina» non è nel nostro codice (probabile Instagram o Zernio) e il comportamento con un non follower non è verificato. Rinviato al post-MVP, con test più seri.
  - **Negozio in attesa con campagne**: non provato dal vivo. Rinviato al pilota.
  - **«Applica» senza limite per carta**: il merchant decide a chi dare la promo finché è attiva. Comportamento voluto per l'MVP.
- **Contract**: invariato.
- **Ticket**: nessuno (decisione di spec).

### F-02 — Correzioni da review di gate 3 (2026-11-25) — bug

- **Cosa**: tre correzioni emerse dalla review.
  - (a) **Log della risposta privata**: il log di `zernio_service._request` scrive il path della richiesta, che contiene id di post e di commento. Il log non deve contenere quegli id.
  - (b) **Pulsante «Applica» riabilitato dopo un errore di rete**: se la prima richiesta è andata a buon fine, il merchant può accreditare due volte.
  - (c) **Campagna eliminata o archiviata durante «Applica»**: il controllo sulla campagna e l'accredito non sono nella stessa condizione, quindi l'accredito può passare anche se la campagna è sparita.
- **Perché**:
  - (a): i log non devono contenere id che collegano un cliente a un commento (decisione D10).
  - (b) e (c): un doppio accredito o un accredito con campagna sparita sono errori sul cashback.
- **Criteri nuovi**:
  - **AC-31** La risposta privata non scrive nel log né il path con gli id di post e di commento, né il testo del commento; il log riporta solo l'esito e l'id della campagna.
  - **AC-32** «Applica» accredita solo se la campagna è attiva **nello stesso istante** dell'accredito. Se la campagna è stata eliminata o archiviata tra la lettura e la scrittura, nessun accredito, nessun utilizzo e risposta di errore leggibile.
  - **AC-33** Dopo un errore di rete su «Applica», il pulsante resta bloccato finché l'esito non è noto: il merchant ricarica la pagina per vedere il cashback reale e non accredita di nuovo alla cieca.
- **Criteri superati**: nessuno.
- **Contract**: invariato (nessuna firma, endpoint, modello o testo fisso cambia). Il comportamento di log e di atomicità è interno.
- **Ticket**: 08 (AC-31), 09 (AC-32 e AC-33).
- **Stato (2026-11-25)**: AC-32 e AC-33 **accettati come rischi** (decisione del founder): nessun ticket 09, nessun test automatico; il testo resta come criterio con la nota «accettato come rischio».

### F-03 — Test mancanti sui criteri esistenti (2026-11-25) — aggiunta

- **Cosa**: aggiungere i test che mancano per i criteri già nella spec. Nessun comportamento nuovo, nessun criterio nuovo.
- **Perché**: la review ha trovato criteri dichiarati coperti che in realtà non lo sono.
  - **AC-10** (follower): manca il caso `isFollower: true`.
  - **AC-11** (contatore delle richieste): il test non distingue una lettura fresca da una stantia.
  - **AC-15** (limite via commento): manca un commento oltre il limite che riceva «offerte terminate».
  - **AC-17** (commento dell'account del negozio): manca il caso in cui l'autore è il negozio stesso.
- **Criteri nuovi**: nessuno.
- **Criteri superati**: nessuno.
- **Contract**: invariato.
- **Stato (2026-11-25)**: test mancanti su AC-10, AC-11, AC-15 e AC-17 **accettati come rischio** (decisione del founder): nessun ticket 10; i criteri restano coperti come oggi.
- **Ticket**: ⛔ superato (rischio accettato). Se un test rivela un comportamento sbagliato, il bug va in un ticket di correzione, non nel 10.
