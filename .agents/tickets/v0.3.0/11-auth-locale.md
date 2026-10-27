# 11 — Autenticazione dei merchant con provider "locale" (password nel nostro DB)

## Obiettivo
Rendere possibile il login dei merchant **in produzione** senza Supabase: un provider `local` dietro la stessa interfaccia
`AuthProvider`, con email+password e hash della password nel nostro DB (Neon). Il merchant **si registra da solo** e sceglie la
password; se la dimentica la reimposta il founder dalla dashboard (ticket 13). Nessun OTP, nessuna email, nessun link a scadenza.

## Contesto
Decisioni del 2026-10-27 (utente):
- Il DB resta **Neon**; Supabase (Auth e/o DB) si valuta più avanti, oltre i ~100 profili.
- Questo **sostituisce** la decisione «niente password nel nostro DB» di v0.2.0: nel pilota l'hash sta in una tabella
  **separata** dai dati del negozio (come farebbe un provider esterno), così passare a Supabase significa cambiare provider ed
  eliminare la tabella.
- Oggi in produzione `dev` è rifiutato e `supabase` è uno stub: nessun merchant può accedere. Questo ticket lo sblocca.
- Flusso: il founder manda al merchant il link della pagina di registrazione `/merchant/register` (che resta aperta); il
  merchant si iscrive e poi viene avviato (approvato) dal founder (ticket 12-13). **Niente link di invito né link per la
  password**: se un profilo va reimpostato lo fa il founder con una password temporanea (sotto).

Stato attuale utile: `AuthProvider` (`app/core/auth.py`) ha `sign_up`, `sign_in_password`, `verify_token`; il token di sessione è
un JWT (`app/core/security.py`, claim `sub` = `auth_user_id`, `email`) nel cookie `access_token`; `get_current_merchant` cerca
il merchant per `auth_user_id`; `register_merchant` crea prima l'utente sul provider e poi la riga `Merchant`.

## Dipendenze
01-10.

## Modifiche
1. **Config**: `AUTH_PROVIDER: Literal["dev", "local", "supabase"]`. `local` è ammesso in produzione; `dev` resta rifiutato con
   `ENVIRONMENT=production`. Il default resta `dev` (locale/test).
2. **Tabella `AuthCredential`** (modelli, `create_all`): `user_id` str PK (uuid), `email` str unique/index (minuscola),
   `password_hash` str, `token_version` int (default 1), `created_at`. Nessuna FK verso `merchant`: il legame resta
   `Merchant.auth_user_id == AuthCredential.user_id`.
3. **Hash della password** nel core puro: `hashlib.scrypt` della **libreria standard** (nessuna nuova dipendenza), salt casuale
   per password, formato autodescrittivo `scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>`, verifica con `hmac.compare_digest`.
   Parametri come costanti documentate. Password: 8-128 caratteri (errore chiaro, mai il valore).
4. **`LocalAuthProvider`** (stesso contratto):
   - `sign_up(email, password)`: crea la credenziale, `AuthError` se l'email esiste già; ritorna `AuthIdentity`.
   - `sign_in_password`: stesso messaggio generico per email sconosciuta e password errata («Credenziali non valide»); si esegue
     comunque un hash fittizio se l'utente non esiste (tempi confrontabili).
   - Token = JWT con `sub`, `email` e claim `ver` = `token_version`; `verify_token` controlla firma/scadenza **e** che la
     credenziale esista e `ver` coincida (un reset invalida le sessioni aperte).
   - Metodi in più (contratto `PasswordAdminProvider`, che dashboard e impostazioni usano): `set_password(user_id, new_password)`
     (reset da parte dell'admin: nuovo hash e `token_version + 1`) e `change_password(user_id, current, new)` (verifica la
     vecchia password, poi come sopra; la sessione corrente va riemessa con il nuovo `ver`).
   - Accesso al DB tramite una **session factory iniettabile** (default: `Session(engine)` con import tardivo come
     `get_session`; i test iniettano quella di SQLite in-memory).
5. **Cambio password del merchant** (scelta mia, serve perché il reset dell'admin dà una password temporanea):
   `POST /api/merchant/me/password` con password attuale e nuova (400 se la nuova è troppo corta, 401 se l'attuale è errata) e
   un blocco «Cambia password» nelle impostazioni; riemette il cookie di sessione.
6. **Freno ai tentativi** su `POST /merchant/login`: contatore **in memoria** per email e per IP, 5 errori in 15 minuti → 429 con
   attesa (un solo processo su DO: sufficiente per il pilota). Funzione nel core puro (tempo passato come argomento); lo stesso
   meccanismo serve al login admin (ticket 13).
7. **Log**: nessuna password, hash o token in log, risposte o errori.
8. **Docs**: AGENTS.md (voce «Auth merchant nel pilota: provider locale», quella su Supabase ridotta a «più avanti»;
   Stack/Auth), overview.md (Autenticazione, endpoint, modello dati), roadmap, deploy.md (`AUTH_PROVIDER=local` in produzione;
   l'avviso sul primo deploy resta finché non sono chiusi anche i ticket 12 e 13), `.env.example`, planner.
9. **Scelte dell'implementazione non previste qui** (Dockerfile con `--proxy-headers`, `delete_user`, lifespan, cookie
   `Secure`, schemi senza vincoli): elenco nel planner, nota del ticket 11.

## File coinvolti
`app/core/config.py`, `app/core/auth.py`, `app/core/security.py`, `app/models/models.py`, `app/services/merchant_service.py`,
`app/routes/merchant/auth.py`, `app/routes/merchant/api.py`, `app/schemas/merchant.py`, template `merchant/settings.html`,
`.env.example`, docs sopra.

## Test da superare
- Core: hash e verifica (giusta, sbagliata, formato malformato → `False`, salt diverso a ogni hash), lunghezza password,
  contatore dei tentativi (soglia, finestra, azzeramento dopo il successo).
- Provider (SQLite in-memory): sign_up + login; email duplicata; messaggio identico per email sconosciuta e password errata;
  `verify_token` rifiuta token con `ver` vecchio, firma errata, utente cancellato; `set_password` invalida le sessioni aperte e
  vale la nuova password; `change_password` con password attuale errata rifiutata.
- Route: registrazione e login `local` end-to-end con cookie; 429 al sesto tentativo; `POST /api/merchant/me/password` (200,
  400, 401); dopo il cambio il cookie riemesso funziona e quello vecchio no.
- Nel DB non c'è nessuna password in chiaro; `caplog` senza password né hash.
- `AUTH_PROVIDER=local` con `ENVIRONMENT=production` parte; `dev` con `production` ancora rifiutato.
- Suite intera verde; i test esistenti con il provider `dev` restano invariati.

## Fuori scope
Recupero password via email, OTP, link di invito o di reimpostazione, Supabase, rotazione dei parametri di hash, captcha e blocco
condiviso tra processi. Il merchant creato dall'API admin senza `auth_user_id` (debito noto) resta com'è: il reset dalla
dashboard riguarda solo i merchant registrati.

## Definition of Done
Un merchant si registra con email+password in un ambiente con `ENVIRONMENT=production` e `AUTH_PROVIDER=local`, accede e può
cambiare la password; docs e planner aggiornati; commit «... (ticket 11)».
