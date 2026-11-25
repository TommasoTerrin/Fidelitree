# Dashboard admin del founder

> Le parti sulle **campagne** e sulla **pausa che archivia** sono **da v0.4.1, non ancora in produzione**.
> Le regole di accesso, la lista dei negozi e le azioni di stato sono quelle in produzione dalla v0.3.0.
> Contract: [tickets/v0.4.1/contracts.md](../tickets/v0.4.1/contracts.md) §5, §8, §9. Schede:
> [0001](../decisions/0001-campagne-pilota-coupon-dm.md), [0003](../decisions/0003-pausa-archivia-campagne.md).

## A cosa serve

`/admin` è l'unico strumento del founder per i negozi pilota: li avvia, li mette in pausa, li riattiva, reimposta le
password e (da v0.4.1) gestisce le **campagne** di ciascun negozio. Un solo accesso, `ADMIN_SECRET_KEY`; nessun account admin.

## Accesso e sicurezza (valgono per ogni endpoint, campagne comprese)

- Sessione a cookie `admin_session` (JWT `role=admin`, 12 ore, `Path=/admin`) oppure header `X-Admin-Key`.
  Senza nessuno dei due: API → 401, pagine → 303 al login. Chiave admin vuota = accesso chiuso.
- POST, PUT e DELETE con cookie controllano che `Origin` (o `Referer`) sia il nostro host: 403 altrimenti (con
  `X-Admin-Key` corretto non serve). Il controllo precede il freno del login.
- Le risposte **di successo** portano `Cache-Control: no-store`, `X-Robots-Tag: noindex`, `Referrer-Policy: same-origin`.
  Le risposte di errore (400, 401, 403, 404, 409) **non** li portano, come in tutta la dashboard: scelta del founder
  del 2026-11-13 (non portano dati personali).
- DOM costruito solo con `textContent` / `createElement`: nessun `innerHTML`, `insertAdjacentHTML`, `outerHTML`,
  `eval`, `| safe` (i nomi li scrivono i merchant e il founder). Un test lo verifica sul sorgente del template.
- Nessuna risposta riporta chiavi, secret, `hook_id` o hash.

## Negozi: lista e azioni di stato

`GET /admin/api/merchants` (al massimo 200, dal più recente) e `POST /admin/api/merchants/{id}/approve|pause|resume|reset-password`.
Transizioni: `approve` imposta `is_approved` e toglie la pausa; `pause` e `resume` valgono solo per un negozio approvato
(409 su uno in attesa); ripetere un'azione è un no-op con 200.

## Campagne di un negozio (da v0.4.1, non ancora in produzione)

| Endpoint | Cosa fa |
|---|---|
| `GET /admin/api/merchants/{id}/campaigns` | lista `{"campaigns": [...]}`: non archiviate prima, poi archiviate; dentro ogni gruppo `created_at` decrescente, poi `id` decrescente (AC-01) |
| `POST …/campaigns` | crea (201): non archiviata, contatori a 0; importo in euro (`value_eur`), vuoto = 0 (AC-02) |
| `PUT …/campaigns/{cid}` | sostituisce tutti i campi modificabili; contatori, archiviazione e data restano; abbassare il limite sotto le richieste contate è ammesso (AC-05) |
| `POST …/campaigns/{cid}/archive` / `…/restore` | cambiano solo lo stato, idempotenti; il ripristino rifà il controllo della parola (AC-06) |
| `DELETE …/campaigns/{cid}` | cancella la riga (contatori compresi); la parola torna libera; il secondo DELETE è 404 (AC-06) |

- Validazione nel service, mai 422: un campo non valido dà **400** con un messaggio che non rimanda indietro il valore
  (AC-03). Limiti: nome 3-40, parola 3-30 senza spazi, testo 1-850, importo 0-50 €, limite ≥ 1.
- **409** se la parola, normalizzata, è uguale a `INSTAGRAM_CARD_KEYWORD` (sempre) o a quella di un'altra campagna **non
  archiviata** dello stesso negozio; vale a creazione, modifica e ripristino. Due negozi possono avere la stessa parola
  (AC-04).
- **404** per negozio o campagna inesistenti o di un altro negozio, con lo stesso messaggio (AC-07).
- La pagina ha, per ogni negozio, il pulsante «Campagne» con lista, form crea/modifica e i pulsanti «Archivia»,
  «Ripristina», «Elimina» (quest'ultimo dopo `confirm()`). «ferma: negozio non attivo» è lo stato di una campagna non
  archiviata di un negozio in attesa o in pausa.

## La pausa archivia le campagne (da v0.4.1, non ancora in produzione)

Quando un negozio **passa** a «in pausa» (azione «Metti in pausa» o `PUT /api/merchant/{id}` con `is_paused`), tutte le
sue campagne non archiviate si archiviano **nello stesso commit** del cambio di stato; se il salvataggio fallisce
(anche con un 400) nessuna campagna risulta archiviata (AC-08). «Riattiva» e «Avvia» non ripristinano nulla: il founder
ripristina a mano, una per una. Pausa su un negozio già in pausa, o su uno in attesa (409 dalla dashboard), non archivia nulla.

## Codice

`app/routes/admin.py`, `app/templates/admin/dashboard.html`, `app/services/campaign_service.py` (shell admin e
`archive_on_pause`), `app/services/db_crud/campaign_crud.py`, `app/schemas/campaign.py`,
`app/services/merchant_service.py` (`set_merchant_state`, `update_merchant_as_admin`, `_update_archiving_on_pause`).
