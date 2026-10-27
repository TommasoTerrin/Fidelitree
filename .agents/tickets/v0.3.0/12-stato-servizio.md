# 12 — Stato del servizio: approvazione, pausa e carta di prova

## Obiettivo
Il founder decide **chi usa davvero la carta**:
- un merchant appena iscritto può collegare il suo Instagram, ma finché non è **approvato** i suoi clienti ricevono un link a una
  **pagina con una carta fittizia di prova** (nessuna carta vera, nessun dato salvato);
- un merchant **in pausa** (periodo di prova finito o abbonamento non pagato) non può più **aggiungere** tree points o cashback,
  ma solo **togliere** quelli esistenti.

I comandi per cambiare stato sono nel ticket 13 (dashboard); qui nasce il modello e il comportamento di app, webhook e pagine.

## Contesto
Decisioni del 2026-10-27 (utente). Oggi `is_approved` conta solo per la chiusura del pool (`tree_service`); un merchant non
approvato «lavora subito» (scan e punti). Cambia: non approvato = nessuna carta vera.

Stati derivati (nessun nuovo enum, due flag):

| `is_approved` | `is_paused` | Stato | Cosa succede |
|---|---|---|---|
| `False` | — | **In attesa** | webhook e pannello Instagram funzionano (si può fare il DM di prova), ma il link della card porta alla carta di prova; nessuna riga `Card`; scan e movimenti bloccati |
| `True` | `False` | **Attivo** | tutto come oggi |
| `True` | `True` | **In pausa** | le carte esistono e si aprono (con un avviso); non si aggiunge nulla, si può solo togliere |

Scelte mie, **da confermare** (sono nei test e nel testo del ticket; se non ti vanno cambio prima di implementare):
1. Un merchant **in attesa** non crea righe `Card` né salva l'indice cieco dell'IGSID: il bottone della card punta a una pagina
   pubblica fissa `/carta-di-prova` (nessun token). Alla successiva approvazione il cliente riscrive `CARTA` e riceve la carta
   vera.
2. Un merchant **in pausa** continua a servire le carte (esistenti e nuove, a saldo 0) con un avviso «servizio sospeso»: il
   cliente può vedere e usare il cashback già accumulato presso il negozio, che il merchant può scalare.
3. I negozi **in pausa sono esclusi dalla chiusura mensile** (`close_period`): gli alberi li paga il founder.
4. «Togliere» vale sia per il cashback (`add-point` con delta negativo) sia per i tree points (`add-tree-points` con delta
   negativo); la conversione automatica non scatta mai in pausa (nessun accredito). Anche per il merchant **in attesa** ogni
   movimento è bloccato (non dovrebbero esserci carte).
5. Se un merchant **approvato** viene riportato a «in attesa» dall'admin, i suoi link `/c/<token>` mostrano la carta di prova
   (stato derivato dal merchant, non dalla carta).

## Dipendenze
06, 08, 11 (non strettamente, ma l'accesso in produzione serve per usarlo).

## Modifiche
1. **Modello**: `Merchant.created_at` (UTC, per la lista admin) e `Merchant.is_paused` bool (default `False`). Schema da
   resettare come sempre (`create_all`, niente Alembic).
2. **Core puro** (nuovo modulo o sezione di `merchant_service`): `ServiceState` (`pending`, `active`, `paused`),
   `service_state(is_approved, is_paused)`, `can_add_balance(state)` e `can_remove_balance(state)`. Solleva `ForbiddenError` con
   messaggio chiaro («In attesa di approvazione», «Servizio in pausa: puoi solo togliere il saldo esistente») quando un
   movimento non è ammesso. Tutto testabile senza DB.
3. **`card_service`**: `add_tree_points` e il cashback applicano il controllo (delta > 0 solo se attivo; delta < 0 se attivo o in
   pausa; delta = 0 resta com'è oggi). Le route `/api/merchant/add-point` e `/add-tree-points` traducono in 403.
4. **Webhook** (`instagram_service`): se il merchant è in attesa, dopo trigger e `isFollower` **non** si crea la carta: si
   risponde con la stessa card (titolo = nome negozio, sottotitolo, bottone) il cui URL è `<PUBLIC_BASE_URL>/carta-di-prova`.
   Il resto (finestra 24 h, contatore, passaggio `AWAITING_TEST_DM` → `ACTIVE`, esiti) resta invariato; l'esito è `sent` come per
   la card vera. In pausa: nessuna differenza nel webhook.
5. **Pagine**:
   - `GET /carta-di-prova` (pubblica, senza dati, `noindex`, no-store): carta con design identico alla vera ma riempita di valori
     fittizi e un'etichetta ben visibile «CARTA DI PROVA»; testo: il negozio sta provando Fidelitree e deve richiedere
     l'approvazione per attivare il servizio. Niente QR vero.
   - `GET /c/{token}`: se il negozio è in attesa mostra la stessa pagina di prova; se in pausa mostra la carta con un avviso
     «servizio sospeso: non è possibile accumulare nuovi punti».
   - Pagine merchant (scanner, manage, impostazioni): banner di stato (in attesa/in pausa) e pulsanti di aggiunta disattivati
     con la spiegazione; quelli di rimozione restano attivi in pausa.
6. **`tree_service.close_period`**: oltre a `is_approved`, esclude `is_paused`; l'anteprima mostra quanti negozi sono saltati
   perché in pausa. `pool_mismatches` e cap invariati.
7. **Seed e script**: `seed_db` crea i due merchant approvati e attivi (come oggi); lo smoke test controlla `/carta-di-prova` 200.
8. **Privacy**: la bozza di `/privacy` non cambia; nota nel ticket 14: un negozio in attesa non salva alcun dato del cliente.
9. **Docs**: AGENTS.md (nuova voce «Stato del servizio: attesa, attivo, pausa» nei vincoli; «Come funziona»: il punto 2 dice che
   la carta vera la ricevono solo i clienti di negozi approvati), overview.md (modello, flusso del webhook, endpoint
   `/carta-di-prova`), planner.

## File coinvolti
`app/models/models.py`, `app/core/errors.py` (se serve un messaggio dedicato), `app/services/merchant_service.py` o
`card_service.py`, `app/services/instagram_service.py`, `app/services/tree_service.py`, `app/routes/consumer/views.py`,
`app/routes/merchant/api.py`, template `consumer/card.html`, `consumer/test_card.html`, `merchant/*.html`,
`scripts/smoke_test_prod.py`, docs sopra.

## Test da superare
- Core: `service_state` per le 4 combinazioni di flag; permessi di aggiunta/rimozione per ogni stato; delta 0.
- Scan/cashback: in attesa → 403 per ogni movimento; in pausa → 403 per delta positivo, ok per negativo (cashback **e** tree
  points), nessuna conversione, pool invariato dal negativo come oggi; attivo → come prima (suite esistente verde).
- Webhook: merchant in attesa → una card con URL `/carta-di-prova` e **nessuna riga `Card`** (né indice cieco); `AWAITING_TEST_DM`
  diventa `ACTIVE`; contatore invii +1; invito a seguire invariato; finestra 24 h invariata; approvazione e nuovo `CARTA` →
  carta vera con link `/c/<token>`. In pausa → carta vera come oggi.
- Pagine: `/carta-di-prova` (200, etichetta, nessun dato dinamico, no-store, nessun QR scansionabile); `/c/<token>` di un negozio
  in attesa → pagina di prova; in pausa → carta con avviso; i banner e i pulsanti disattivati nelle pagine merchant.
- `close_period`: un negozio approvato **in pausa** non entra nell'anteprima né nella piantumazione.
- Nessun segreto nei log (`caplog`); suite intera verde.

## Fuori scope
Pagamenti e abbonamenti (la pausa è manuale), scadenza automatica del periodo di prova, notifiche al merchant, messaggio ai
clienti di un negozio in pausa, personalizzazione del testo della carta di prova.

## Definition of Done
Un merchant appena registrato con Instagram collegato fa vedere ai clienti la carta di prova; dopo l'approvazione (via API admin
esistente `POST /api/merchant/{id}/approve`, la dashboard arriva nel ticket 13) la carta è vera; in pausa non accumula; docs e
planner aggiornati; commit «... (ticket 12)».
