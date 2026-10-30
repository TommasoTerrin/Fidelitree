# 09 — Rimozione del vecchio flusso cliente

## Obiettivo
Togliere tutto ciò che serviva a iscrizione email+OTP, wallet e QR `/join/{negozio}`: modello `Customer`,
`Card.customer_id`, route, template, schemi, parti cliente di `AuthProvider`, crud e test. Dopo questo ticket l'unico
modo per avere una carta è il DM Instagram.

## Contesto
Decisione del 2026-10-22: il vincolo "Iscrizione cliente obbligatoria, niente carte anonime" è **annullato**. Il cliente
non ha autenticazione e la carta è identificata da (negozio, indice cieco dell'IGSID). Non ci sono dati da migrare:
v0.2.x non è mai andata in produzione, e i DB locali si resettano.

## Dipendenze
06, 07, 08.

## Modifiche
1. **Modello**:
   - `Customer` rimosso;
   - da `Card` via `customer_id`, la relationship e la `UniqueConstraint(merchant_id, customer_id)`;
   - `Card.igsid_hash` diventa **obbligatorio** (`str`), resta `UNIQUE(merchant_id, igsid_hash)`;
   - `Card.link_token_hash` obbligatorio.
2. **Auth**:
   - da `AuthProvider`, `DevAuthProvider` e `SupabaseAuthProvider` via `request_otp`, `verify_otp` e `DEV_OTP_CODE`;
   - da `app/core/dependencies.py` via `get_current_customer` e `get_optional_customer`;
   - il cookie `access_token` resta per il merchant.
3. **Route**:
   - `app/routes/consumer/auth.py` rimosso;
   - in `consumer/api.py` via `POST /api/customer/join/{id}`, `GET /api/customer/wallet` e `GET /api/card/{id}`. Se il
     file resta vuoto si elimina e si toglie dal `main`;
   - in `consumer/views.py` via `/customer/login`, `/join/{id}`, `/wallet` e `/card/{id}`; restano `/c/{token}` e
     `/privacy`.
4. **Service e crud**:
   - in `customer_service.py` via tutto il flusso email/wallet; il modulo si elimina se resta vuoto;
   - `customer_crud.py` rimosso;
   - `card_crud.get_cards_by_customer` rimosso;
   - `card_crud.create_card` aggiornato, oppure rimosso se la creazione passa solo da `get_or_create_card`.
5. **Schemi**: via `app/schemas/customer.py`, `JoinResponse` e `WalletEntryResponse`; `CardResponse` resta (API
   merchant).
6. **Template**:
   - via `consumer/login.html`, `join.html` e `wallet.html`;
   - in `merchant/settings.html` via il blocco "QR del negozio" (`join_path`) e la relativa route;
   - in `partials/pwa.html` va tolto il riferimento alle pagine cliente.
7. **Test e fixture**:
   - in `conftest.py` la fixture `customer` sparisce;
   - `card` e `approved_merchants` creano carte con `igsid_hash` e `link_token_hash` (helper unico, per esempio
     `make_card(session, merchant, igsid="igsid-test-1")`);
   - `identity_for` e `login_as` restano solo per i merchant;
   - via `tests/test_customer.py`, `tests/unit/test_customer_core.py`, la parte OTP di `tests/unit/test_auth_dev.py` e
     le parti cliente di `test_views.py`, `test_auth_dependencies.py`, `test_crud.py` e `test_models.py`;
   - i test di scan, pool, close_period e conversione restano e passano con le nuove fixture.

## File coinvolti
`app/models/models.py`, `app/core/auth.py`, `app/core/dependencies.py`, `app/main.py`, `app/routes/consumer/*`,
`app/services/customer_service.py`, `app/services/db_crud/customer_crud.py`, `app/services/db_crud/card_crud.py`,
`app/schemas/card.py`, `app/schemas/customer.py`, `app/templates/consumer/*`, `app/templates/merchant/settings.html`,
`app/routes/merchant/views.py`, `tests/**`.

## Test da superare
- **Route rimosse** (404): `/customer/login`, `/join/1`, `/wallet`, `/card/<uuid>`, `POST /api/customer/otp/request`,
  `POST /api/customer/join/1`, `GET /api/customer/wallet`, `GET /api/card/<uuid>`.
- **Codice ripulito**: `grep` nel codice di `app/` non trova `Customer`, `customer_id`, `wallet`, `otp` né `/join`, a
  parte i commenti storici se servono.
- **Modello**: una `Card` senza `igsid_hash` → errore.
- **Flusso completo**: webhook "CARTA" → `/c/<token>` → scan del merchant +60 tree points → la pagina mostra la
  conversione e il pool aggiornati.
- **Eliminazione da parte del merchant**: `DELETE /api/merchant/card/{id}` cancella la carta (diritto all'oblio su
  richiesta al negozio); un nuovo "CARTA" dallo stesso IGSID crea una carta nuova a zero.
- **Avvio**: `python -c "import app.main"` ok; la suite intera è verde e il numero dei test è riportato nel riepilogo.

## Fuori scope
Seed e smoke test (10), documentazione (11).

## Definition of Done
Suite verde, nessun residuo del flusso email/wallet nel codice, l'app parte su un DB appena resettato.
