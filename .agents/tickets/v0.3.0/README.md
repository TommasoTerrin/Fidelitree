# Ticket v0.3.0 — Carta fedeltà via DM Instagram (Zernio)

Obiettivo della versione: la carta del cliente nasce da un **DM Instagram al negozio**. Il cliente scrive la parola
chiave (o tocca la voce "🌳 La mia carta" del menu della chat), il webhook Zernio arriva alla nostra app, che crea
(o ritrova) la carta e risponde con **una card** (generic template) che contiene un link segreto alla pagina carta.
Questo flusso **sostituisce** iscrizione email+OTP, wallet, QR `/join/{negozio}` e la PWA lato cliente.
**Alberi, pool, cashback e auth merchant restano invariati.**

Contesto di business e regole: [AGENTS.md](../../../AGENTS.md). Vincoli delle piattaforme, con le fonti:
[zernio-notes.md](../../architecture/zernio-notes.md). Architettura target: [overview.md](../../architecture/overview.md).
Leggili PRIMA.

## Come usare i ticket

Si lavora **un ticket alla volta**, nell'ordine. Un ticket è chiuso solo quando:
- tutti i test della sezione "Test da superare" esistono e passano;
- `python -m pytest` è verde sull'intera suite;
- il collaudo manuale, se il ticket lo prevede, è stato fatto.

A fine ticket: commit in italiano e riepilogo di 3 righe all'utente. Se emerge una decisione architetturale non
prevista qui: **fermati e chiedi**.

Ogni ticket contiene: obiettivo, contesto, dipendenze, modifiche, file coinvolti, test da superare (l'agente può
affinarli, ma non ridurne la copertura), fuori scope, definition of done.

## Ordine e dipendenze

| # | Ticket | Dipende da |
|---|---|---|
| 01 | [Versione 0.3.0](01-versione.md) | — |
| 02 | [Modelli, config ed errori](02-modelli-config-errori.md) | 01 |
| 03 | [Cifratura, indice cieco e token del link](03-cifratura-indice-cieco.md) | 02 |
| 04 | [Core dei messaggi: trigger, card, 24 ore, quota](04-core-messaggi.md) | 02 |
| 05 | [Client Zernio, `zernio_check` e collaudo anticipato](05-client-zernio.md) | 03, 04 |
| 06 | [Webhook: dalla parola chiave alla card](06-webhook.md) | 03, 04, 05 |
| 07 | [Onboarding Instagram del merchant](07-onboarding-merchant.md) | 05, 06 |
| 08 | [Pagina carta, QR, scan e PWA merchant](08-pagina-carta-scan-pwa.md) | 03, 06 |
| 09 | [Rimozione del vecchio flusso cliente](09-rimozione-flusso-cliente.md) | 06, 07, 08 |
| 10 | [Seed, smoke test e script](10-seed-script.md) | 09 |
| 11 | [Autenticazione dei merchant: provider locale](11-auth-locale.md) | 01-10 |
| 12 | [Stato del servizio: approvazione, pausa e carta di prova](12-stato-servizio.md) | 06, 08, 11 |
| 13 | [Dashboard admin](13-dashboard-admin.md) | 11, 12 |
| 14 | [Documentazione, collaudo end-to-end e release](14-docs-collaudo-release.md) | tutti |

I ticket 11-13 sono stati aggiunti il 2026-10-27 (decisione «prima del pilota»): in produzione i merchant non potevano accedere
(`dev` rifiutato, Supabase stub) e il founder deve poter avviare (approvare), mettere in pausa e reimpostare le password. Il vecchio ticket 11
è diventato il **14**.

Il **ticket 05** ha un collaudo manuale su un account Instagram vero. Va fatto **prima** di scrivere webhook e onboarding,
perché verifica il rischio più grosso: che Meta rifiuti la card a chi non segue il negozio.
Se l'esito contraddice queste ipotesi: **fermati e chiedi**.

I ticket 02-08 **aggiungono** il nuovo flusso accanto al vecchio, che continua a funzionare (`Card.customer_id` diventa
facoltativo). Il vecchio flusso viene **tolto** tutto insieme nel ticket 09: così ogni ticket lascia il progetto funzionante.

## Convenzioni valide per TUTTI i ticket

Restano valide tutte le convenzioni di [v0.2.0](../v0.2.0/README.md): stile, docstring in italiano, functional core /
imperative shell, test che descrivono il vecchio comportamento riscritti o rimossi, progetto avviabile, nuove env var,
planner, denaro in centesimi, tempo UTC. In più valgono queste:

1. **Nessuna chiamata di rete nei test.** Il client Zernio riceve un `httpx.AsyncClient` iniettabile; nei test si usa
   `httpx.AsyncClient(transport=httpx.MockTransport(handler))`. Le route lo ottengono da una dependency sovrascrivibile
   in `app.dependency_overrides`.
2. **Nessun segreto in log, risposte API, messaggi di errore o commit.** Sono segreti:
   - la chiave Zernio e il secret del webhook;
   - l'IGSID in chiaro;
   - il token del link della carta.

   La chiave Zernio si mostra al massimo con le ultime 4 cifre. I test lo verificano dove indicato (`caplog`, corpo
   delle risposte).
3. **Confronti in tempo costante** (`hmac.compare_digest`) per firme, token e hash.
4. **Chiavi di cifratura solo da env**, senza default: l'app non parte se mancano. Nei test i valori arrivano da
   `os.environ.setdefault(...)` in cima a `tests/conftest.py`, prima di importare l'app.
5. **Il punto di aggancio** `zernio_service.zernio_credentials_for(merchant)` è l'**unico** codice che sa da dove arriva
   la chiave Zernio. Nessun altro modulo legge `Merchant.zernio_api_key_enc` o decifra la chiave.
6. **Testo dei messaggi mai salvato.** Del cliente si salvano solo l'indice cieco dell'IGSID e l'handle della
   conversazione Zernio; niente username, nome o foto.

## Modello dati target (riferimento unico)

```
Merchant      (campi esistenti invariati) +
              zernio_api_key_enc     str opz.   # AES-256-GCM "<key_id>:<base64(nonce+cifrato)>"
              zernio_account_id      str opz., unique   # accountId Zernio dell'account Instagram scelto
              zernio_profile_id      str opz.
              zernio_team_id         str opz.   # identità del team Zernio della chiave (ambito della quota, ticket 05)
              instagram_username     str opz.   # handle PUBBLICO del negozio, per il pannello
              webhook_hook_id        str opz., unique, index  # id opaco nel path del webhook (token_urlsafe)
              webhook_secret_enc     str opz.   # secret del webhook del negozio, cifrato
              zernio_webhook_id      str opz.   # id del webhook su Zernio (per rimuoverlo)
              instagram_status       InstagramStatus (default NOT_CONNECTED)
                                     # not_connected | awaiting_test_dm | active | key_invalid
              persistent_menu_set    bool (default False)  # False con account collegato = menu altrui, avviso
              standby_detected_at    datetime opz. (UTC)   # ultimo messaggio in standby (altra app proprietaria)
              standby_owner_app_id   str opz.              # app proprietaria, se Meta la indica

Card          id UUID (è anche il contenuto del QR per lo scan), merchant_id, cashback_cents, tree_points,
              igsid_hash             str opz. (obbligatorio dal ticket 09)  # HMAC-SHA256 dell'IGSID
              link_version           int (default 1)       # +1 = revoca del link
              link_token_hash        str opz., unique, index  # SHA-256 del token del link (il token non si salva)
              zernio_conversation_id str opz.   # handle Zernio per rispondere, aggiornato a ogni messaggio
              last_inbound_at        datetime opz. (UTC)   # sentAt dell'ultimo messaggio del cliente
              created_at             datetime (UTC)
              customer_id            int opz.   # SOLO fino al ticket 09, poi rimosso con Customer
              UNIQUE(merchant_id, igsid_hash)   # una carta per coppia (negozio, IGSID)

ProcessedWebhookEvent  event_id str PK (X-Zernio-Event-Id), merchant_id (FK CASCADE), received_at (UTC, index),
              outcome str  # received (iniziale) | sent | fallback_sent | follow_requested | ignored | standby | send_failed | send_uncertain | out_of_window
              # dedup dei retry Zernio (at-least-once, ~51 h di retry): conservazione 7 giorni

ZernioSendCounter  quota_scope str + period 'YYYY-MM' (PK composta), sent int
              # invii riusciti del mese per ambito di quota = team Zernio che invia
              # (oggi "zernio:<zernio_team_id>", fallback "account:<zernio_account_id>"; domani "platform")

AuthCredential  (ticket 11) user_id str PK (= Merchant.auth_user_id), email unique, password_hash (scrypt),
              token_version int (un reset invalida le sessioni), created_at
Merchant      (ticket 12) + created_at (UTC), is_paused bool (default False)

PointTransaction, MerchantPool, TreePlanting   invariati
Customer      RIMOSSO nel ticket 09 (insieme a Card.customer_id)
```

Vincoli trasversali: FK verso `merchant` con `ondelete="CASCADE"` come in v0.2.0; `InstagramStatus` e `WebhookOutcome`
sono enum `str, Enum` in `app/core/enums.py`.
