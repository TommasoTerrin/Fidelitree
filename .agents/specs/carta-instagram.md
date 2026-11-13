# Carta via DM Instagram (trigger, card, follower, 24 h, quota, standby)

> Regole vigenti dell'area, ricavate da AGENTS.md («Vincoli e trade-off accettati») e dal codice di
> `instagram_service`. **Le parole chiave delle campagne in DM e i commenti con risposta privata sono da v0.4.1, non ancora
> in produzione** (ticket 03 e 04; nulla di Zernio/Meta sui commenti è provato dal vivo: lo fa il ticket 07). Scheda: [0002](../decisions/0002-commenti-risposta-privata-testo.md).
> Spec della versione: [tickets/v0.4.1/README.md](../tickets/v0.4.1/README.md) (AC-09..13).

## Flusso di un `message.received`

Un solo endpoint per negozio, `POST /webhooks/zernio/{hook_id}`. Ordine: negozio dal `hook_id` → firma → JSON → riga
dell'evento inserita **per prima** (dedup, un duplicato esce subito; righe tenute 7 giorni) → messaggio → standby →
trigger. Risposta HTTP sempre 200 per ogni esito (401 per la firma, 404 per un `hook_id` sconosciuto).

1. **Standby** (un'altra app possiede la conversazione): nessun invio, nessun contatore, avviso nel pannello del merchant.
2. **`CARTA`** (parola di piattaforma `INSTAGRAM_CARD_KEYWORD`) o voce di menu «🌳 La mia carta» (postback
   `FIDELITREE_CARD`): flusso della carta, sotto.
3. **Altro testo** (anche la risposta a una storia, che è un `message.received` con `metadata.storyReply`):
   si confronta con le parole delle campagne, sotto. Un postback diverso dal nostro è ignorato.
4. Tutto il resto → `IGNORED`, in silenzio.

Il confronto delle parole è sempre sulla forma normalizzata (`normalize_text`: maiuscole, accenti, punteggiatura ed
emoji ignorati) e **esatto**: «carta» vale, «vorrei la carta» no.

## La carta (`CARTA` e voce di menu)

- Una sola card (generic template): titolo = nome del negozio, sottotitolo fisso, bottone «Apri la carta». Nessun dato
  dinamico. Unico ripiego: testo fisso con il link se Meta rifiuta la card a un non follower.
- **Solo a chi segue**: `isFollower` `true` o `null` → card; `false` → nessuna carta, solo il testo di invito a
  seguire (`follow_requested`).
- **Negozio in attesa**: a un cliente nuovo la card porta a `/carta-di-prova` (nessuna riga `Card`); chi ha già una
  carta riceve il suo link. In pausa non cambia nulla.

## Le parole chiave delle campagne in DM (da v0.4.1, non ancora in produzione)

- Il testo del DM (o della risposta a una storia) uguale, dopo la normalizzazione, alla parola di una campagna **non
  archiviata** del negozio fa rispondere con un **DM di testo**: promo + riga vuota + riga fissa «Per utilizzare questa
  offerta devi avere la nostra carta fedeltà…» (AC-10). Se la stessa parola è in una campagna archiviata e in una non
  archiviata risponde la non archiviata e contano solo i suoi contatori (AC-09).
- **`isFollower` è ignorato**; nessuna carta letta, creata o modificata, nessun tree point né cashback (AC-10).
- **Limite**: la richiesta si conta con un solo `UPDATE … RETURNING` atomico (`register_request`) e il totale
  (DM + commenti) è quello **dopo** l'incremento; fino a `request_limit` incluso si manda la promo, oltre il testo
  «offerte terminate». La richiesta oltre il limite è contata comunque (AC-11).
- **Campagna archiviata o negozio in attesa/in pausa**: nessun invio, nessun contatore, `IGNORED` (AC-12).
- Valgono le regole del webhook (AC-13): firma, dedup (un evento ripetuto non manda e non conta), standby (nessun
  contatore), **finestra di 24 ore** (fuori finestra `OUT_OF_WINDOW`, senza invio ma con la richiesta già contata),
  quota +1 per invio riuscito o incerto, **nessun nuovo tentativo**, 200 per ogni esito.
- Esiti: `SENT`; timeout di lettura → `SEND_UNCERTAIN` (quota +1, negozio non attivato); chiave rifiutata →
  `KEY_INVALID` e `SEND_FAILED`; conversazione di un'altra app → `STANDBY`; testo troppo lungo → `SEND_FAILED` senza invio.
- Idempotenza verso Zernio: `Idempotency-Key` = `<event_id>:promo`.

## I commenti `comment.received` (da v0.4.1, non ancora in produzione)

- Stessa route, stessa firma e stessa dedup dei DM; il negozio sottoscrive `message.received` e `comment.received`
  alla registrazione del webhook (un negozio già collegato si aggiorna con «Scollega» e nuovo collegamento) (AC-14, AC-20).
- Si leggono solo `account.accountId`, `comment.id`, `comment.platformPostId` e `comment.text`; un commento di un altro
  account o con campi mancanti è `IGNORED`. Una risposta a un altro commento vale come un commento.
- Commento uguale a `CARTA` (normalizzato) → **risposta privata di solo testo** «Per ricevere la tua carta scrivici CARTA
  qui in chat», **in ogni stato del negozio**; nessuna carta, nessun contatore (AC-16).
- Commento uguale alla parola di una campagna non archiviata di un negozio attivo → risposta privata con lo stesso testo
  dei DM (promo o «offerte terminate»), richieste da commento +1 (AC-15). Altrimenti `IGNORED`, nessun contatore (AC-17).
- Nessuna risposta pubblica, nessuna finestra di 24 ore nostra (i 7 giorni li controlla Meta), nessun nuovo tentativo.
- Errori: timeout o esito sconosciuto → `SEND_UNCERTAIN` (quota +1, negozio non attivato); chiave rifiutata →
  `KEY_INVALID` e `SEND_FAILED`; **ogni altro** errore (anche `NOT_THREAD_OWNER`, `NOT_FOLLOWER`, già usata) →
  `SEND_FAILED`, mai standby; la richiesta è comunque contata (AC-18). Un invio riuscito conta +1 in quota (AC-19).
- Log: negozio, evento, esito, id campagna e canale `commento`; mai testo, id del commento o del post.

## Finestra, quota, standby

- Si risponde solo entro **24 ore** dal `sentAt` del cliente (non dall'arrivo del webhook); nessun invio proattivo.
- **Quota**: `ZernioSendCounter` per ambito (`account:<id>`) e mese UTC; avviso alla soglia (75%), nessun blocco
  nostro. Un invio riuscito o incerto conta +1.
- Timeout verso Zernio 4 s, webhook che risponde entro 5 s, nessun nuovo tentativo sugli invii.

## Invarianti

- Del cliente non si salva né il testo né l'IGSID in chiaro (solo l'indice cieco HMAC per le carte); le campagne non
  salvano nessun dato dei clienti. **Nei log**: id del negozio, dell'evento, esito e, per le campagne, id e canale
  (`dm`); mai testo, IGSID, chiavi o token (I6, AC-13).
- Il core di `instagram_service` è puro (tempo e parola di `CARTA` si passano come argomenti).

## Codice

`app/services/instagram_service.py` (core e shell del webhook; `_reply_with_campaign` per le campagne),
`app/services/campaign_service.py` (`handle_campaign_request`, `register_request`), `app/services/zernio_service.py`,
`app/routes/webhooks.py`. Fonti dei vincoli: [zernio-notes.md](../architecture/zernio-notes.md).
