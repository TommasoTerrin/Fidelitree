# 08 — Pagina carta, QR, scan e PWA merchant

## Obiettivo
- **Pagina carta**: il link della card apre `/c/<token>`, una pagina web semplice con punti, cashback, livello del pool
  e QR. Non ha né manifest né service worker.
- **Scan**: il merchant inquadra il QR con lo scanner della sua PWA e gestisce la carta come oggi.
- **PWA**: passa alle sole pagine merchant.
- **Privacy**: nuova pagina `/privacy`, linkata in fondo alla pagina carta.
- **Log**: il token del link non compare nei log dell'app.

## Contesto
Decisioni del 2026-10-22:
- **Accesso alla carta**: il cliente non ha autenticazione e vede la carta solo tramite il link segreto. Il token si
  cerca per hash (`Card.link_token_hash`, confronto in tempo costante). Token sconosciuto o revocato → pagina 404
  amichevole: "Link non valido o scaduto: scrivi CARTA al negozio su Instagram per riceverne uno nuovo". La pagina non
  dice se la carta esiste.
- **QR della pagina carta**: contiene **solo l'id della carta** (UUID), diverso dal token. Fotografato al banco non
  apre la carta. Lo scanner lo accetta e porta a `/merchant/card/<id>/manage`, che resta protetta dal cookie merchant
  e dal controllo di appartenenza al negozio.
- **Log**: il token nel percorso finisce nei log di accesso. Un filtro su `uvicorn.access` lo sostituisce con
  `/c/***`, e lo stesso vale per `hook_id` (`/webhooks/zernio/***`). I log della piattaforma DigitalOcean restano fuori
  dal nostro controllo: trade-off accettato. Il "segreto dopo #" è in roadmap.
- **PWA solo merchant**:
  - `start_url` `/merchant/scanner`, `scope` `/merchant/`;
  - partial PWA incluso nelle pagine merchant (scanner, impostazioni, gestione carta, login);
  - service worker sempre servito da `/sw.js`, con lo scope ristretto e la stessa politica: solo la shell statica,
    niente pagine né API.
  - Le pagine HTML merchant (`/merchant/scanner`, `/merchant/settings`, `/merchant/card/{id}/manage`) **senza sessione
    valida** rimandano con un 303 a `/merchant/login`. Oggi rispondono 401 JSON, e la PWA installata con il cookie
    scaduto si aprirebbe su `{"detail": ...}`. Le API `/api/merchant/*` restano 401.
- **Privacy**: bozza dell'informativa scritta dall'agente, da far verificare al founder.
  - Contenuti: titolare = il negozio che ha dato la carta; Fidelitree = fornitore del servizio; dati = identificativo
    Instagram pseudonimizzato, punti, cashback, date; finalità = la carta fedeltà richiesta; destinatari = Zernio,
    Meta, hosting e database; conservazione finché il cliente non chiede la cancellazione al negozio o il negozio esce;
    diritti e reclamo al Garante.
  - Il testo dice chiaramente che è una bozza da verificare: commento nel template, non visibile all'utente.

## Dipendenze
03, 06.

## Modifiche
1. **`app/services/instagram_service.py`**, shell: `get_card_by_link_token(session, token) -> Card`. Calcola l'hash,
   cerca e confronta in tempo costante; altrimenti `NotFoundError`.
2. **`app/routes/consumer/views.py`**:
   - `GET /c/{token}` → `consumer/card.html` con carta, merchant, pool (`current_pool_progress`), conversione e
     `scan_code = str(card.id)`;
   - `NotFoundError` → template 404 amichevole con status 404;
   - `GET /privacy` → `consumer/privacy.html`;
   - la vecchia `/card/{id}` resta fino al ticket 09.
3. **`app/templates/consumer/card.html`**:
   - via il partial PWA e il link "← Le tue carte";
   - il QR codifica `scan_code`, non l'URL della pagina;
   - in fondo il link "Privacy";
   - stessi blocchi di oggi (saldo, conversione, pool).

   **`consumer/card_not_found.html`** e **`consumer/privacy.html`**: nuovi, stile Tailwind esistente.
4. **`app/templates/merchant/qr_scanner.html`**:
   - accetta un UUID: niente più trasformazione `/card/` → `/merchant/card/`;
   - qualsiasi altro contenuto mostra "QR non riconosciuto";
   - include il partial PWA.

   **Altre pagine merchant** (`settings`, `update_card`, `login_merchant`, `register_merchant`): includono il partial
   PWA.

   **`app/routes/merchant/views.py`**: dependency per le pagine HTML (es. `get_optional_merchant`). Senza merchant →
   `RedirectResponse("/merchant/login", 303)`. Stessa idea di `_login_redirect` dei clienti; nessun parametro `next`.
5. **`app/static/manifest.webmanifest`**:
   - `start_url: /merchant/scanner`, `scope: /merchant/`;
   - descrizione "Lo scanner Fidelitree del tuo negozio".

   **`app/main.py`**: `/sw.js` con `Service-Worker-Allowed: /merchant/`. **`partials/pwa.html`**: registrazione con
   `scope: '/merchant/'` e commento aggiornato ("pagine merchant").
6. **`app/core/logging_filters.py`** (nuovo, oppure in `crypto.py` se resta piccolo): filtro che maschera
   `/c/<token>` e `/webhooks/zernio/<hook_id>` nei record di `uvicorn.access`. Si installa all'avvio (lifespan), e
   quindi vale anche per `local_main.py` e per il `CMD` del Dockerfile.

## File coinvolti
`app/services/instagram_service.py`, `app/routes/consumer/views.py`, `app/templates/consumer/card.html`,
`app/templates/consumer/card_not_found.html` (nuovo), `app/templates/consumer/privacy.html` (nuovo),
`app/templates/merchant/*.html`, `app/templates/partials/pwa.html`, `app/static/manifest.webmanifest`, `app/main.py`,
`app/core/logging_filters.py` (nuovo), `tests/test_card_page.py` (nuovo), `tests/test_views.py`,
`tests/unit/test_logging_filters.py` (nuovo).

## Test da superare
- **Pagina carta**: `GET /c/<token>` di una carta creata dal webhook → 200 con il nome del negozio, i tree points, il
  cashback e il livello del pool.
  - Il QR contiene l'UUID della carta e **non** il token.
  - Nessun `rel="manifest"` né registrazione del service worker.
  - Link a `/privacy`.
- **Link revocato o sconosciuto**: token inventato → 404 con il testo amichevole. Dopo `link_version += 1` e il
  ricalcolo dell'hash, il vecchio token → 404 e il nuovo → 200.
- **Isolamento**: la pagina mostra solo la carta del token. Il token di un'altra carta mostra l'altra carta: nessuna
  confusione tra negozi.
- **Gestione dal QR**: `/merchant/card/<uuid>/manage` funziona per il merchant della carta e dà 404 per un altro
  merchant (comportamento attuale, verificato con una carta creata dal flusso Instagram).
- **Scan**: `add-tree-points` su una carta Instagram aggiorna saldo, registro e pool come prima.
- **Manifest e service worker**:
  - `start_url == "/merchant/scanner"` e `scope == "/merchant/"`;
  - le pagine merchant includono `rel="manifest"`;
  - `/sw.js` ha l'header `Service-Worker-Allowed: /merchant/`.
- **Redirect delle pagine merchant**: `/merchant/scanner` senza cookie (o con un token non valido) → 303 a
  `/merchant/login`; con il cookie → 200. `GET /api/merchant/me` senza cookie → resta 401.
- **`/privacy`**: 200, nomina Zernio e Meta e spiega come chiedere la cancellazione.
- **Filtro dei log** (unit): un record `GET /c/abc123 HTTP/1.1` diventa `/c/***`, e lo stesso per
  `/webhooks/zernio/xyz`; gli altri percorsi restano invariati.

## Fuori scope
Rimozione di `/card/{id}`, wallet e login cliente (09); segreto dopo `#` (roadmap).

## Definition of Done
Suite verde. Prova manuale:
- il link della card di prova (ticket 07) apre la pagina dal browser di Instagram;
- il merchant scansiona il QR dalla PWA e aggiunge punti;
- la PWA si installa dalle pagine merchant.
