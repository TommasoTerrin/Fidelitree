# 13 — Dashboard admin

## Obiettivo
Una pagina `/admin`, solo per il founder, per gestire i merchant: vedere chi si è iscritto, **avviarlo** (approvare),
**metterlo in pausa** e riattivarlo, e **reimpostare la password** di chi la dimentica. Niente account admin e niente modifiche
allo schema per l'accesso.

## Contesto
Decisioni del 2026-10-27 (utente):
- Accesso con **una sola password in variabile d'ambiente**: si riusa `ADMIN_SECRET_KEY` (già obbligatoria, già usata
  dall'header `X-Admin-Key`, che sa solo il founder).
- Flusso: il founder manda al merchant il link di registrazione; il merchant si iscrive, contatta il founder su WhatsApp e il
  founder lo **avvia** dalla dashboard. **Il founder non crea profili** e non ci sono link di invito.
- Pausa: periodo di prova finito o abbonamento non pagato (ticket 12 per gli effetti).
- Password dimenticata: il founder la reimposta dalla dashboard (password temporanea da comunicare a mano, poi il merchant la
  cambia dalle impostazioni, ticket 11). Niente OTP né email.
- Con ~100 merchant la gestione via dashboard è sufficiente: lista semplice, nessuna paginazione obbligatoria (limite 200 righe).

Stato attuale: `require_admin_key` (header) protegge `/api/merchant/*` (CRUD, approve) e lo smoke test lo usa: **resta com'è**.

## Dipendenze
11 (reset della password), 12 (stati e flag).

## Modifiche
1. **Accesso admin**:
   - `GET /admin/login` (form con un solo campo password) e `POST /admin/login`: confronto con `ADMIN_SECRET_KEY` in tempo
     costante (`hmac.compare_digest`); se giusto, cookie `admin_session` httpOnly (JWT firmato con `JWT_SECRET_KEY`, claim
     `role=admin`, scadenza **12 ore**, `SameSite=Strict`, `Secure` quando `ENVIRONMENT=production`); `GET /admin/logout`.
   - Dipendenza `require_admin_session`: cookie valido **oppure** header `X-Admin-Key` corretto (per curl e smoke test). Le pagine
     HTML senza sessione rimandano con 303 a `/admin/login`; le API rispondono 401.
   - Freno ai tentativi sbagliati (lo stesso del login merchant, ticket 11): 5 errori in 15 minuti → 429.
   - `ADMIN_SECRET_KEY` non compare mai in log, risposte, template o errori.
2. **Protezione CSRF**: le azioni che cambiano stato sono `POST` con `SameSite=Strict` e controllo dell'header `Origin` (o
   `Referer`) uguale al nostro host; senza, 403. Niente token CSRF a parte.
3. **Lista** `GET /admin` (HTML, JS vanilla + Tailwind come le altre pagine): tabella con nome attività, email, telefono,
   iscritto il, **stato del servizio** (In attesa / Attivo / In pausa), stato Instagram (non collegato / in attesa del DM /
   attivo / chiave non valida), numero di carte e punti del mese; ordinata dai più recenti; filtro per stato e ricerca per nome
   o email (lato client). Dati da `GET /admin/api/merchants` (JSON, mai chiavi, secret, `hook_id`, hash).
4. **Azioni per riga** (`POST /admin/api/merchants/{id}/...`, servizio in `merchant_service`, errori di dominio come sempre):
   - `approve` (imposta `is_approved`, toglie la pausa), `pause`, `resume`;
   - `reset-password`: genera una **password temporanea** casuale (12 caratteri, alfabeto senza caratteri ambigui), la imposta con
     `set_password` (le sessioni aperte del merchant decadono) e la **mostra una sola volta** con pulsante «Copia»; non viene
     salvata in chiaro né loggata; 409 se il merchant non ha una credenziale (creato dall'API admin);
   - nessuna azione di eliminazione né di creazione in dashboard (restano nell'API admin).
5. **Smoke test**: `/admin/login` 200 (HTML), `GET /admin/api/merchants` senza credenziali 401, con `X-Admin-Key` 200.
6. **Docs**: AGENTS.md (comandi/endpoint, voce «Dashboard admin», mappa del codice), overview.md (endpoint, flusso di
   approvazione), deploy.md (come si accede, procedure «iscrizione di un nuovo merchant», «password dimenticata»,
   «prova finita / abbonamento non pagato»), planner.

## File coinvolti
`app/core/dependencies.py` (`require_admin_session`), `app/core/security.py`, `app/routes/admin.py` (nuovo), `app/main.py`,
`app/services/merchant_service.py`, `app/schemas/merchant.py`, template `admin/login.html` e `admin/dashboard.html`,
`scripts/smoke_test_prod.py`, docs sopra.

## Test da superare
- Accesso: password giusta → cookie e redirect; sbagliata → 401 senza cookie; sesto tentativo → 429; cookie scaduto/manomesso →
  303 (HTML) o 401 (API); header `X-Admin-Key` valido accettato, errato rifiutato; `Origin` estraneo su un `POST` → 403.
- Lista: ordine, filtri per stato, nessun segreto nel JSON (chiave Zernio, secret, `hook_id`, hash), un merchant con Instagram
  collegato mostra stato e conteggi giusti.
- Azioni: approva/pausa/riattiva cambiano i flag e di conseguenza il comportamento verificato nel ticket 12 (un esempio
  end-to-end); `approve` toglie la pausa; id inesistente → 404.
- Reset password: la password temporanea permette il login, la vecchia no, le sessioni aperte decadono; compare solo nella
  risposta (non nel DB in chiaro né in `caplog`); merchant senza credenziale → 409.
- Suite intera verde.

## Fuori scope
Creazione, eliminazione e modifica dei dati del merchant dalla dashboard, link di invito, soglie dei livelli per negozio (restano
nell'API admin), più utenti admin, audit log, statistiche.

## Definition of Done
Dal browser, con la sola password admin: vedo gli iscritti con nome attività e telefono, li avvio, li metto in pausa e li
riattivo, reimposto una password; docs e planner aggiornati; commit «... (ticket 13)».
