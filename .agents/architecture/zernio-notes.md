# Note su Zernio e Meta per v0.3.0 (carta via DM Instagram)

> Raccolte il 2026-10-22 dalla documentazione ufficiale. Le pagine Zernio sono lette dai sorgenti `.mdx` di
> docs.zernio.com e dalla spec `https://zernio.com/openapi.yaml` (versione `1.331.2`); le pagine Meta via fetch
> di developers.facebook.com (citazioni brevi). "verificato = no" vuol dire che il dato viene solo da riassunti di
> ricerca o da fonti di terze parti; "non verificato" che la documentazione non lo dice: **non va dato per buono**,
> si chiude nel collaudo reale.

## Zernio: autenticazione, errori, rate limit

| Vincolo | Valore | Fonte | Verificato |
|---|---|---|---|
| Base URL | `https://zernio.com/api` (chiamate su `/v1/...`) | https://zernio.com/openapi.yaml (`servers`), https://docs.zernio.com/quickstart | sì |
| Base URL alternativo | `https://api.zernio.com/v1/...` compare **solo** in una voce del changelog (2026-10-22), non nella spec | https://docs.zernio.com/changelog#1792665421464 | sì (incoerenza: usiamo quello della spec, configurabile in env). **Confermato nel collaudo del 05 (2026-10-26)**: le chiamate su `https://zernio.com/api` funzionano |
| Autenticazione | `Authorization: Bearer <key>` | https://docs.zernio.com/quickstart | sì |
| Formato chiave | `sk_` + 64 caratteri esadecimali (67 in tutto); chiavi con gruppi disattivati: prefisso `zrk_` (lunghezza non documentata) | https://docs.zernio.com/quickstart, https://docs.zernio.com/multi-tenant | sì |
| Chiave `zrk_` con gruppi disattivati | 403 `insufficient_permissions` + `required_group`; gruppi rilevanti per noi: `messages`, `webhooks`, `accounts` | https://docs.zernio.com/multi-tenant | sì |
| Formato errore | JSON piatto `error` (testo, non stabile), `type`, `code`, `param`, `details`, `platform`, `platformError`; decidere su `type`/`code`, mai sul testo | https://docs.zernio.com/guides/error-handling | sì |
| 401 | `missing_credentials` (header assente), `invalid_credentials` (chiave sconosciuta, revocata o scaduta) | https://docs.zernio.com/messages/send-inbox-message | sì |
| Rate limit | 60 / 600 / 1.200 richieste al minuto per **team** in base agli account (0-2 account = 60/min), finestra scorrevole | https://docs.zernio.com/guides/rate-limits | sì |
| 429 | header `Retry-After`; corpo senza `code` stabile: si decide sullo status | https://docs.zernio.com/guides/rate-limits | sì |
| Validare una chiave | non esiste `/v1/me`; `GET /v1/accounts` (o `GET /v1/users`, `GET /v1/profiles`) risponde 200 con chiave valida | https://docs.zernio.com/accounts/list-accounts, https://docs.zernio.com/users/list-users | sì (assenza di `/v1/me` non verificata in modo esaustivo) |
| Elenco account collegati | `GET /v1/accounts?platform=instagram&status=connected` → `{"accounts":[{"_id","platform","username","isActive","profileId"}]}`; `page` e `limit` vanno insieme | https://docs.zernio.com/accounts/list-accounts, https://docs.zernio.com/multi-tenant | sì |
| Elenco profili | `GET /v1/profiles` (`externalId`, `name`, `limit`, `skip`) | https://docs.zernio.com/profiles/list-profiles | sì |
| Chiave limitata a un profilo | `POST /v1/api-keys` con `scope: "profiles"`, `profileIds`, `permission` | https://docs.zernio.com/multi-tenant | sì |

## Zernio: invio del messaggio

| Vincolo | Valore | Fonte | Verificato |
|---|---|---|---|
| Endpoint | `POST /v1/inbox/conversations/{conversationId}/messages`; `conversationId` opaco ("Format not to be assumed") | https://docs.zernio.com/messages/send-inbox-message | sì |
| Corpo | `accountId` obbligatorio; `message` (testo < 10.000 caratteri) | idem | sì |
| Generic template | `template: {type: "generic", elements: [...]}`, max 10 elementi; elemento: `title` obbligatorio, `subtitle`, `imageUrl`, `buttons` opzionali | idem | sì |
| `title` | max **80** caratteri | https://zernio.com/openapi.yaml (`sendInboxMessage`) | sì |
| `subtitle` | Zernio: nessun limite nella spec; Meta: **80** | spec Zernio; Meta (sotto) | sì per Meta, Zernio non dichiara |
| Bottoni per elemento | max **3**, `type` ∈ `url`, `postback`; `title` max **20** caratteri | https://zernio.com/openapi.yaml | sì |
| URL del bottone solo https? | non dichiarato da Zernio (`url: string`) né da Meta per Instagram (https obbligatorio solo con `messenger_extensions`) | spec Zernio; https://developers.facebook.com/documentation/business-messaging/messenger-platform/send-messages/buttons/url | non verificato (noi imponiamo https comunque) |
| `imageUrl` | opzionale; `imageAspectRatio` è solo Facebook, Instagram lo rifiuta (400) | https://docs.zernio.com/messages/send-inbox-message | sì |
| `template` + `buttons` di primo livello | mutuamente esclusivi: entrambi → 400 | idem | sì |
| `message` + `template` nella stessa richiesta | non documentato | — | non verificato (non lo facciamo: un solo invio, solo `template`) |
| Alternativa "button template" | `message` (≤ **640** caratteri) + `buttons` (max 3) → una bolla con bottoni | https://docs.zernio.com/platforms/instagram/inbox | sì |
| Card su Instagram desktop | il generic template **si vede solo nell'app mobile**: "Meta does not support the generic template on Instagram desktop web" | https://docs.zernio.com/platforms/instagram/inbox; Meta: "This feature is currently not available in the web version." https://developers.facebook.com/docs/messenger-platform/instagram/features/generic-template | sì |
| Fuori finestra 24h | `messagingType: "MESSAGE_TAG"` + `messageTag: "HUMAN_AGENT"` (unico tag su Instagram) | https://docs.zernio.com/platforms/instagram/inbox | sì (non lo usiamo in v0.3.0) |
| Risposta 200 | `{success, warnings?, data: {messageId, conversationId, ...}}` | https://docs.zernio.com/messages/send-inbox-message | sì |
| 400 | validazione o rifiuto Meta: `type` `platform_error`, `code` `platform_api_error`, `platformError{code, subcode, fbtraceId, type}` | idem | sì |
| 403 | addon inbox mancante **o** invio fuori finestra rifiutato da Meta; quota esaurita: `code` `message_allowance_exceeded` | idem; https://docs.zernio.com/pricing/messages | sì |
| 409 | `Idempotency-Key` ancora in lavorazione, oppure `not_thread_owner` (subcode Meta `2534037`, conversazione di un'altra app) | https://docs.zernio.com/messages/send-inbox-message | sì |
| 500 | Zernio **non ritenta** l'invio; ritentare può consegnare due volte | idem | sì |
| Idempotenza dell'invio | header `Idempotency-Key`, valido 24 h; replay con `Idempotent-Replayed: true`; su 5xx/timeout la chiave viene rilasciata | idem | sì |
| Card rifiutata ai non follower | Meta `2`/`1545133` rifiuta bottoni e card a chi non segue l'account: documentato **solo per le private reply ai commenti** | https://docs.zernio.com/changelog#1788345066805 | **non verificato per i DM** (il profilo del founder segue il negozio: card consegnata). Da chiudere nel collaudo finale, ticket 14 (vedi sotto). Il codice non dipende dall'esito: chi non segue riceve comunque solo l'invito a seguire, il ripiego «testo con il link» resta come rete di sicurezza |

## Zernio: webhook

| Vincolo | Valore | Fonte | Verificato |
|---|---|---|---|
| Registrazione | `POST /v1/webhooks/settings`: `name` (1-50), `url`, `events` obbligatori; `secret`, `isActive`, `customHeaders`, `profileIds`, `accountIds` opzionali | https://docs.zernio.com/webhooks/create-webhook-settings | sì |
| Ambito | registrato con la **chiave** e salvato per team ("per user" in una pagina, "per team" in un'altra), max 50 endpoint; di default riceve gli eventi di tutti i profili, si restringe con `profileIds`/`accountIds` | idem; https://docs.zernio.com/multi-tenant | sì (formulazioni discordanti) |
| Secret | **lo sceglie chi registra**: "Zernio never generates one for you"; senza secret le consegne **non sono firmate** | https://docs.zernio.com/webhooks | sì |
| Firma | header `X-Zernio-Signature` (alias legacy `X-Late-Signature`) = HMAC-SHA256 esadecimale minuscolo del **corpo grezzo** con il secret; confronto `hmac.compare_digest`; firma errata → non elaborare | idem | sì |
| Header | `X-Zernio-Event`, `X-Zernio-Event-Id` (UUID, **uguale a ogni retry**, = `payload.id`), `User-Agent: Zernio-Webhooks/1.0` | idem | sì |
| Tempo di risposta | qualsiasi 2xx **entro 5 secondi** | idem | sì |
| Retry | 7 tentativi in tutto: dopo 10 s, 1 m 40 s, 16 m 40 s, 2 h 46 m 40 s, 24 h, 24 h; poi dead-letter (rinvio manuale) | idem | sì |
| Disattivazione automatica | dopo 3 giorni senza consegne riuscite e 20 fallimenti consecutivi (o 3 giorni di fallimenti); si riattiva con `isActive: true` | idem | sì |
| Consegna | at-least-once: dedup su `X-Zernio-Event-Id` | idem | sì |
| Eventi inbox | `message.received`, `message.sent`, `conversation.started`, `conversation.control_changed`, `message.failed`, `comment.received`, ... | https://docs.zernio.com/webhooks/inbox | sì |
| `message.received`: campi | `id`, `event`, `message`, `conversation`, `account`, `metadata`, `timestamp`, `profiles`, `test` | idem; spec `WebhookPayloadMessage` | sì |
| `message` | `id`, `conversationId`, `platform`, `direction` (`incoming`/`outgoing`), `text` (nullable), `attachments`, `sender`, `sentAt` | https://docs.zernio.com/webhooks/inbox | sì |
| `message.sender` | `id` (identificativo di piattaforma = IGSID), `name`, `username`, `picture`, `instagramProfile{isFollower, ...}` | idem | sì (`id` = IGSID dedotto da `conversation.platformConversationId`) |
| `conversation` | `id` (**da usare per l'invio**), `platformConversationId` (= IGSID su Instagram), `participantUsername`, `status` | spec `InboxWebhookConversation`; https://docs.zernio.com/webhooks/inbox | sì |
| `account` | `id` = `accountId`, `profileId` (opz.), `platform`, `username` | spec `InboxWebhookAccount` | sì |
| `metadata.standby` | `true` se un'altra app possiede il thread: l'invio riceve 409 `not_thread_owner`; con Instagram Login Zernio non può `take`/`request` | https://docs.zernio.com/webhooks/inbox | sì |
| Storico precedente al collegamento | non genera `message.received` | idem | sì |
| Test del webhook | `POST /v1/webhooks/test` con `webhookId` (evento `webhook.test`, una volta, senza retry) | https://docs.zernio.com/webhooks | sì |

## Zernio: Instagram e collegamento

| Vincolo | Valore | Fonte | Verificato |
|---|---|---|---|
| Tipo di account | Business o Creator | https://docs.zernio.com/platforms/instagram | sì |
| Pagina Facebook | non serve con `loginMethod=instagram_login` (default) | idem | sì |
| Connect (futura chiave unica) | `GET /v1/connect/instagram?profileId=...&redirect_url=...` → `{authUrl, state}`; 402 `free_tier_exceeded` oltre gli account gratuiti | https://docs.zernio.com/connect/get-connect-url, https://docs.zernio.com/multi-tenant | sì |
| Message request | DM di non follower → cartella Requests; "Meta has no accept call: replying moves a thread into the inbox"; esiste comunque `POST /v1/inbox/conversations/{id}/accept` (`accountId`, `message`) | https://docs.zernio.com/platforms/instagram/inbox, https://docs.zernio.com/messages/accept-conversation-request | sì |
| Il webhook arriva per i DM in Requests? | Meta: notifica per ogni messaggio, senza eccezioni dichiarate; Zernio non ne parla | https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api | **non verificato**: da chiudere nel collaudo finale, ticket 14 (vedi sotto) |
| Limiti di DM per account | nessuno documentato | https://docs.zernio.com/guides/rate-limits | non verificato |

## Zernio: prezzi

| Vincolo | Valore | Fonte | Verificato |
|---|---|---|---|
| Account gratuiti | 1-2 account senza carta di credito; profili illimitati | https://docs.zernio.com/pricing, https://zernio.com/pricing | sì |
| Invii gratuiti | primi **10.000 messaggi in uscita al mese**, poi $1 ogni 10.000; contati **per team** (non per account); reset alle 00:00 UTC del giorno 1 | https://docs.zernio.com/pricing/messages | sì |
| Senza carta oltre la soglia | email al proprietario a **7.500**; l'invio che supererebbe 10.000 fallisce con **403 `message_allowance_exceeded`** fino al mese dopo | idem; https://zernio.com/pricing | sì |
| Con carta | nessuno stop, si paga l'eccedenza | https://docs.zernio.com/pricing/messages | sì |
| Cosa non conta | messaggi ricevuti, invii falliti, letture | idem | sì |
| Contatore via API | "No endpoint reports it today" | idem | sì |
| Inbox nel piano gratuito | sì | https://docs.zernio.com/pricing | sì |

## Meta (Instagram Messaging)

| Vincolo | Valore | Fonte | Verificato |
|---|---|---|---|
| Finestra standard | 24 ore dall'ultimo messaggio dell'utente | https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api | sì |
| `HUMAN_AGENT` | finestra separata di 7 giorni per risposte **manuali** | idem; https://developers.facebook.com/documentation/business-messaging/messenger-platform/policy | sì |
| `HUMAN_AGENT` richiede App Review / vietato agli automatismi | solo da riassunti e fonti terze | — | no |
| Bot automatici | "must respond to user input within 30 seconds" | https://developers.facebook.com/documentation/business-messaging/messenger-platform/policy | sì |
| Generic template | `title` max 80, `subtitle` max 80, max 3 bottoni per elemento (`web_url`, `postback`), max 10 elementi, immagine opzionale; non disponibile sul web | https://developers.facebook.com/docs/messenger-platform/instagram/features/generic-template | sì |
| Titolo del bottone | max 20 caratteri | https://developers.facebook.com/documentation/business-messaging/messenger-platform/send-messages/buttons/url | sì (pagina Messenger; coincide con la spec Zernio) |
| Handover Protocol | non più supportato su Instagram, sostituito da Conversation Routing | https://developers.facebook.com/documentation/business-messaging/instagram-messaging/features/conversation-routing | sì |
| Più app collegate, nessuna di default | tutte ricevono i webhook e possono rispondere | idem | sì |
| Thread con app di default | solo l'app di default invia; le altre ricevono in **standby** e non devono rispondere (detto esplicitamente per Meta Business AI) | idem | sì per Meta AI; con ManyChat come app di default **non verificato** |
| Controllo del thread | scade dopo 24 h di inattività | idem | sì |
| Requests | i nuovi DM di non follower finiscono in Requests; passano in Generale quando l'app risponde; dopo 30 giorni di inattività spariscono dall'API | https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api | sì |

## Zernio: endpoint di configurazione usati dal client (spec 1.331.x, letta il 2026-10-23, ticket 05)

| Vincolo | Valore | Fonte | Verificato |
|---|---|---|---|
| Elimina webhook | `DELETE /v1/webhooks/settings?webhookId=<id>` (id di 24 caratteri esadecimali; alias deprecato `id`; un parametro sconosciuto → 400); risposta `{success}` | https://zernio.com/openapi.yaml (`deleteWebhookSettings`) | sì |
| Crea webhook, risposta | `{success, webhook: {_id, name, url, events, isActive, ...}}`: l'id è `webhook._id` | idem (`createWebhookSettings`) | sì |
| Menu persistente | `GET/PUT/DELETE /v1/accounts/{accountId}/messenger-menu`; **PUT** (non POST) con `{"persistent_menu": [...]}` in formato Meta (`locale`, `call_to_actions[{type, title, payload}]`); GET → `{data: [...]}`; max 3 voci di primo livello, max 5 annidate | idem (`setMessengerMenu`); formato: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api/persistent-menu | sì |
| Limite del titolo della voce di menu | **non dichiarato** né da Zernio né dalla pagina Meta per Instagram; la nostra voce "🌳 La mia carta" è di 15 caratteri | idem | **non verificato** (nessun limite imposto dal client) |
| Menu su Facebook | richiede un Get Started button; per Instagram non è citato | idem | sì (solo Facebook) |
| Elenco conversazioni | `GET /v1/inbox/conversations`: `accountId`, `platform`, `status` (`active`/`archived`), `folder` (`inbox`/`requests`), `limit` (max 100), `cursor`; risposta `{data: [{id, accountId, accountUsername, participantId, participantName, lastMessage, updatedTime, status, folder?, instagramProfile{isFollower,...}}], pagination, meta}` | idem (`listInboxConversations`) | sì |
| **`folder=requests` con Instagram Login** | **non supportato**: "Instagram accounts connected with Instagram Login answer PLATFORM_LIMITATION (Meta does not expose the folder on that login)" → 400. Serve Facebook Login. Lo script (`conversations --folder requests`) lo mostra come errore `bad_request` | idem | sì (da spec; da riconfermare nel collaudo) |
| Identità del team | **nessun campo**: `GET /v1/users` → `{currentUserId, users[{_id, name, email, role, isRoot, profileAccess}]}` identifica l'utente, non il team (`teamId` esiste solo nelle impostazioni Slack). `isRoot`/`role: owner` indicherebbe il titolare, ma la semantica non è documentata. `get_team_identity` restituisce quindi `None` e la quota ripiega su `account:<id>` | idem (`listUsers`) | sì (assenza); `isRoot` come team: non verificato |

## Cosa ne segue per il progetto (proposte del 2026-10-22: le decisioni prese sono in AGENTS.md)

1. **Secret del webhook**: lo scegliamo noi alla registrazione. Senza secret non c'è firma, quindi va sempre impostato. Resta da decidere se è per merchant o globale.
2. **Tempi**: Zernio vuole risposta entro 5 s, Meta entro 30 s (policy). Proposta: risposta sincrona nel webhook, timeout verso Zernio di circa 3 s. **Misurato il 2026-10-26: l'invio della card dura 1,2-3,1 s (il 3,1 s a connessione nuova, come fa il webhook); con 3 s scadeva, quindi il timeout è 4 s.**
3. **Dedup e retry**:
   - dedup su `X-Zernio-Event-Id`;
   - la finestra dei retry Zernio dura circa 51 h, quindi gli id degli eventi vanno conservati almeno 3 giorni;
   - su 5xx o timeout Zernio rilascia l'`Idempotency-Key`, quindi ritentare può mandare la card due volte. Proposta: nessun nuovo tentativo e log.
4. **Filtro su `direction == "incoming"`**, così non si risponde ai propri messaggi.
5. **Per l'invio si usa `conversation.id`**, un handle interno di Zernio che probabilmente cambia se l'account passa a un altro team. Per trovare la carta proposta: l'IGSID (`message.sender.id`), che è stabile.
6. **Limiti da verificare nel core**: `title` ≤ 80, `subtitle` ≤ 80, al massimo 3 bottoni (ne usiamo 1), titolo del bottone ≤ 20. In più, scelta nostra: URL solo https.
7. **Quota**:
   - 10.000 invii al mese **per team Zernio**: oggi il team del merchant, domani quello di piattaforma;
   - Zernio non espone un contatore, quindi il nostro conta solo i nostri invii;
   - il 403 `message_allowance_exceeded` va gestito comunque.
8. **Standby**: con `metadata.standby = true` un invio riceve 409 `not_thread_owner`.
9. **Desktop**: la card non si vede su Instagram web. Rischio da accettare o mitigare.
10. **Da chiudere nel collaudo reale**:
    - ~~quale base URL usare?~~ chiuso nel collaudo del 05: `https://zernio.com/api`;
    - arriva il webhook per i DM in Requests? → collaudo finale (ticket 14);
    - la card viene accettata da chi non segue l'account? → collaudo finale (ticket 14);
    - come si comporta con ManyChat come app di default? → collaudo finale (ticket 14).

## Verificato nel collaudo del ticket 05 (2026-10-26, `zernio_check` con la chiave del founder)

| Cosa | Esito |
|---|---|
| Base URL `https://zernio.com/api` | funziona (`accounts` e `conversations` rispondono) |
| `send-card` verso la conversazione del founder (profilo che **segue** il negozio) | card consegnata e corretta su mobile (titolo, sottotitolo, bottone «Apri la carta») |
| `conversations`: ordine e date | in ritardo (la conversazione del founder risultava del giorno prima): per trovare la conversazione si legge il mittente dei messaggi, non ci si fida dell'ordine |
| `conversations --folder requests` | 400 `PLATFORM_LIMITATION` con Instagram Login, come dichiarato dalla spec (riga «`folder=requests`» sopra: ora verificato) |
| Card a un **non follower** (passo 3 del collaudo) | rimandato: nessun profilo non follower disponibile → collaudo finale |

## Verificato nel collaudo del ticket 07 (2026-10-26, webhook reale via ngrok, account `@oroscopo.kittysincula`)

| Cosa | Esito |
|---|---|
| Onboarding da pannello (chiave, scelta account, webhook registrato, menu vuoto → voce impostata) | funziona; stato `AWAITING_TEST_DM` |
| `message.received` da un profilo **che segue** il negozio | il webhook arriva e firma/dedup funzionano; card consegnata; stato → `ACTIVE`; contatore invii a 1 |
| Ritardo tra DM (`sentAt`) e webhook | ~11,5 s (14:39:57,7 → 14:40:09,2 UTC) |
| Durata della sola chiamata di invio card (10 prove) | 1,2-3,1 s; il massimo a connessione nuova (il webhook crea un client per richiesta). Con timeout 3 s scadeva pur consegnando la card → `SEND_TIMEOUT` portato a **4 s** |
| Ritardo percepito di ~30 s | non è l'invio: webhook ~11,5 s + consegna Instagram/telefono (il resto non è stato scomposto) |
| `/c/<token>` | 404 fino al ticket 08 (atteso) |
| Card a un **non follower** (rifiuto Meta 2/1545133 o consegna) | **non verificato**: manca un profilo non follower → collaudo finale |
| Webhook per DM in **Requests** | **non verificato** (stesso motivo) → collaudo finale |
| `isFollower: null` nel payload reale | **non verificato** → collaudo finale |
| ManyChat come app predefinita / standby | **non verificato** → collaudo finale |
| Tocco della voce di menu «🌳 La mia carta» → card | **non verificato** → collaudo finale |
| «Scollega» da pannello → webhook rimosso da Zernio | **non verificato** (coperto solo dai test automatici) → collaudo finale |

## Collaudo finale del ticket 14 (esiti del founder, 2026-10-28)

Procedura con i comandi: sezione «v0.3.0» di [collaudo.md](../workflows/collaudo.md) (fino al 2026-10-30 stava in `deploy.md`). Per ogni riga si scrive l'esito
e, dove serve, i numeri misurati; nessun dato personale, token, IGSID o chiave.

### Non confermato o non riuscito (riepilogo, 2026-10-28)

**Non riuscito o limite noto**
1. **Voce di menu «🌳 La mia carta»**: il tocco non fa nulla e non arriva nessun evento al webhook. Bug aperto, causa non capita (Instagram o Zernio?), da segnalare a Zernio se persiste. Aggirabile: scrivere `CARTA`.
2. **Timeout di invio a 4 s**: 2 invii su ~7 scaduti; nel caso verificabile la card è arrivata lo stesso (falso `send_failed`). Vedi riga «Timeout di invio».
3. **Non follower lenti**: il primo DM (cartella Requests, non leggibile dall'API) arriva al webhook dopo minuti; non so se serva accettare la richiesta.

**Non verificato**
4. Evento duplicato (`replay_webhook`): test futuro.
5. ManyChat/standby: non provato per scelta (pilota senza strumenti simili; se c'è, lo scollega il founder).
6. Latenza `sentAt` → card sul telefono: non misurata.
7. Nel browser: reset password, 429, «Esci», banner e pulsanti grigi in pausa, carta di prova a occhio (verificati solo via HTTP il 2026-10-27).
8. `isFollower` `null`/assente nei payload del webhook: mai osservato.
9. Fuori da questo collaudo locale: Neon e DigitalOcean, un account Instagram di un merchant vero.

| Cosa | Esito |
|---|---|
| Onboarding da zero con tunnel cloudflared (webhook e voce di menu su Zernio) | **ok (2026-10-28)**, dal log: registrazione, chiave e account Zernio collegati (200), webhook registrato e raggiunto via tunnel (consegne 200), stato `ACTIVE`, voce di menu impostata (`persistent_menu_set` vero) |
| DM «CARTA» da un profilo che segue → card → `/c/<token>` → scan dalla PWA → punti nuovi in pagina | **ok lato server (2026-10-28)**: card consegnata, `/c/***` aperto (200), scan dalla PWA con +60 tree points e 1 conversione, cashback −200 centesimi. Il founder riferisce che il flusso funziona; la pagina sul telefono non è tracciata nel log |
| Tocco della voce di menu «🌳 La mia carta» → stessa card, stesso link | **non ok (2026-10-28)**: il menu è nostro (`persistent_menu_set` = vero, voce visibile in chat dal menu ≡), ma il tocco non fa nulla e **nessun evento arriva al webhook** (nessuna riga nel log). Il codice non è coinvolto; causa non capita (lato Instagram/Zernio?). **Bug aperto**, non blocca il rilascio: la carta si ottiene scrivendo `CARTA`. Da riprovare con altro profilo/app aggiornata e da segnalare a Zernio se persiste |
| DM «CARTA» (profilo che segue), 2026-10-28 | ok: card consegnata. Contatore invii del mese = **2** (`account:<id>`, 2026-10). Eventi registrati: 2 `sent`, 1 `ignored`, 1 `send_failed` (timeout di rete verso Zernio sull'invio; il retry di Zernio è scartato come «già visto» per scelta di progetto: nessun nuovo tentativo) |
| Timeout di invio (4 s) | **da tenere d'occhio (2026-10-28)**: 2 invii su ~7 sono scaduti a 4,1 s, il tetto, mentre quelli riusciti durano 1,5-1,9 s (12:47 con card appena creata per un follower, 13:20 durante la prova del non follower; anche un `GET` di elenco è scaduto). **Non dipende dal follow.** Nel caso verificabile (12:47) la conversazione su Zernio risulta aggiornata 1,2 s dopo il nostro timeout: la card è arrivata comunque, quindi `send_failed` può essere un falso negativo e il contatore invii può essere sottostimato. **Corretto dopo il collaudo (2026-10-28)**: il timeout di lettura dà ora `ZernioErrorKind.TIMEOUT` ed esito `send_uncertain` (invio contato nella quota, negozio in attesa non attivato); connessione mancata o `ConnectTimeout` restano `send_failed` e non contano. Nessun nuovo tentativo, per scelta di progetto (con timeout Zernio rilascia l'`Idempotency-Key`: un retry può duplicare la card) |
| Card/risposta a un **non follower**: invito a seguire consegnato? la card verrebbe rifiutata da Meta (2/1545133)? | **ok (2026-10-28)**: invito a seguire consegnato (`esito=follow_requested`), nessuna card, come da progetto. Il rifiuto Meta 2/1545133 **non è stato osservato**: ai non follower la card non viene nemmeno tentata |
| Dopo che il non follower segue e riscrive «CARTA»: arriva la card? | **ok, ma lento (2026-10-28)**: dopo il follow e un nuovo `CARTA` la card è partita (`esito=sent`, nuova card creata). Contatore invii del mese a fine prova: **5** (4 card + 1 invito). Il founder riferisce che «ci mette tanto ma funziona» |
| Webhook per un DM in **Requests** (profilo che non segue il negozio) | **arriva, con grande ritardo (2026-10-28)**: B (non follower) scrive `CARTA`; per diversi minuti nessun evento e nessuna conversazione su `GET /v1/inbox/conversations` (la cartella Requests non è leggibile con Instagram Login: 400 `PLATFORM_LIMITATION`). Dopo l'accettazione della richiesta dall'app e un nuovo `CARTA` il webhook è arrivato (`follow_requested`). **Non so se a sbloccare sia stata l'accettazione, il nuovo messaggio o solo il tempo**: ritardo non misurato con precisione. Per i merchant: il primo DM di un non follower può impiegare minuti |
| `isFollower`: valore reale nei payload (`true`/`false`/`null`/assente), anche subito dopo aver iniziato a seguire | **parziale (2026-10-28)**: `true` per i profili che seguono (letto dall'API conversazioni); per B il server ha registrato `follow_requested`, quindi falso al momento del DM. `null`/assente **non osservato** nei payload del webhook (compare solo in conversazioni vecchie di febbraio); il ritardo dell'aggiornamento dopo il follow non è misurato. Il codice tratta `null` come follower (deploy.md, passo 5) |
| ManyChat (o altra app) come app predefinita: arriva `metadata.standby`? l'avviso compare nel pannello? | **non provato, per scelta (2026-10-28)**: troppo presto per i pilota; strumenti simili sono quasi assenti tra le attività italiane. Se un merchant pilota lo avesse, lo scollega il founder. Il codice gestisce `standby` (nessuna risposta + avviso nel pannello) ma resta non verificato dal vivo |
| Evento duplicato (`replay_webhook --event-id`): un solo invio | **non eseguito (2026-10-28)**, per scelta: test futuro (il rischio è una card mandata due volte). La dedup su `X-Zernio-Event-Id` è coperta dai test automatici e in questa sessione ha scartato due retry di Zernio come «già visto» |
| Latenza: `sentAt` → arrivo del webhook → card sul telefono (osservati ~30 s; webhook ~11,5 s dopo `sentAt`) | **non misurata (2026-10-28)**. Osservato: l'invio della card dura 1,5-1,9 s quando riesce (prove precedenti 1,2-3,1 s); il primo DM di un non follower può arrivare dopo minuti (riga sulle Requests) |
| Log del server: nessun token, IGSID, chiave o secret | **ok (2026-10-28)**, 155 righe lette: 0 occorrenze di chiave `sk_`, hash `scrypt$`, `bearer`, password, secret, token nei percorsi (`/c/***`, `/webhooks/zernio/***` mascherati), numeri lunghi tipo IGSID. Nei log compaiono: id Zernio della conversazione (solo nei timeout d'invio), UUID della card (che è anche il contenuto del QR; non il token del link, di cui il DB tiene solo l'hash) e `fbclid` nelle richieste dei crawler Meta a `/` (404). **Osservazione**: 2 invii su ~7 sono falliti per timeout verso Zernio (12:47 e 13:20 locali; anche un `GET` elenco è scaduto), senza nuovo tentativo per scelta di progetto: il cliente non riceve nulla finché non riscrive `CARTA` |
| «Scollega» da pannello → webhook sparito da Zernio | **ok (2026-10-28)**, riferito dal founder |
| Negozio in attesa: `CARTA` di un cliente nuovo → `/carta-di-prova` (senza QR né dati); dopo «Avvia» → carta vera | **parziale (2026-10-28)**, dal log: `/carta-di-prova` servita (200) e «Avvia» dalla dashboard (200), poi carte vere consegnate. L'assenza di QR e dati è coperta dal test del ticket 12; **non ricontrollata a occhio** in questa sessione |
| Dashboard `/admin` nel browser: lista, filtro, ricerca, «Avvia», «Metti in pausa» (banner e pulsanti grigi nello scanner, pagina carta invariata), «Riattiva», «Esci» | **parziale (2026-10-28)**, dal log: login admin, lista, «Avvia», pausa e «Riattiva» eseguiti (200). **Non confermati**: banner e pulsanti grigi nello scanner in pausa, «Esci», filtro e ricerca (girano nel browser, senza traccia nel log) |
| Reset password (Copia, vecchia password e sessione aperta invalide, cambio dalle impostazioni) e 429 dopo 6 errori | **non eseguito dal founder (2026-10-28)**: nessuna chiamata di reset nel log. Verificato solo via HTTP il 2026-10-27 (script usa-e-getta: password temporanea, sessioni decadute, 429 al 6° errore), **non da browser** |
| Log del server: nessuna password, temporanea o `ADMIN_SECRET_KEY` | **ok per il log del 2026-10-28** (0 occorrenze di password, secret, hash). Nessuna password temporanea è stata generata in questa sessione: quel caso resta provato solo dallo script del 2026-10-27 |
