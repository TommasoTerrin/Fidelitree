# Campagne promozionali

> **Da v0.4.1, non ancora in produzione.** Questo file descrive le regole che il ticket 01 ha reso vere (modello e
> core puro). La gestione dal founder (API admin, pausa che archivia) è del ticket 02 e sta in [admin.md](admin.md); il webhook dei DM è del ticket 03 (sezione «Richieste in DM»); commenti e scanner si aggiungono con i ticket 04-05.
> Spec della versione: [tickets/v0.4.1/README.md](../tickets/v0.4.1/README.md); contract congelato:
> [contracts.md](../tickets/v0.4.1/contracts.md); decisioni: [0001](../decisions/0001-campagne-pilota-coupon-dm.md),
> [0002](../decisions/0002-commenti-risposta-privata-testo.md), [0003](../decisions/0003-pausa-archivia-campagne.md),
> [0004](../decisions/0004-applica-nello-scanner.md).

## A cosa serve

Una **campagna** è una promozione di un negozio, creata dal founder dalla dashboard `/admin`: un cliente la richiede
scrivendo la **parola chiave** della campagna (in DM, come risposta a una storia o in un commento) e riceve in DM il
testo della promo. Il merchant può poi «applicare» la campagna dallo scanner e accreditare l'importo alla carta.

## Il modello `Campaign` (tabella `campaign`)

| Campo | Regola |
|---|---|
| `merchant_id` | negozio proprietario; `ON DELETE CASCADE` |
| `name` | 3-40 caratteri (dopo lo `strip`) |
| `keyword` | come l'ha scritta il founder (dopo lo `strip`), **mai normalizzata** in tabella; 3-30 caratteri, nessuno spazio interno, non vuota dopo la normalizzazione |
| `promo_text` | 1-850 caratteri (`strip` ai lati, gli a capo interni restano) |
| `value_cents` | 0-5000 (0 = nessun importo); l'euro compare solo ai bordi |
| `request_limit` | `None` = nessun limite; altrimenti intero ≥ 1 |
| `is_archived` | vero = non risponde più ai clienti |
| `dm_requests`, `comment_requests`, `uses` | contatori; la modifica non li tocca |
| `created_at` | UTC aware |

Lo **stato** (`attiva` / `archiviata` / `ferma`) non è una colonna: si deriva da `is_archived` e dallo stato del
servizio del negozio (`campaign_status`). «Ferma» = negozio in attesa o in pausa.

## Parola chiave

- Il confronto usa `normalize_text` (`app/core/text.py`): maiuscole, accenti, punteggiatura ed emoji ignorati.
- Una parola è in conflitto se normalizzata è uguale a quella di `CARTA` (`riservata`) o a quella di un'altra
  campagna **non archiviata** dello stesso negozio (`in uso`); `riservata` ha la precedenza. Due negozi possono usare
  la stessa parola; una campagna archiviata non blocca nessuna parola.
- Il riconoscimento di una richiesta (`match_campaign`) sceglie la prima campagna, nell'ordine ricevuto, che combacia.

## Testi dei DM

- Il DM della promo è `promo_text` + riga fissa con la parola di `CARTA` (`INSTAGRAM_CARD_KEYWORD`, passata come
  argomento: il core non legge la configurazione). Con una promo di 850 caratteri il DM sta sotto i 1000
  (`INSTAGRAM_TEXT_MAX`); oltre → `MessageTooLongError`.
- Finito il limite (`total_requests > request_limit`, totale DM + commenti dopo l'incremento) il cliente riceve il
  testo fisso «offerte terminate».

## Richieste in DM (ticket 03)

- `handle_campaign_request(session, merchant, text, canale)`: cerca tra le campagne non archiviate del negozio
  (`created_at` decrescente) quella la cui parola combacia; nessuna → `None`. **Negozio non attivo (in attesa o in
  pausa) → `None` e nessun conteggio** (il controllo viene prima del conteggio). Poi `register_request` e il testo
  scelto sul totale dopo l'incremento.
- `register_request` è **un solo `UPDATE … RETURNING`** (`campaign_crud.increment_request_counter`) seguito dal
  commit: non legge i contatori dall'oggetto in memoria. Campagna sparita nel frattempo → `None` (esito `IGNORED`).
- Il webhook (`instagram_service`) manda il testo come DM con chiave `<evento>:promo`; regole del flusso in
  [carta-instagram.md](carta-instagram.md).

## Validazione

`validate_campaign_input` accetta il corpo grezzo e dà `InvalidInputError` (400) per ogni valore non valido, mai
`TypeError`; il messaggio cita campo e regola, mai il valore inviato. Un `float` senza parte decimale vale come
intero per il limite; per l'importo si accetta anche una stringa con virgola o punto.

## Invarianti

- Le campagne **non salvano dati dei clienti** (né testo, né IGSID, né username, né id del commento) e i log non li
  riportano (I6).
- Il core resta puro (I7); le tabelle e gli enum esistenti non cambiano (I8).

## Codice

`app/services/campaign_service.py` (sezione «Core puro»), `app/core/text.py`, `Campaign` in `app/models/models.py`,
script `migrations/0001_campagne.sql`.
