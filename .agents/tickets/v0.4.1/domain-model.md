# v0.4.1 — Modello di dominio (gate 2, parte 1 di 2)

> **Stato: APPROVATO il 2026-11-12 (gate 2), CONGELATO.** Insieme a [contracts.md](contracts.md); deriva dalla
> [spec](README.md) approvata il 2026-11-12. I 7 scostamenti qui sotto sono accettati dal founder (il 3 nella forma
> consigliata: campagne ammesse anche con il negozio in pausa). Cambiarlo richiede `/fix`.

## Moduli e responsabilità

| Modulo | Cosa sa | Cosa NON sa |
|---|---|---|
| `app/core/text.py` (nuovo) | `normalize_text` (spostata da `instagram_service`, identica, che la ri-esporta) e il limite di 1000 caratteri di un DM di testo | tutto il resto |
| `app/services/campaign_service.py` (nuovo, core + shell) | validazione dei campi, confronto e unicità della parola chiave, stato mostrato in `/admin`, testi del DM di campagna (promo e «offerte terminate»), scelta del testo in base al limite, inizio della pausa, etichette dello scanner; CRUD admin, riconoscimento e conteggio delle richieste, «Applica» | Zernio, eventi del webhook, HTTP, sessioni admin |
| `app/services/db_crud/campaign_crud.py` (nuovo) | query su `Campaign`: lista per negozio, campagne non archiviate, archiviazione in blocco senza commit, incrementi atomici | regole |
| `app/services/instagram_service.py` | eventi `message.received` e `comment.received`, ordine dei controlli del webhook (D2), finestra di 24 ore, invii, esiti e quota; testo dell'invito `CARTA` da commento | regole delle campagne: le chiede a `campaign_service` |
| `app/services/zernio_service.py` | `send_private_reply` e sua classificazione degli errori, `WEBHOOK_EVENTS` con `comment.received` | regole |
| `app/services/merchant_service.py` | cambio di stato del negozio (dashboard e `PUT /api/merchant/{id}`): se inizia una pausa archivia le campagne nella stessa transazione | regole delle campagne oltre a «la pausa archivia» |
| `app/services/card_service.py` | invariato: `merchant_state` e `check_balance_change` li usa `campaign_service.apply_campaign` | campagne |
| `app/routes/admin.py`, `routes/merchant/{api,views}.py`, `routes/webhooks.py` (invariata) | traducono HTTP ↔ service | regole |
| `app/templates/admin/dashboard.html`, `merchant/update_card.html` | sezione «Campagne» della dashboard; sezione campagne e «Applica» nella gestione della carta | regole |

**Dipendenze (nessun ciclo)**:

```
instagram_service (shell) ─┐
merchant_service  (shell) ─┼─→ campaign_service ─→ card_service, campaign_crud, app/core/*, models
routes (admin, merchant) ──┘
```

`campaign_service` non importa mai `instagram_service`, `merchant_service` né `zernio_service`: per questo
`normalize_text` scende in `app/core/text.py` (stessa ragione per cui nel ticket 12 di v0.3.0 `service_state` stette
in `card_service`). Il ciclo già esistente tra `zernio_service` e il core di `instagram_service` (`CardMessage`) non
cambia e non se ne aggiungono altri.

## Aggregati

Nessun aggregato in senso stretto: ogni invariante si regge su **una riga**, tranne I2, che si regge su un controllo
del service.

- **Contatori e limite** (AC-11, I5): una sola riga `campaign`, aggiornata con `UPDATE … SET n = n + 1 … RETURNING`
  (nessun leggi-modifica-scrivi). La scelta tra promo e «offerte terminate» si fa sul totale **ritornato** da
  quell'`UPDATE`, quindi due richieste sull'ultimo posto vedono totali diversi.
- **«Applica»** (AC-23, I4): due `UPDATE` atomici (`card.cashback_cents + v`, `campaign.uses + 1`) e un solo commit.
- **I2 (parole chiave diverse tra le non archiviate)**: nessun vincolo nel DB (servirebbe un indice unico parziale su
  una forma normalizzata che il DB non conosce). Regge perché **l'unico che scrive le campagne è il founder**, una
  richiesta alla volta dalla dashboard: il controllo sta in `campaign_service` alla creazione, alla modifica e al
  ripristino. Se un giorno le campagne le creasse anche il merchant, va ripensato (roadmap).
- **Pausa → archiviazione** (AC-08): `UPDATE campaign SET is_archived = true WHERE merchant_id = … AND NOT is_archived`
  e cambio di stato del negozio nello stesso commit.

## Regole di business e dove vivono

| # | Regola | Sede |
|---|---|---|
| R1 | Campi (decisioni 4 e 12): nome 3-40, parola chiave 3-30 senza spazi e non vuota dopo la normalizzazione, testo 1-850, importo 0-50 € in centesimi (vuoto = 0, D1), limite intero ≥ 1 o vuoto | core `validate_campaign_input` |
| R2 | Parola chiave: diversa da `INSTAGRAM_CARD_KEYWORD` e da quella di ogni altra campagna **non archiviata** del negozio, sempre confrontando le forme normalizzate (D15) | core `keyword_conflict`; shell `create_campaign`, `update_campaign`, `restore_campaign` |
| R3 | Stato mostrato in `/admin`: archiviata; altrimenti attiva se il negozio è attivo, ferma se è in attesa o in pausa | core `campaign_status` |
| R4 | Riconoscimento (decisione 5): testo normalizzato **uguale** alla parola chiave normalizzata, solo tra le non archiviate del negozio | core `match_campaign`; shell `handle_campaign_request` |
| R5 | Una richiesta conta solo per una campagna **attiva** (negozio attivo): altrimenti nessun contatore e nessun invio (AC-12, AC-17) | shell `handle_campaign_request` |
| R6 | Il totale dopo l'incremento (DM + commenti) ≤ limite → promo; oltre → «offerte terminate» (D3); senza limite sempre promo | core `is_within_limit`, `campaign_reply_text` |
| R7 | Testi: promo + riga vuota + riga fissa con la parola di `CARTA`; «offerte terminate»; invito `CARTA` da commento; ogni DM ≤ 1000 caratteri | core `build_promo_text`, `build_exhausted_text` (campagne), `build_comment_card_invite_text` (instagram) |
| R8 | Ordine nel webhook dei DM (D2): dedup → account → in arrivo → standby → `CARTA`/menu (invariato) → parola di campagna → ignorato. `isFollower` non conta per le campagne | shell `instagram_service._process_message` |
| R9 | DM di campagna: la richiesta si conta **prima** della finestra di 24 ore; fuori finestra nessun invio (D4) | shell `instagram_service` |
| R10 | Commento: `CARTA` → invito in ogni stato del negozio (D7), nessun contatore; parola di campagna attiva → risposta privata; nessun controllo nostro dei 7 giorni | shell `instagram_service` |
| R11 | Ogni invio riuscito (DM o risposta privata) conta nella quota e attiva il collegamento in attesa del DM di prova (D5); un invio incerto conta ma non attiva; nessun nuovo tentativo | shell `instagram_service._record_send` (esistente) |
| R12 | La pausa (passaggio dello **stato derivato** ad «in pausa», da qualunque strada) archivia le campagne non archiviate nella stessa transazione; «Avvia» e «Riattiva» non ripristinano (D13) | core `pause_begins`; shell `merchant_service.set_merchant_state`, `update_merchant_as_admin` |
| R13 | «Applica»: carta del negozio (404) → campagna del negozio, anche archiviata (404) → `check_balance_change(stato, importo)` (403) → cashback + importo **attuale** e utilizzi + 1 in una transazione; nessun tree point, pool, conversione o `PointTransaction` | shell `apply_campaign` |
| R14 | Scanner: campagne non archiviate dalla più recente, etichetta «Applica <nome> (+X,XX €)» o «Applica <nome>» | core `scanner_label`; shell `scanner_campaigns` |

## Glossario aggiornato

Nessun termine nuovo oltre a quelli già entrati in `.agents/glossario.md` al gate 1. Nel codice: **canale** di una
richiesta = `RequestChannel.DM` (DM e risposte alle storie) o `RequestChannel.COMMENT`; **campagna ferma** = non
archiviata di un negozio non attivo (stato `stopped` in `/admin`).

## Scostamenti dalla spec (da approvare insieme al contract)

1. **DM di campagna e conversazione di un'altra app**: un invio rifiutato con `not_thread_owner` dà `STANDBY` (con
   l'avviso nel pannello del merchant), come oggi per `CARTA`, e non `SEND_FAILED` come direbbe D6. Si riusa
   `_handle_send_error` così com'è. Per le **risposte private** invece vale AC-18 alla lettera: ogni errore diverso dal
   timeout è `SEND_FAILED` (con chiave rifiutata anche lo stato «chiave non valida» nel pannello, come oggi).
2. **Nessun default lato DB**: script SQL e modello coincidono **senza** `DEFAULT` sulle colonne (oggi nessuna tabella
   ne ha: `create_all()` non li crea); i valori iniziali li mette sempre l'app. Il test di AC-28 è più forte di quello
   della spec: confronta lo script con il DDL PostgreSQL generato dal modello (tipi, lunghezze, `NOT NULL`, chiave
   esterna con `ON DELETE CASCADE`, indice), non solo i nomi delle colonne.
3. **Campagne create o ripristinate su un negozio in pausa**: nulla lo impedisce (la spec non lo dice). La campagna
   resta «ferma»: il webhook la ignora, nello scanner «Applica» con importo dà 403 e con importo 0 conta solo
   l'utilizzo. La nota di AC-24 («un negozio in pausa non ha campagne non archiviate») vale quindi solo subito dopo
   la pausa, non sempre. **Accettato al gate 2**: nessun 409 su creazione e ripristino con negozio in pausa (meno
   codice; il founder è l'unico a farlo).
4. **I2 senza vincolo nel DB** (vedi «Aggregati»): regge sul controllo del service perché il founder è l'unico che
   scrive.
5. **Lunghezze in caratteri Python**: 1000 è contato come `len()` (punti di codice). Se Instagram contasse unità
   UTF-16, un testo della promo pieno di emoji potrebbe superare il limite e l'invio fallirebbe (`SEND_FAILED`).
   Da verificare nel collaudo finale; non si cambia il conteggio senza un dato vero.
6. **Risposte alle storie senza codice nuovo**: arrivano come `message.received` con `metadata.storyReply` e il testo
   in `message.text` (archivio `feature/campagne`, da spec Zernio), quindi passano dal riconoscimento dei DM e contano
   come richieste da DM. Un test con quel payload lo fissa.
7. **Parola chiave salvata come scritta dal founder** (spazi ai lati tolti), mai normalizzata nel DB: la forma
   normalizzata si calcola a ogni confronto (poche campagne per negozio). La lunghezza 3-30 vale sulla forma scritta;
   l'unicità e il riconoscimento sulla forma normalizzata (`black-friday` e `Black_Friday` sono la stessa parola).

## Rischi aperti (si chiudono nel collaudo finale, ticket 06)

Il collaudo anticipato non c'è per decisione del founder (decisione 13). Il codice dei commenti si scrive dalla spec
Zernio e dalle note dell'archivio; se Instagram vero si comporta diversamente si apre una voce `/fix`.

- `comment.received` arriva al webhook del negozio con l'account Zernio gratuito, firmato come i DM.
- Campi del payload: `account.accountId`, `comment.id`, `comment.platformPostId`, `comment.text`; `{postId}` della
  risposta privata = `comment.platformPostId`.
- Risposta privata di solo testo consegnata a un non follower; conta nella quota Zernio come un DM.
- Testo della risposta a una storia in `message.text`.
- Conteggio dei 1000 caratteri (scostamento 5).
