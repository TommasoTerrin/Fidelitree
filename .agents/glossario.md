# Glossario

Il vocabolario del dominio, **unico per tutto il progetto**: spec, ticket, codice, test e messaggi usano questi
termini e non dei sinonimi. Un termine nuovo nasce nel grilling (`/new-feature`) e si aggiunge qui al gate 1
(`/spec`); il glossario della spec di una versione elenca solo i termini nuovi di quella versione.

| Termine | Significato | Nel codice |
|---|---|---|
| **Founder** | Chi gestisce la piattaforma: approva i negozi, crea le campagne, paga gli alberi | dashboard `/admin` |
| **Merchant** / **negozio** | Il piccolo negozio che usa Fidelitree (PWA per lo scanner) | `Merchant` |
| **Cliente** | Chi scrive al negozio su Instagram; non ha account, vede la carta con un link segreto | — (nessuna tabella) |
| **Carta** | La carta fedeltà di un cliente presso un negozio: una per coppia (negozio, IGSID) | `Card` |
| **Link della carta** | `/c/<token>`, token HMAC mai salvato in chiaro | `card_link_token` |
| **IGSID** / **indice cieco** | L'id Instagram del cliente per quel negozio; se ne salva solo l'HMAC | `crypto` |
| **Parola chiave** | Testo che il cliente scrive in DM per avere la carta (`CARTA`) o una campagna | `INSTAGRAM_CARD_KEYWORD` |
| **Card** (messaggio) | Il messaggio Instagram con titolo, sottotitolo e un bottone che apre la pagina | `instagram_service` |
| **Tree points** | Punti che il merchant assegna allo scan; alimentano il pool | `PointTransaction` |
| **Cashback** | Credito in euro (centesimi) sulla carta, pagato dal merchant | `*_cents` |
| **Conversione** | Tree points della carta → cashback al raggiungimento della soglia del merchant | `card_service` |
| **Pool** | Somma dei tree points netti di un negozio nel mese solare UTC | `MerchantPool` |
| **Livello** | Bronzo / argento / oro: quanti alberi pianta il pool a fine mese | `Level` |
| **Chiusura del periodo** | Script mensile che pianta gli alberi del livello raggiunto | `scripts.close_period` |
| **Stato del servizio** | In attesa / attivo / in pausa, derivato da `is_approved` e `is_paused` | `ServiceState` |
| **Carta di prova** | Carta fittizia per i clienti nuovi di un negozio in attesa | `/carta-di-prova` |
| **Campagna** | Promo di un negozio: nome, parola chiave, testo della promo, importo di cashback (0 = nessuno), limite di richieste facoltativo, archiviata sì/no, contatori; il DM ricevuto è il coupon. Nessuna data nel pilota (v0.4.1) | `Campaign` |
| **Testo della promo** | Testo libero del founder (validità compresa); prima parte del DM di risposta | `Campaign.promo_text` |
| **Campagna archiviata** | Spenta: la parola chiave è una parola qualsiasi, non compare nello scanner; si ripristina | `Campaign.is_archived` |
| **Campagna attiva** | Non archiviata, di un negozio attivo | — |
| **Richiesta** | DM (risposte alle storie comprese) o commento il cui testo normalizzato è esattamente la parola chiave di una campagna attiva; contata per canale | `Campaign.dm_requests`, `comment_requests` |
| **Limite di richieste** | Numero facoltativo: oltre, la risposta è «offerte terminate» | `Campaign.request_limit` |
| **Risposta privata** | Il DM con cui Instagram risponde a un commento: uno per commento, solo testo | `zernio_service` |
| **Utilizzo** | Un «Applica» confermato nello scanner: accredita l'importo della campagna e incrementa il contatore | `Campaign.uses` |
