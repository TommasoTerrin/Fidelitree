# 07 — Onboarding Instagram del merchant

## Obiettivo
Dalle impostazioni il merchant collega il suo Instagram in quattro passi:
1. incolla la **sua chiave Zernio**;
2. sceglie l'account Instagram collegato;
3. l'app configura **da sola** il webhook e la voce di menu persistente;
4. il merchant scrive "CARTA" da un altro profilo e diventa **attivo**.

Dallo stesso pannello vede lo stato (chiave mascherata, standby, menu, quota) e può scollegarsi.

## Contesto
Decisioni del 2026-10-22:
- **Pilota**: ogni merchant ha il proprio account Zernio gratuito (2 account, 10.000 invii al mese per team). La chiave
  si salva cifrata e non torna mai al frontend né nei log: si mostra solo `…1234`.
- **Validazione** con una chiamata reale: `GET /v1/accounts?platform=instagram&status=connected`. Non esiste `/v1/me`.
- **Webhook**: `POST /v1/webhooks/settings` con la chiave del merchant, URL `<PUBLIC_BASE_URL>/webhooks/zernio/<hook_id>`,
  un secret generato da noi (`secrets.token_urlsafe(32)`), `events=["message.received"]` e `accountIds=[account]`.
- **Menu persistente** "🌳 La mia carta" (postback `FIDELITREE_CARD`): si imposta **solo se il menu è vuoto**. Se il
  merchant ne ha già uno (es. ManyChat) non si tocca e il pannello lo segnala.
- **Standby / ManyChat**: non si può rilevare via API prima del primo messaggio. Il test DM finale lo fa emergere, e il
  pannello mostra l'avviso se `standby_detected_at` è recente.
- **Quota**: solo contatore e avviso. Barra `inviati/limite` e avviso dal `ZERNIO_SEND_WARN_PERCENT`.
- **Uscita**: "Scollega" rimuove il webhook da Zernio (tentativo singolo, l'errore si logga) e cancella chiave, secret
  e campi Zernio. Le carte restano. Se l'admin elimina il merchant, la riga sparisce con la chiave; il webhook rimasto
  su Zernio risponde 404 e Zernio lo disattiva da solo dopo 3 giorni.

## Dipendenze
05, 06.

## Modifiche
1. **`app/core/errors.py`**: `ExternalServiceError(DomainError)` → **502** nell'handler globale. Serve per Zernio non
   raggiungibile o per un errore inatteso durante la configurazione. Il messaggio in italiano non contiene dettagli
   della chiave.
2. **`app/services/merchant_service.py`** (o un nuovo `instagram_onboarding` in `instagram_service`, a scelta
   dell'agente purché coerente). Nella shell, tutte le chiamate a Zernio passano da `zernio_service`:
   - `save_zernio_key(session, http, merchant, api_key) -> list[ZernioAccount]`:
     - chiave vuota o con un prefisso diverso da `sk_`/`zrk_` → `InvalidInputError`, senza chiamare Zernio;
     - `AUTH` → `InvalidInputError("Chiave Zernio non valida")`;
     - nessun account Instagram → `InvalidInputError` con l'istruzione di collegarlo su Zernio;
     - se c'era già una configurazione, prima la scollega;
     - salva la chiave cifrata e `zernio_team_id` (da `get_team_identity`, ticket 05) e restituisce gli account.
   - `connect_instagram_account(session, http, merchant, account_id) -> Merchant`:
     - `PUBLIC_BASE_URL` deve iniziare con `https://`, altrimenti `InvalidInputError`;
     - l'account deve essere nell'elenco (`NotFoundError`) e non collegato a un altro negozio (`ConflictError`);
     - genera `webhook_hook_id` e secret, chiama `register_webhook`, poi `get_persistent_menu` / `set_persistent_menu`;
     - salva lo stato `AWAITING_TEST_DM`;
     - se `register_webhook` fallisce non salva nulla (né account né hook) → `ExternalServiceError`.
   - `disconnect_instagram(session, http, merchant) -> Merchant`.
   - Core puro `instagram_panel(merchant_fields, counter_sent, now) -> InstagramPanel`: stato, `@username`, chiave
     mascherata, avvisi (menu, standby negli ultimi 7 giorni, chiave non valida, quota), parola chiave da mostrare.
3. **`app/routes/merchant/api.py`** (cookie merchant; prima delle route `/{merchant_id}`):
   - `POST /api/merchant/instagram/key` `{api_key}` → `{accounts: [{id, username}]}`;
   - `GET /api/merchant/instagram/accounts` (riusa la chiave salvata);
   - `POST /api/merchant/instagram/account` `{account_id}` → pannello;
   - `GET /api/merchant/instagram` → pannello;
   - `DELETE /api/merchant/instagram` → pannello.

   Schemi Pydantic in `app/schemas/merchant.py`. **Nessuno schema di risposta contiene la chiave o il secret.**
4. **`app/templates/merchant/settings.html`** + `GET /merchant/settings`: sezione "Instagram" nello stile Tailwind
   esistente, con uno stato per volta.
   - **`NOT_CONNECTED`**: istruzioni brevi (crea un account Zernio gratuito, collega l'Instagram Business o Creator,
     crea una API key), campo chiave `type="password"` con `autocomplete="off"`, poi la scelta dell'account.
   - **`AWAITING_TEST_DM`**: "Scrivi CARTA al tuo negozio da un altro profilo Instagram", bottone "Aggiorna".
   - **`ACTIVE`**: stato attivo, `@username`, `…1234`, barra della quota, "Scollega".
   - **`KEY_INVALID`**: banner rosso e campo per una nuova chiave.

   Avvisi standby e menu dove servono. Il blocco del QR `/join` resta fino al ticket 09.

## File coinvolti
`app/core/errors.py`, `app/main.py` (handler 502), `app/services/merchant_service.py` / `instagram_service.py`,
`app/routes/merchant/api.py`, `app/routes/merchant/views.py`, `app/schemas/merchant.py`,
`app/templates/merchant/settings.html`, `tests/test_instagram_onboarding.py` (nuovo), `tests/unit/test_instagram_panel.py`
(nuovo), `tests/test_views.py`.

## Test da superare
(`MockTransport`, nessuna rete.)
- **Chiave valida** → 200 con gli account; nel DB la chiave è cifrata (diversa dal testo e decifrabile); la risposta
  **non** contiene la chiave.
- **Chiave errata** (Zernio 401) → 400 "Chiave Zernio non valida", nulla salvato. Chiave vuota o malformata → 400
  senza chiamate a Zernio.
- **Collegamento dell'account**:
  - un POST a `/v1/webhooks/settings` con URL `https://…/webhooks/zernio/<hook_id>`, il secret salvato (decifrato
    coincide) e `accountIds`;
  - menu vuoto → `PUT` del menu e `persistent_menu_set=True`;
  - menu esistente → nessun `PUT` e `persistent_menu_set=False`;
  - stato finale `AWAITING_TEST_DM`.
- **Errori del collegamento**:
  - account non in elenco → 404;
  - account già collegato a un altro merchant → 409;
  - `PUBLIC_BASE_URL` `http://` → 400;
  - errore Zernio sulla registrazione del webhook → 502 e nessun campo salvato.
- **Scollega**: `DELETE` del webhook su Zernio, campi Zernio a `None`, stato `NOT_CONNECTED`, carte intatte. Con
  Zernio in errore i campi si cancellano comunque, con log.
- **Pannello** (unit):
  - avviso standby se `standby_detected_at` è entro 7 giorni, e no oltre;
  - avviso quota dal 75%;
  - avviso menu solo con account collegato;
  - chiave mostrata come `…1234`.
- **Accesso**: senza cookie merchant → 401; un merchant non vede né modifica la configurazione di un altro.
- **Nessun segreto**: in tutte le risposte e in `caplog` mancano la chiave e il secret.
- **Pagina impostazioni**: mostra lo stato giusto per ognuno dei 4 stati.

## Collaudo manuale (a cura del founder)
Ambiente: server locale su SQLite usa-e-getta, `cloudflared tunnel --url http://127.0.0.1:8001`, `PUBLIC_BASE_URL` =
URL del tunnel (vedi deploy.md).
1. Registra un merchant, incolla la chiave Zernio, scegli l'account → su Zernio compare il webhook e su Instagram la
   voce di menu.
2. Dal profilo A scrivi "CARTA": arriva la card e il merchant diventa attivo. Tocca la voce di menu: arriva di nuovo la
   card.
3. Dal profilo B (non follower) scrivi "CARTA" e annota in zernio-notes.md:
   - il webhook arriva per un DM in Requests?
   - card o ripiego?
4. Facoltativo, con ManyChat collegato come app predefinita: il DM arriva in standby? Compare l'avviso nel pannello?
5. "Scollega" → il webhook sparisce da Zernio.

## Fuori scope
Pagina carta (08), modalità chiave unica e connect OAuth (roadmap), tabella eventi visibile nel pannello.

## Definition of Done
Suite verde, collaudo 1-3 eseguito ed esiti in zernio-notes.md.
