# 10 — Frontend cliente e PWA

## Obiettivo
Pagine cliente per **login OTP**, **join del negozio**, **wallet** e **carta** con il livello collettivo del negozio, installabili come **PWA**. Stile coerente con `consumer/card.html` attuale.

## Contesto
`consumer/card.html` mostra una barra personale `tree_points/tree_threshold` e "Hai già piantato N alberi": va sostituita dalla gamification collettiva. `consumer/download.html` (download carta + WhatsApp) viene rimosso. `app/static/` è vuota (`.gitkeep`): verifica in `app/main.py` se è montata come static files e, se no, montala.

## Dipendenze
08.

## Modifiche
1. **`consumer/login.html`** (nuovo): due passaggi nella stessa pagina — email → "Invia codice" (`POST /api/customer/otp/request`) → campo codice a 6 cifre (`inputmode="numeric"`) → `verify` → redirect a `next` (default `/wallet`). Messaggi d'errore come toast. In ambiente `dev` mostra un promemoria "codice di sviluppo: 000000" **solo se** `AUTH_PROVIDER=dev`.
2. **`consumer/join.html`** (nuovo, `/join/{merchant_id}`): mostra nome del negozio e il messaggio "Entra nel progetto alberi di {negozio}". Se non loggato → bottone che porta al login con `next=/join/{id}`; se loggato → chiama `POST /api/customer/join/{id}` e porta alla carta. Negozio inesistente → pagina 404 amichevole.
3. **`consumer/wallet.html`** (nuovo, `/wallet`): elenco delle carte come tessere (stile card `rounded-[2rem]`): nome negozio, saldo tree points, cashback, **medaglia del livello del negozio** e mini-barra verso il livello successivo. Tap → `/card/{id}`. Stato vuoto: "Inquadra il QR di un negozio per aggiungere la tua prima carta". Link logout.
4. **`consumer/card.html`** (riscrittura del blocco tree points): 
   - **saldo personale** tree points + (se conversione attiva) barra verso la prossima conversione: "Ancora X punti per € Y di cashback";
   - **blocco "Il progetto del negozio"**: livello (🥉/🥈/🥇), punti del mese del pool, barra verso il livello successivo, frase *"Insieme questo mese stiamo piantando N alberi 🌳"*; a livello oro: *"Livello massimo raggiunto!"*;
   - cashback sempre visibile; QR della carta invariato; **rimuovi** "Hai già piantato N alberi" e il banner "Carta di Test" se non più pertinente (mantienilo per `merchant.type == 'test'`).
5. **PWA**: `app/static/manifest.webmanifest` (nome "Fidelitree", `start_url=/wallet`, `display=standalone`, colori in tinta con il verde dell'app, icone 192/512 in SVG o PNG), `app/static/sw.js` minimale (cache shell + strategia network-first, **nessuna cache delle risposte autenticate/API**), registrazione del service worker e `<link rel="manifest">`/meta `theme-color`/`apple-touch-icon` in un partial condiviso incluso da wallet/carta/login. Il service worker deve essere servito con scope `/` (route dedicata `GET /sw.js` se necessario).
6. Rimuovi `consumer/download.html`.

## File coinvolti
`app/templates/consumer/{login,join,wallet,card}.html`, `app/templates/consumer/download.html` (rimosso), `app/templates/partials/pwa.html` (nuovo), `app/static/*` (nuovi), `app/main.py` (mount static / route `sw.js`), `app/routes/consumer/views.py`, `tests/test_views.py`.

## Test da superare (render server-side)
- `GET /customer/login` → 200 con campo email; in `AUTH_PROVIDER=dev` contiene il promemoria codice, assente altrimenti.
- `GET /join/{id}` anonimo → 200, contiene il nome del negozio e il link al login con `next=/join/{id}`; id inesistente → 404.
- `GET /wallet` anonimo → redirect 303 al login; col cliente con 2 carte → 200, contiene entrambi i nomi negozio e i link `/card/{id}`; stato vuoto → contiene il messaggio di invito.
- `GET /card/{id}` (proprietario) con pool preparato a 150 punti (soglie 100/300/600): contiene il livello bronzo, "150", la dicitura sul prossimo livello e `points_to_next=150`; con pool a 700 contiene "Livello massimo"; **non** contiene "Hai già piantato".
- Con conversione attiva (soglia 50, saldo 20) la carta mostra "Ancora 30 punti"; con conversione disattivata quel testo è assente.
- `GET /static/manifest.webmanifest` → 200, JSON valido con `start_url="/wallet"` e `display="standalone"`; `GET /sw.js` → 200 con `Content-Type` JavaScript e header `Service-Worker-Allowed: /` se necessario; wallet e carta includono `rel="manifest"`.
- `GET /download_card` → 404.
- Verifica manuale su telefono (checklist ticket 11): installazione su schermata Home, apertura in standalone.

## Fuori scope
Notifiche push, funzionamento offline dei dati, personalizzazione grafica per negozio.

## Definition of Done
Test verdi, suite verde, stile coerente con le pagine esistenti, manifest e service worker validi (verificati con DevTools → Application).
