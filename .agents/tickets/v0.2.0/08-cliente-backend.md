# 08 — Backend cliente: login OTP, join del negozio, wallet, proprietà della carta

## Obiettivo
Il cliente si iscrive con **email + OTP**, entra in un negozio dal **QR statico del negozio** e vede **tutte le sue carte** (wallet). La carta è accessibile solo al proprietario. Nessuna carta anonima, nessun WhatsApp.

## Contesto
Oggi `POST /api/get-card` crea una carta anonima (`merchant_id` nel body) e restituisce un link `wa.me`; `GET /card/{uuid}` e `GET /api/card/{uuid}` sono pubblici (capability URL). Il merchant scansiona il QR della **carta** (contiene l'URL `/card/{uuid}`; lo scanner lo trasforma in `/merchant/card/{uuid}/manage`): questo meccanismo resta, ma la pagina carta richiede ora il login del proprietario.

## Dipendenze
04, 06.

## Modifiche
1. **Core puro** in `app/services/customer_service.py` (nuovo): `normalize_email(email) -> str` (trim + lowercase, formato valido, altrimenti errore di dominio); `build_wallet(cards: list[WalletCardInput], pools: dict[int, PoolProgress]) -> list[WalletEntry]` che unisce carta + livello del pool del negozio, ordinando per negozio (nome).
2. **Shell** (stesso modulo):
   - `get_or_create_customer(session, identity) -> Customer` (idempotente per `auth_user_id`/email);
   - `join_merchant(session, customer, merchant_id) -> tuple[Card, bool]`: crea la carta se non esiste per `(merchant_id, customer_id)`, altrimenti ritorna quella esistente (`created=False`); merchant inesistente → `NotFoundError("Merchant non trovato")`;
   - `list_wallet(session, customer) -> list[WalletEntry]` (pool del mese corrente per ciascun negozio, con `compute_pool_progress` e soglie effettive).
3. **Auth cliente** (`app/routes/consumer/auth.py`, nuovo): `POST /api/customer/otp/request` (`{email}`) e `POST /api/customer/otp/verify` (`{email, code}`) → setta cookie `access_token` e crea il `Customer` al primo accesso; `GET /customer/logout`. `get_current_customer` (ticket 06) ora crea il customer se manca.
4. **Route** `app/routes/consumer/api.py`:
   - `POST /api/customer/join/{merchant_id}` → `{card_id, created}`;
   - `GET /api/customer/wallet` → lista carte con livello del negozio;
   - `GET /api/card/{id}` → **solo proprietario** (altrimenti 404, per non rivelare l'esistenza);
   - rimuovi `POST /api/get-card`, `create_whatsapp_link` e `app/core/utils/whatsapp_utils.py`.
5. **Pagine** (solo le route e il contesto Jinja; i template sono nel ticket 10): `GET /join/{merchant_id}` (pubblica), `GET /wallet` (cliente), `GET /card/{id}` (proprietario; non loggato → redirect a `/customer/login?next=...`), `GET /customer/login`. Rimuovi `/download_card`.
6. Il QR statico del negozio punta a `/join/{merchant_id}`: la pagina merchant per mostrarlo/scaricarlo è nel ticket 09.

## File coinvolti
`app/services/customer_service.py` (nuovo), `app/routes/consumer/api.py`, `app/routes/consumer/views.py`, `app/routes/consumer/auth.py` (nuovo), `app/main.py` (include router), `app/schemas/card.py`, `app/core/utils/whatsapp_utils.py` (rimosso), `tests/unit/test_customer_core.py`, `tests/test_customer.py`, `tests/test_views.py`, `tests/test_routes.py`.

## Test da superare
**Unit (senza DB):**
- `normalize_email("  Mario@Mail.IT ")` = `"mario@mail.it"`; `"mario"` → errore.
- `build_wallet`: due carte di negozi diversi producono due voci ordinate per nome negozio con il livello del rispettivo pool; lista vuota → `[]`; negozio senza pool → livello NONE.

**Integrazione (provider `dev`):**
- OTP request + verify con `"000000"` → cookie; con codice errato → 400/401 col messaggio italiano; al primo accesso nasce un `Customer`, al secondo no (nessun duplicato).
- `join` nuovo → carta creata, `created=True`; secondo `join` allo stesso negozio → stessa carta, `created=False`, una sola riga in DB; join su due negozi → due carte, stesso cliente; merchant inesistente → 404; senza login → 401.
- `wallet`: elenca solo le carte del cliente loggato (un altro cliente non vede le sue), con `level`/`points_to_next` del negozio coerenti con un pool preparato via movimenti.
- Proprietà: `GET /api/card/{id}` col proprietario → 200; con un altro cliente → 404; anonimo → 401; `/card/{id}` anonimo → redirect 303 a `/customer/login?next=/card/{id}`.
- La route `/api/get-card` e `/download_card` non esistono più (404).
- Il merchant può ancora aprire `/merchant/card/{id}/manage` per carte del proprio negozio e non per quelle altrui.
- Scenario end-to-end: cliente fa join → merchant (stesso DB) aggiunge 60 tree points → il wallet mostra pool 60 e saldo carta coerente con la conversione.

## Fuori scope
Template HTML e PWA (10), pagina QR negozio (09), collegamento di carte anonime preesistenti (non esistono dati di produzione da migrare: DB resettabile).

## Definition of Done
Test verdi, suite verde, nessun riferimento a WhatsApp nel codice, la carta non è più leggibile senza essere il proprietario.
