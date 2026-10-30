# 06 — Interfaccia di autenticazione e provider `dev`

## Obiettivo
Introdurre un'**interfaccia di autenticazione** indipendente dal fornitore (preparata per Supabase Auth) con un'implementazione `dev` per sviluppo e test. Sostituire il login per telefono+password Fernet con identità verificate da provider. **Il provider Supabase reale NON si implementa in questa versione.**

## Contesto
Oggi: `/merchant/login` confronta la password decifrata Fernet e crea un JWT nostro in cookie `access_token`; `get_current_merchant` legge il cookie. I clienti non si autenticano. Target: merchant con email+password, clienti con OTP email; entrambi gestiti da un provider esterno (Supabase) che ci restituisce un token da verificare. Il codice dell'app parla solo con l'interfaccia.

## Dipendenze
02.

## Modifiche
1. **`app/core/auth.py`** (nuovo):
   - `AuthIdentity(BaseModel)`: `user_id: str`, `email: str`.
   - `AuthProvider` (`typing.Protocol`): `sign_up(email, password) -> AuthIdentity`; `sign_in_password(email, password) -> str` (token); `request_otp(email) -> None`; `verify_otp(email, code) -> str` (token); `verify_token(token) -> AuthIdentity | None`. Errori: `AuthError(DomainError)` per credenziali/codice errati.
   - `DevAuthProvider`: **solo sviluppo/test**. Utenti in memoria (`dict`), `user_id` deterministico dall'email; password verificata se l'utente si è registrato con `sign_up`; OTP sempre `"000000"`; token = JWT firmato con `JWT_SECRET_KEY` (riusa `create_jwt_token` / `decode_jwt_token`, claim `sub=user_id`, `email`).
   - `SupabaseAuthProvider`: **stub** che solleva `NotImplementedError("Collegamento Supabase: rilascio successivo")` in ogni metodo, con docstring che elenca cosa servirà (URL progetto, anon key, verifica JWT con JWT secret Supabase).
   - `get_auth_provider()`: ritorna il provider scelto da `settings.AUTH_PROVIDER`; **solleva all'avvio** se `AUTH_PROVIDER="dev"` e `ENVIRONMENT="production"`.
2. **`app/core/dependencies.py`**:
   - `get_auth_identity(request)`: legge il token dal cookie `access_token` (o header `Authorization: Bearer`), lo verifica con il provider; 401 se assente/invalido.
   - `get_current_merchant` ora risolve l'identità → `Merchant` via `auth_user_id`; 401 se identità non valida, **403 "Account non registrato come esercente"** se non esiste il merchant.
   - `get_current_customer` analoga per `Customer` (se manca viene creato in ticket 08 al primo accesso: qui 403).
   - `require_admin_key` invariata.
3. **`app/core/security.py`**: rimuovi Fernet (`encrypt_key`/`decrypt_key`, `cipher_suite`); resta la gestione JWT usata dal provider `dev`. Rimuovi `ENCRYPTION_KEY` da `Settings`, `.env.example`, `deploy.md`; rimuovi `MERCHANT_PASSWORD` se non più usata (il seed la sostituisce nel ticket 11: coordina).
4. **`tests/conftest.py`**: fixture `auth_provider` (reset dello stato in memoria a ogni test), helper `login_as(client, identity)` che imposta il cookie; mantieni la fixture `auth_client`.

## File coinvolti
`app/core/auth.py` (nuovo), `app/core/dependencies.py`, `app/core/security.py`, `app/core/config.py`, `app/services/db_crud/merchant_crud.py` (via `encrypt_key`), `tests/conftest.py`, `tests/unit/test_auth_dev.py`, `tests/test_auth_dependencies.py`, `.env.example`, `.agents/workflows/deploy.md`.

## Test da superare
**Unit (`tests/unit/test_auth_dev.py`):**
- `sign_up("a@b.it","password1")` poi `sign_in_password` con password giusta → token; `verify_token(token)` ritorna identità con quella email e lo stesso `user_id`; password sbagliata → `AuthError`; utente inesistente → `AuthError`.
- `request_otp` + `verify_otp(email,"000000")` → token valido; codice `"123456"` → `AuthError`.
- `verify_token("spazzatura")` → `None`; token scaduto → `None`.
- Stesso `user_id` per la stessa email in momenti diversi; diverso per email diverse.
- `get_auth_provider()` con `AUTH_PROVIDER="dev"` e `ENVIRONMENT="production"` → solleva; con `"supabase"` ritorna lo stub e i suoi metodi sollevano `NotImplementedError`.

**Dipendenze (con route di prova):**
- Nessun cookie → 401; cookie invalido → 401; token valido ma nessun merchant collegato → 403 con il messaggio italiano; token valido di un merchant esistente → la dependency ritorna quel merchant.
- Il token da header `Authorization: Bearer` funziona come il cookie.
- `import app.security` non espone più `encrypt_key`/`decrypt_key`; l'app parte senza `ENCRYPTION_KEY` in env.

## Fuori scope
Pagine login (09/10), registrazione merchant (07), creazione Customer (08), Supabase reale.

## Definition of Done
Test verdi, suite verde, nessuna password salvata nel nostro DB, `grep -r "decrypt_key\|encrypt_key\|Fernet"` vuoto in `app/`.
