# Brief per il grilling — campagne pilota

> Scritto il 2026-11-12 con il founder, prima di `/new-feature`. È la «richiesta iniziale» del grilling: le decisioni
> qui sotto sono già prese, il grilling chiude solo i punti aperti e i quattro temi della skill. Dopo il grilling
> questo file si può eliminare (il contenuto finisce nel `README.md` della versione).

## Contesto

Rifà le campagne in forma ridotta per partire con i primi pilota. La versione precedente (v0.4.0: adesioni salvate
nella carta, pagina `/p/<token>`, secondo QR, promozioni multiple, limiti per cliente) è **archiviata** sul branch
`feature/campagne`: non si mergia, si copia solo ciò che serve. Motivo: troppa logica e troppo DB per un pilota; ora
conta partire con le cose più spettacolari e avere i primi pilota.

## Obiettivo

Il negozio pubblica una campagna su Instagram («commenta o scrivici NATALE»). Chi scrive la parola chiave riceve in
DM il testo della promo: **quel DM è il coupon** da mostrare in cassa. Il merchant scansiona la carta del cliente e
preme «Applica»: cashback accreditato e utilizzo contato. Le campagne rendono più interattivo il rapporto
negozio-clienti su Instagram (seguire, guardare i post, commentare).

## Decisioni già prese

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
   ritentata). Ogni risposta consuma un invio della quota Zernio (10.000 al mese), come un DM normale.
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
11. **Contatori** visibili in `/admin`: richieste da DM, richieste da commento, utilizzi («Applica»), cashback erogato.

## Da decidere nel grilling (con la raccomandazione dell'agente)

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

## Rischi da verificare per primi (primo ticket: collaudo su Instagram vero)

- `comment.received` arriva al webhook del negozio, firmato come i DM, con l'**account Zernio gratuito** e il
  collegamento Instagram di oggi (se i negozi devono ricollegarsi o pagare: fermarsi e decidere);
- risposta privata di solo testo consegnata a un **non follower**; `{postId}` = `comment.platformPostId`;
- come riconoscere i commenti dell'account stesso (`isOwner` o altro);
- campo del testo nella risposta a una storia (`metadata.storyReply`);
- cambiare gli eventi dei webhook dei negozi già collegati senza farli ricollegare (`PUT /v1/webhooks/settings`,
  dalla spec Zernio, non ancora provato).

Se i commenti non funzionano con l'account gratuito: **piano B** = solo DM e storie, i commenti in roadmap.

## Riuso dall'archivio (`feature/campagne`)

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

## Fuori scope (da registrare in roadmap o in `.agents/fuori-scope.md` nel grilling)

Promo salvata nella carta, utilizzo unico o N volte per cliente, pagina `/p/` e QR della promo, più promozioni per
campagna, «porta un amico» (affiliazione), campagne create dal merchant, dati per cliente, risposta pubblica ai
commenti.
