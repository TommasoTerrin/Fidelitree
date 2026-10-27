# 11 — Autenticazione dei merchant con provider "locale" (password nel nostro DB)

## Obiettivo
Rendere possibile il login dei merchant **in produzione** senza Supabase: un provider `local` dietro la stessa interfaccia
`AuthProvider`, con email+password, hash della password nel nostro DB (Neon) e **link monouso per impostare la password**
(creazione profilo da parte dell'admin e reset). Nessun OTP, nessun servizio di invio email: il link lo manda il founder a mano.

## Contesto
Decisioni del 2026-10-27 (utente):
- Il DB resta **Neon**; Supabase (Auth e/o DB) si valuta più avanti, oltre i ~100 profili. Con pochi merchant la gestione via
  dashboard admin (ticket 13) è sufficiente.
- Questo **sostituisce** la decisione «niente password nel nostro DB» di v0.2.0: nel pilota l'hash sta nel nostro DB, in una
  tabella **separata** dai dati del negozio (come farebbe un provider esterno), così passare a Supabase significa cambiare
  provider ed eliminare la tabella.
- Oggi in produzione `dev` è rifiutato e `supabase` è uno stub: nessun merchant può accedere. Questo ticket lo sblocca.
- Un merchant creato dall'admin senza `auth_user_id` oggi non può accedere né registrare la sua email (409, debito noto):
  con il link di impostazione password il problema sparisce.
- La registrazione libera `/merchant/register` **resta** (il merchant sceglie la password al momento dell'iscrizione).

Stato attuale utile: `AuthProvider` (`app/core/auth.py`) ha `sign_up`, `sign_in_password`, `verify_token`; il token di sessione è
un JWT (`app/core/security.py`, claim `sub` = `auth_user_id`, `email`) nel cookie `access_token`; `get_current_merchant` cerca
il merchant per `auth_user_id`; `register_merchant` crea prima l'utente sul provider e poi la riga `Merchant`.

## Dipendenze
01-10 (indipendente dai ticket 11-14 per il resto).

## Modifiche
1. **Config**: `AUTH_PROVIDER: Literal["dev", "local", "supabase"]`. `local` è ammesso in produzione; `dev` resta rifiutato con
   `ENVIRONMENT=production`. Il default resta `dev` (locale/test).
2. **Tabella `AuthCredential`** (modelli, `create_all`): `user_id` str PK (uuid), `email` str unique/index (minuscola),
   `password_hash` str opz. (vuoto = password non ancora scelta), `token_version` int (default 1),
   `reset_token_hash` str opz. unique/index (SHA-256 del token del link, mai il token), `reset_expires_at` datetime opz. (UTC),
   `created_at`. Nessuna FK verso `merchant`: il legame resta `Merchant.auth_user_id == AuthCredential.user_id`.
3. **Hash della password** nel core puro: `hashlib.scrypt` della **libreria standard** (nessuna nuova dipendenza), salt casuale
   per password, formato autodescrittivo `scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>`, verifica con `hmac.compare_digest`.
   Parametri come costanti documentate. Password: 8-128 caratteri (messaggio d'errore chiaro, mai il valore).
4. **`LocalAuthProvider`** (stesso contratto):
   - `sign_up(email, password)`: crea la credenziale, `AuthError` se l'email esiste già; ritorna `AuthIdentity`.
   - `sign_in_password`: stesso messaggio generico per email sconosciuta, password errata o password non ancora scelta
     («Credenziali non valide»); in tempo confrontabile (si esegue comunque un hash fittizio se l'utente non esiste).
   - Token = JWT con `sub`, `email` e claim `ver` = `token_version`; `verify_token` controlla firma/scadenza **e** che la
     credenziale esista e `ver` coincida (così un reset invalida le sessioni aperte).
   - Accesso al DB tramite una **session factory iniettabile** (default: `Session(engine)` con import tardivo come
     `get_session`; i test iniettano quella di SQLite in-memory).
5. **Link di impostazione password** (metodi del `LocalAuthProvider`, contratto separato `PasswordLinkProvider`, che il
   ticket 13 usa; l'app lo richiede solo quando serve):
   - `create_user_without_password(email) -> AuthIdentity` (profilo creato dall'admin).
   - `issue_password_link(user_id) -> token`: genera `secrets.token_urlsafe(32)`, salva solo l'hash e la scadenza (**7 giorni**,
     costante), invalida un eventuale link precedente; ritorna il token in chiaro **una volta sola**.
   - `set_password_with_token(token, new_password) -> AuthIdentity`: se hash corrispondente e non scaduto, imposta la password,
     **incrementa `token_version`** (sessioni vecchie invalidate), azzera token e scadenza. Token sconosciuto, scaduto o già
     usato → `NotFoundError` con lo stesso messaggio generico («Link non valido o scaduto»).
6. **Servizio** (`merchant_service`): `register_merchant` invariato nel flusso; compare in più `password_link_url(token)`
   (`<PUBLIC_BASE_URL>/merchant/password/<token>`, https richiesto come per la card).
7. **Pagina pubblica `GET /merchant/password/{token}`** (form: nuova password + conferma) e **`POST /merchant/password/{token}`**
   (imposta e rimanda a `/merchant/login` con un messaggio). Intestazioni `Cache-Control: no-store` e
   `Referrer-Policy: no-referrer` come la pagina carta; link non valido → 404 amichevole identico per sconosciuto/scaduto/usato.
   Nessun login automatico dopo l'impostazione.
8. **Freno ai tentativi** su `POST /merchant/login`: contatore **in memoria** per email e per IP, 5 errori in 15 minuti →
   429 con attesa (un solo processo su DO: sufficiente per il pilota). Funzione nel core puro (tempo passato come argomento).
9. **Log**: il filtro di `uvicorn.access` maschera anche `/merchant/password/<token>` (`mask_sensitive_paths`). Nessun token
   del link, password o hash in log, risposte o messaggi di errore.
10. **Docs**: AGENTS.md («Vincoli e trade-off»: nuova voce «Auth merchant: provider locale nel pilota», quella su Supabase
    ridotta a «più avanti»; Stack/Auth), overview.md (Autenticazione, endpoint, modello dati), roadmap («Collegare Supabase»:
    ora opzionale e successivo; resta valido il debito sul merchant creato dall'admin: **chiuso da questo ticket**),
    deploy.md (`AUTH_PROVIDER=local` in produzione, tolto l'avviso sull'accesso dei merchant), `.env.example`, planner.

## File coinvolti
`app/core/config.py`, `app/core/auth.py`, `app/core/security.py`, `app/core/logging_filters.py`, `app/models/models.py`,
`app/services/merchant_service.py`, `app/routes/merchant/auth.py`, `app/routes/merchant/views.py`, template
`merchant/password.html` e `merchant/password_invalid.html`, `.env.example`, docs sopra.

## Test da superare
- Core: hash e verifica (giusta, sbagliata, formato malformato → `False`, salt diverso a ogni hash), lunghezza password,
  contatore dei tentativi (soglia, finestra, azzeramento dopo il successo).
- Provider (SQLite in-memory): sign_up + login; email duplicata; password non ancora scelta non permette il login; messaggio
  identico per email sconosciuta e password errata; `verify_token` rifiuta token con `ver` vecchio, firma errata, utente
  cancellato.
- Link: emissione → impostazione → login con la nuova password; **secondo uso** rifiutato; link **scaduto** (tempo passato come
  argomento) rifiutato; un nuovo link invalida il precedente; dopo l'impostazione le sessioni aperte non valgono più (401);
  nel DB non c'è il token in chiaro.
- Route: GET/POST `/merchant/password/{token}` (200, 404 identico per i tre casi non validi, intestazioni no-store e
  no-referrer, password troppo corta → 400 senza il valore); login `local` end-to-end con cookie; 429 al sesto tentativo.
- Log: `caplog` e filtro — né token, né password, né hash; `/merchant/password/***` mascherato.
- `AUTH_PROVIDER=local` con `ENVIRONMENT=production` parte; `dev` con `production` ancora rifiutato.
- Suite intera verde; i test esistenti con il provider `dev` restano invariati.

## Fuori scope
Recupero password via email, OTP, cambio password dal pannello del merchant, Supabase, rotazione dei parametri di hash,
captcha e blocco per IP condiviso tra processi.

## Definition of Done
Un merchant si registra con email+password in un ambiente con `ENVIRONMENT=production` e `AUTH_PROVIDER=local`; un profilo
senza password riceve un link, lo usa una volta e accede; docs e planner aggiornati; commit «... (ticket 11)».
