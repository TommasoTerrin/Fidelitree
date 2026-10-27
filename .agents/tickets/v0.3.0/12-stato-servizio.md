# 12 — Stato del servizio: approvazione, pausa e carta di prova

## Obiettivo
Il founder decide **chi usa davvero la carta**. Il merchant si iscrive da solo e viene **avviato** (approvato) dal founder; può
essere messo **in pausa** (prova finita, abbonamento non pagato).
- Finché non è approvato, il merchant può collegare il suo Instagram, ma i **nuovi** clienti ricevono un link a una **pagina con
  una carta fittizia di prova** (nessuna carta vera, nessun dato salvato).
- Se non è approvato o è in pausa, lo **scanner** non può **aggiungere** nulla (né tree points né cashback): solo togliere.
- Il cliente non viene mai messo in mezzo: nessun avviso sulle sue pagine, le carte esistenti si aprono come sempre.

I comandi per cambiare stato sono nel ticket 13 (dashboard).

## Contesto
Decisioni del 2026-10-27 (utente, confermate punto per punto). Oggi `is_approved` conta solo per la chiusura del pool
(`tree_service`); un merchant non approvato «lavora subito» (scan e punti). Cambia lo scanner e il webhook, **non** le pagine
del cliente.

Stati derivati (nessun nuovo enum, due flag):

| `is_approved` | `is_paused` | Stato | Webhook | Scanner (merchant) | Pagina carta del cliente |
|---|---|---|---|---|---|
| `False` | — | **In attesa** | cliente con carta già esistente → carta vera; **cliente nuovo → link a `/carta-di-prova`**, nessuna riga `Card` e nessun indice cieco salvato | solo togliere | come sempre |
| `True` | `False` | **Attivo** | come oggi | tutto | come sempre |
| `True` | `True` | **In pausa** | come oggi | solo togliere | come sempre |

Regole:
1. Un merchant **in attesa** non crea righe `Card`: il cliente nuovo vede la carta di prova; dopo l'approvazione riscrive `CARTA`
   e riceve quella vera. Se il cliente ha già una carta (negozio approvato e poi riportato «in attesa») il webhook manda il link
   vero: apre la carta reale, ma lo scanner non può aggiungere punti di nessun tipo.
2. Il solo avviso per «in attesa» e «in pausa» sta nello **scanner e nelle pagine del merchant** (banner con la spiegazione e
   pulsanti di aggiunta disattivati). Nessun avviso, banner o testo diverso nella pagina carta del cliente.
3. **La chiusura mensile non cambia**: conta solo `is_approved`. Un negozio in pausa partecipa con i punti già raccolti prima della
   pausa (in pausa non può aggiungerne altri; le rimozioni sul pool contano come oggi).
4. «Togliere» vale per cashback (`add-point` con delta negativo) e tree points (`add-tree-points` con delta negativo); la
   conversione automatica non scatta mai senza accrediti. Delta 0 resta com'è.
5. **Nessuno stato «sospeso dal merchant»** (deciso): se il merchant vuole fermare il servizio usa «Scollega» (le card non
   partono più) e chiede la pausa al founder.

## Dipendenze
06, 08, 11 (non strettamente, ma l'accesso in produzione serve per usarlo).

## Modifiche
1. **Modello**: `Merchant.created_at` (UTC, per la lista admin) e `Merchant.is_paused` bool (default `False`). Schema da
   resettare come sempre (`create_all`, niente Alembic).
2. **Core puro** (sezione di `merchant_service`): `ServiceState` (`pending`, `active`, `paused`), `service_state(is_approved,
   is_paused)`, `can_add_balance(state)` (solo `active`) e `can_remove_balance(state)` (sempre). Solleva `ForbiddenError` con
   messaggio chiaro («In attesa di approvazione: non puoi aggiungere punti», «Servizio in pausa: puoi solo togliere il saldo
   esistente») per un movimento non ammesso. Testabile senza DB.
3. **`card_service`**: `add_tree_points` e il cashback applicano il controllo (delta > 0 solo se attivo; delta < 0 sempre). Le
   route `/api/merchant/add-point` e `/add-tree-points` traducono in 403.
4. **Webhook** (`instagram_service`): se il merchant è in attesa, dopo trigger e `isFollower` si cerca la carta esistente
   **senza crearla**: se c'è, flusso normale con il suo link; se non c'è, si risponde con la stessa card (titolo = nome negozio,
   sottotitolo, bottone) il cui URL è `<PUBLIC_BASE_URL>/carta-di-prova`. Finestra 24 h, contatore invii,
   `AWAITING_TEST_DM` → `ACTIVE` ed esiti restano invariati (esito `sent`). In pausa: nessuna differenza.
5. **Pagine**:
   - `GET /carta-di-prova` (pubblica, senza dati, `noindex`, no-store): carta con design identico alla vera ma con valori
     fittizi e l'etichetta ben visibile «CARTA DI PROVA»; testo: il negozio sta provando Fidelitree e deve richiedere
     l'approvazione per attivare il servizio. Niente QR vero.
   - `GET /c/{token}`: **invariata** (nessun avviso, nessuno stato).
   - Pagine merchant (scanner, manage, impostazioni): banner di stato (in attesa/in pausa) e pulsanti di aggiunta disattivati
     con la spiegazione; la rimozione resta attiva.
6. **`tree_service.close_period`**: invariato.
7. **Seed e script**: `seed_db` crea i due merchant approvati e attivi (come oggi); lo smoke test controlla `/carta-di-prova` 200.
8. **Privacy**: la bozza di `/privacy` non cambia; nota nel ticket 14: un cliente nuovo di un negozio in attesa non lascia alcun
   dato.
9. **Docs**: AGENTS.md (voce «Stato del servizio» aggiornata, «Come funziona»: la carta vera la ricevono i nuovi clienti dei
   negozi approvati), overview.md (modello, flusso del webhook, endpoint `/carta-di-prova`), planner.

## File coinvolti
`app/models/models.py`, `app/services/merchant_service.py` o `card_service.py`, `app/services/instagram_service.py`,
`app/routes/consumer/views.py`, `app/routes/merchant/api.py`, template `consumer/test_card.html`, `merchant/*.html`,
`scripts/smoke_test_prod.py`, docs sopra.

## Test da superare
- Core: `service_state` per le 4 combinazioni di flag; permessi di aggiunta/rimozione per ogni stato; delta 0.
- Scan/cashback: in attesa e in pausa → 403 per delta positivo, ok per negativo (cashback **e** tree points), nessuna
  conversione; attivo → come prima (suite esistente verde).
- Webhook: merchant in attesa e cliente nuovo → una card con URL `/carta-di-prova` e **nessuna riga `Card`** (né indice cieco);
  `AWAITING_TEST_DM` diventa `ACTIVE`; contatore invii +1; invito a seguire invariato; finestra 24 h invariata. Cliente con carta
  già esistente su un negozio riportato «in attesa» → link vero. Dopo l'approvazione e un nuovo `CARTA` → carta vera. In pausa →
  come oggi.
- Pagine: `/carta-di-prova` (200, etichetta, nessun dato dinamico, no-store, nessun QR scansionabile); `/c/<token>` **identica**
  in ogni stato (nessun avviso); banner e pulsanti disattivati nelle pagine merchant.
- `close_period`: invariato (un negozio approvato in pausa entra come prima).
- Nessun segreto nei log (`caplog`); suite intera verde.

## Fuori scope
Pagamenti e abbonamenti (la pausa è manuale), scadenza automatica del periodo di prova, notifiche al merchant, avvisi al cliente,
stato «sospeso dal merchant», personalizzazione del testo della carta di prova.

## Definition of Done
Un merchant appena registrato con Instagram collegato fa vedere ai nuovi clienti la carta di prova; dopo l'approvazione (via API
admin esistente `POST /api/merchant/{id}/approve`, la dashboard arriva nel ticket 13) la carta è vera; in pausa lo scanner non
aggiunge nulla; docs e planner aggiornati; commit «... (ticket 12)».
