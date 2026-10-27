# 13 — Dashboard admin

## Obiettivo
Una pagina `/admin`, solo per il founder, per gestire i merchant: vedere chi si è iscritto, **approvare**, **mettere in pausa**,
**creare un profilo su richiesta** e **generare il link per scegliere/reimpostare la password**. Niente account admin e niente
modifiche allo schema per l'accesso.

## Contesto
Decisioni del 2026-10-27 (utente):
- Accesso con **una sola password in variabile d'ambiente**: si riusa `ADMIN_SECRET_KEY` (già obbligatoria, già usata dall'header
  `X-Admin-Key`, che sa solo il founder).
- Flusso: il merchant si iscrive (`/merchant/register`), contatta il founder su WhatsApp, il founder lo approva dalla dashboard.
  Può anche creare lui il profilo e mandare il link per scegliere la password.
- Pausa: periodo di prova finito o abbonamento non pagato (ticket 12 per gli effetti).
- Reimpostare una password dimenticata: dalla dashboard, senza OTP né email (ticket 11 per il meccanismo).
- Con ~100 merchant la gestione via dashboard è sufficiente: lista semplice, nessuna paginazione obbligatoria (limite 200 righe).

Stato attuale: `require_admin_key` (header) protegge `/api/merchant/*` (CRUD, approve) e lo smoke test lo usa: **resta com'è**.

## Dipendenze
11 (link password), 12 (stati e flag).

## Modifiche
1. **Accesso admin**:
   - `GET /admin/login` (form con un solo campo password) e `POST /admin/login`: confronto con `ADMIN_SECRET_KEY` in tempo
     costante (`hmac.compare_digest`); se giusto, cookie `admin_session` httpOnly (JWT firmato con `JWT_SECRET_KEY`, claim
     `role=admin`, scadenza **12 ore**, `SameSite=Strict`, `Secure` quando `ENVIRONMENT=production`); `GET /admin/logout`.
   - Dipendenza `require_admin_session`: cookie valido **oppure** header `X-Admin-Key` corretto (per curl e smoke test). Le pagine
     HTML senza sessione rimandano con 303 a `/admin/login`; le API rispondono 401.
   - Freno ai tentativi sbagliati (lo stesso del login merchant, ticket 11, contatore in memoria): 5 errori in 15 minuti → 429.
   - Nessuna password nei log; `ADMIN_SECRET_KEY` non compare mai in risposte, template o errori.
2. **Protezione CSRF**: le azioni che cambiano stato sono `POST` con `SameSite=Strict` e controllo dell'header `Origin` (o
   `Referer`) uguale al nostro host; senza, 403. Niente token CSRF a parte.
3. **Lista** `GET /admin` (HTML, JS vanilla + Tailwind come le altre pagine): tabella con nome attività, email, telefono,
   iscritto il, **stato del servizio** (In attesa / Attivo / In pausa), stato Instagram (non collegato / in attesa del DM /
   attivo / chiave non valida), numero di carte e punti del mese; ordinata dai più recenti; filtro per stato e ricerca per nome
   o email (lato client). Dati da `GET /admin/api/merchants` (JSON, mai chiavi, secret, hook id, token).
4. **Azioni per riga** (`POST /admin/api/merchants/{id}/...`, servizio in `merchant_service`, errori di dominio come sempre):
   - `approve` (imposta `is_approved`, toglie la pausa), `pause`, `resume`;
   - `password-link`: genera il link (ticket 11) e lo **mostra una sola volta** con pulsante «Copia»; non viene salvato in chiaro;
     un merchant senza credenziale ne ottiene una vuota; scadenza 7 giorni, indicata a video;
   - nessuna azione di eliminazione in dashboard (resta l'API admin esistente).
5. **Crea profilo** (`POST /admin/api/merchants`): nome attività (stessa validazione, ≤ 80), email (normalizzata, 409 se
   esiste), telefono facoltativo (stessa validazione +39), casella «approvato subito» (default **attiva**). Crea `Merchant` con
   `auth_user_id` della credenziale senza password e restituisce il link per scegliere la password.
6. **Sicurezza dei link**: la risposta con il link ha `Cache-Control: no-store`; nei log il percorso è mascherato
   (`/merchant/password/***`, ticket 11). Un link rigenerato invalida il precedente.
7. **Smoke test**: `/admin/login` 200 (HTML), `GET /admin/api/merchants` senza credenziali 401, con `X-Admin-Key` 200.
8. **Docs**: AGENTS.md (comandi/endpoint, nuova voce «Dashboard admin», mappa del codice), overview.md (endpoint, flusso di
   approvazione), deploy.md (come si accede, procedura «nuovo merchant su richiesta», «password dimenticata»), planner.

## File coinvolti
`app/core/dependencies.py` (`require_admin_session`), `app/core/security.py`, `app/routes/admin.py` (nuovo), `app/main.py`,
`app/services/merchant_service.py`, `app/schemas/merchant.py`, template `admin/login.html` e `admin/dashboard.html`,
`scripts/smoke_test_prod.py`, docs sopra.

## Test da superare
- Accesso: password giusta → cookie e redirect; sbagliata → 401 senza cookie; sesto tentativo → 429; cookie scaduto/manomesso →
  303 (HTML) o 401 (API); header `X-Admin-Key` valido accettato, errato 403/401; `Origin` estraneo su un `POST` → 403.
- Lista: ordine, filtri per stato, nessun segreto nel JSON (chiave Zernio, secret, `hook_id`, hash, token), un merchant con
  Instagram collegato mostra stato e conteggi giusti.
- Azioni: approva/pausa/riattiva cambiano i flag e di conseguenza il comportamento verificato nel ticket 12 (un esempio
  end-to-end); `approve` toglie la pausa; id inesistente → 404.
- Crea profilo: validazioni (nome, email, telefono), email duplicata 409, merchant creato con `auth_user_id`, link valido e usabile
  per scegliere la password e accedere; la stessa email non si può più registrare da `/merchant/register`.
- Password link: generato una sola volta, non presente in chiaro nel DB né nei log (`caplog`); rigenerato invalida il vecchio;
  dopo l'uso le sessioni del merchant sono invalidate.
- Suite intera verde.

## Fuori scope
Eliminazione e modifica dei dati del merchant dalla dashboard, soglie dei livelli per negozio (restano nell'API admin), invio
automatico del link per email o WhatsApp, più utenti admin, audit log, statistiche.

## Definition of Done
Dal browser, con la sola password admin: vedo gli iscritti con nome attività e telefono, approvo, metto in pausa e riattivo,
creo un profilo e genero un link per la password; docs e planner aggiornati; commit «... (ticket 13)».
