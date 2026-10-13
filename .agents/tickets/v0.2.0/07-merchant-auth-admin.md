# 07 — Auth merchant, approvazione e endpoint admin

## Obiettivo
Registrazione e login del merchant **per email** tramite l'interfaccia auth, flusso di **approvazione** da parte del founder e endpoint admin per gestire soglie e approvazione. Rimozione della chiave Ecologi dal flusso merchant.

## Contesto
Oggi `POST /merchant/register` valida la chiave Ecologi (anti-spam) e crea l'account con password Fernet; `POST /merchant/login` usa telefono+password. Nuova regola anti-abuso: il merchant **lavora subito** (può scansionare e dare punti) ma il suo pool conta per la piantumazione **solo se `is_approved`** (ticket 05). Il telefono è solo un contatto facoltativo.

## Dipendenze
02, 06.

## Modifiche
1. **Core puro** in `app/services/merchant_service.py` (nuovo, sezione core): `validate_registration(business_name, email, password, contact_phone) -> RegistrationData` (Pydantic: nome non vuoto trim, email con formato valido, password ≥ 8, telefono `+39…` solo se presente). Errori di dominio, non `HTTPException`.
2. **Shell** (stesso modulo): `register_merchant(session, provider, data) -> Merchant`: email già usata → errore 409; `provider.sign_up` → crea `Merchant(is_approved=False, type="free", auth_user_id=identity.user_id)`; ritorna anche il token per l'auto-login.
3. **Route** `app/routes/merchant/auth.py`:
   - `POST /merchant/register` (JSON: `business_name`, `email`, `password`, `contact_phone?`) → crea account, setta cookie, risponde `{"status":"success","merchant_id":...,"is_approved":false}`;
   - `POST /merchant/login` (form: `email`, `password`) → `provider.sign_in_password`, verifica che esista un `Merchant` per quell'identità (altrimenti 403), cookie, redirect 303 a `/merchant/scanner`;
   - `GET /merchant/logout` invariata.
   Rimuovi ogni uso di `ecologi_service` e `decrypt_key` qui.
4. **Impostazioni merchant** `PUT /api/merchant/me/settings`: campi `conversion_enabled`, `conversion_threshold` (≥1), `conversion_value_eur` (>0; l'API parla in **euro**, il service lo converte con `euro_to_cents` e salva `conversion_value_cents`; `GET /me` lo restituisce di nuovo in euro), `business_name`, `contact_phone`. **Non** modificabili dal merchant: `is_approved`, `type`, `*_threshold` livelli. `GET /api/merchant/me` risponde anche con `is_approved` e le **soglie effettive** (`resolve_thresholds`).
5. **Admin** (header `X-Admin-Key`): `PUT /api/merchant/{id}` accetta `is_approved`, `type`, `bronze_threshold`/`silver_threshold`/`gold_threshold` (anche `null` per tornare al default); gli override incoerenti (es. bronzo ≥ argento effettivo) → 400. Endpoint comodo `POST /api/merchant/{id}/approve`. Il CRUD admin di creazione crea merchant già approvato se passato `is_approved=true`. Rimuovi `create_test_merchant` basato su `MERCHANT_PASSWORD` (il seed lo sostituisce, ticket 11).
6. `MerchantResponse`/schemi aggiornati (niente password, niente chiavi); `merchant_crud` privo di cifratura.

## File coinvolti
`app/services/merchant_service.py` (nuovo), `app/services/db_crud/merchant_crud.py`, `app/routes/merchant/auth.py`, `app/routes/merchant/api.py`, `app/schemas/merchant.py`, `tests/unit/test_merchant_validation.py`, `tests/test_merchant_auth.py`, `tests/test_routes.py`, `tests/test_crud.py`.

## Test da superare
**Unit (senza DB):**
- `validate_registration`: email senza `@` → errore; password di 7 caratteri → errore; nome `"   "` → errore; telefono `"3331234567"` → errore, `None` → ok, `"+393331234567"` → ok; nome con spazi ai lati viene ripulito.

**Integrazione (provider `dev`, SQLite):**
- Registrazione valida: 200, merchant con `is_approved=False`, `auth_user_id` valorizzato, cookie `access_token` presente, nessuna password nel DB (nessuna colonna password).
- Stessa email due volte → 409 "Esiste già un account con questa email".
- Login con credenziali giuste → 303 a `/merchant/scanner` + cookie; password errata → 401; email sconosciuta → 401/404 coerente con il messaggio italiano esistente; identità valida ma non merchant (es. un cliente) → 403.
- Il merchant non approvato **può** accedere a `/merchant/scanner` e a `add-tree-points`.
- `PUT /api/merchant/me/settings`: `conversion_threshold=0` → 422/400; `conversion_value_eur=-1` → 422/400; valori validi salvati (`conversion_value_eur=2.5` → `conversion_value_cents=250` in DB e `2.5` in `GET /me`); tentativo di inviare `is_approved=true` o `bronze_threshold` viene ignorato/rifiutato e il DB non cambia.
- Admin: senza `X-Admin-Key` → 403; `approve` mette `is_approved=True`; `PUT` con `bronze_threshold=50` → `GET /me` mostra soglie effettive 50/300/600; `bronze_threshold=400` → 400; `null` ripristina il default.
- `grep -r ecologi app/routes/merchant` vuoto.

## Fuori scope
Pagine HTML (09), recupero password (lo gestirà Supabase), conferma email.

## Definition of Done
Test verdi, suite verde, flusso registrazione→login→scan funzionante con provider `dev`.
