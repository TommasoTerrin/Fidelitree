# Stato corrente

> Aggiorna questo file a inizio e fine sessione di lavoro, e dentro il commit di ogni ticket.
> Qui sta solo il lavoro **di adesso**. Item completati di una versione → riga nel changelog di `roadmap.md`;
> il registro dettagliato di una versione chiusa → `.agents/tickets/vX.Y.Z/STORICO.md`
> (v0.2.0: [STORICO.md](../tickets/v0.2.0/STORICO.md)).

## Dove siamo

**v0.3.0 — carta fedeltà via DM Instagram (Zernio)**, branch `feature/instagram-cards` (da `develop`, avviata il
2026-10-22). È la **prima release in produzione dopo v0.1.0**: assorbe v0.2.x (pool del negozio, auth merchant,
alberi), mai rilasciata. Dopo v0.3.0 l'app è funzionalmente quella descritta in AGENTS.md; la strada verso la
versione "a regime" è nella [roadmap](roadmap.md).

Contesto di riferimento: decisioni in [AGENTS.md](../../AGENTS.md), vincoli Zernio/Meta con le fonti in
[zernio-notes.md](../architecture/zernio-notes.md), ticket in [tickets/v0.3.0](../tickets/v0.3.0/README.md).

### Ticket

| # | Ticket | Stato |
|---|---|---|
| 01 | Versione 0.3.0 | ✅ `505fc00` |
| 02 | Modelli, config ed errori | ✅ `865797d` |
| 03 | Cifratura AES-GCM, indice cieco IGSID, token del link | ✅ `161850d` (414 test) |
| 04 | Core dei messaggi: trigger, card, finestra 24 h, quota | ✅ 2026-10-23 `f4bb1b3` (459 test) |
| 05 | Client Zernio, `zernio_check`, **collaudo anticipato** | ✅ 2026-10-26: passi 1-2 del collaudo fatti (base URL `https://zernio.com/api` ok, `send-card` consegnata e corretta su mobile al profilo del founder); passo 3 (non follower) rimandato al collaudo del 07/11 |
| 06 | Webhook: dalla parola chiave alla card | ✅ 2026-10-23 (644 test) |
| 07 | Onboarding Instagram del merchant | |
| 08 | Pagina carta, QR, scan e PWA merchant | |
| 09 | Rimozione del vecchio flusso cliente (OTP, wallet, `/join`, `Customer`) | |
| 10 | Seed, smoke test e script | |
| 11 | Documentazione, collaudo end-to-end e release | |

Suite di partenza: 360 test. I ticket 02-08 **aggiungono** il nuovo flusso accanto al vecchio (che continua a
funzionare); il vecchio si toglie tutto insieme nel 09.

Note sui ticket fatti:
- **03**: `app/core/crypto.py` (AES-256-GCM, HMAC dell'IGSID, token del link, `mask_secret`) e `validate_keys` all'avvio.
- **04**: `instagram_service` contiene per ora **solo il core** (payload `message.received`, firma, normalizzazione e
  trigger, card e testo di ripiego con limiti, finestra 24 h, stato quota); la shell arriva con i ticket 05-07.
  `merchant_service.validate_business_name`: nome del negozio ≤ 80 caratteri (è il titolo della card).

- **05**: `zernio_service` (core: `classify_error`, corpi delle richieste, `parse_accounts`, `ZernioCredentials` con
  `SecretStr`; shell: client httpx senza nuovi tentativi, timeout 3 s invio / 10 s configurazione,
  `zernio_credentials_for` unico lettore dei campi cifrati) e `scripts/zernio_check`. Dalla spec: il menu si imposta con
  **PUT** `messenger-menu`, il webhook si elimina con `DELETE /v1/webhooks/settings?webhookId=`, e **`folder=requests`
  non funziona con Instagram Login** (400 `PLATFORM_LIMITATION`); nessun campo identifica il team Zernio, quindi
  `get_team_identity` → `None` (quota `account:<id>`). Dettagli in `zernio-notes.md`. Lo script ha bisogno di
  `ENCRYPTION_KEY`, `IGSID_HMAC_KEY`, `CARD_LINK_KEY` nell'ambiente (importa le settings).

- **06**: `instagram_service` ha ora anche la shell: `get_or_create_card`, `card_link_url`, `handle_webhook` (negozio da
  `hook_id` → firma → JSON → riga dell'evento per prima → pulizia a 7 giorni → trigger → `isFollower` → carta → invio),
  route `POST /webhooks/zernio/{hook_id}` in `app/routes/webhooks.py` e `scripts/replay_webhook` (`--follower si|no`
  in più rispetto al ticket). Esito nuovo `FOLLOW_REQUESTED`. Scelte non previste dal ticket:
  `build_follow_prompt_text` ha un terzo parametro `keyword` (il core non legge le settings); anche l'invito a seguire
  rispetta la finestra di 24 ore, conta per la quota e attiva un negozio `AWAITING_TEST_DM` (come card e ripiego);
  la mappatura degli errori è una sola per card, ripiego e invito (`AUTH` → `KEY_INVALID`, `NOT_THREAD_OWNER` → standby);
  un negozio con `hook_id` ma senza chiave/account risponde 404, senza secret 401; un errore di costruzione del
  messaggio (link non https, nome > 80 caratteri) dà `SEND_FAILED` e 200, non un 400 che farebbe ritentare Zernio.

### Prossimo passo

1. ~~Ticket 05~~ codice fatto; **chiuderlo** dopo il collaudo.
2. ~~Ticket 06~~ fatto. Ora il **collaudo manuale anticipato del 05, a cura del founder** (passi 1-2 almeno; ticket 05 →
   "Collaudo manuale anticipato", ora con `replay_webhook` per provare il webhook in locale), **prima** di scrivere il
   07. Se ManyChat risulta ancora collegato all'account, scollegarlo.
   Verifica i rischi più grossi: Meta accetta la card a chi non segue il negozio? Il webhook arriva per i DM in
   Requests? Come si comporta ManyChat come app di default? Quale base URL Zernio vale? Se l'esito contraddice le
   ipotesi di `zernio-notes.md`: **fermarsi e chiedere**.
3. Poi 07 → 11 in ordine.

Esiti del collaudo del 05 (2026-10-26): `conversations` ha date in ritardo (la conversazione del founder risultava del
giorno prima: per trovarla si legge il mittente dei messaggi, non si fida dell'ordine); `--folder requests` dà 400
(limite già noto). Il founder ha notato una **latenza di circa 30 secondi** da qualche parte nel giro (non chiaro se
Zernio→webhook o consegna Instagram): **da misurare nel collaudo del 07** con timestamp di `sentAt`, arrivo del webhook e
consegna della card, perché in negozio il cliente aspetta al banco.
La chiave Zernio per gli script sta in `.env` come `ZERNIO_CHECK_API_KEY` (una sola variabile).

### Decisione del 2026-10-23: carta solo a chi segue
Il webhook (06) manda la card solo se `isFollower` è `true` o `null`; se `false` solo un testo di invito a seguire, senza
creare la carta. Dettagli in AGENTS.md e nel ticket 06 (nuovo esito `follow_requested`). Il comportamento con `null` si
rivede nel collaudo finale. QR "apri la chat": a mano dal founder (ticket 11).

### Da fare a mano (founder)

- Aggiungere al `.env` locale `ENCRYPTION_KEY`, `IGSID_HMAC_KEY`, `CARD_LINK_KEY` (l'app non parte senza; i test le
  impostano da soli). Non committare mai i valori.
- Collaudo del ticket 05 (sopra), un account Zernio gratuito e un account Instagram Business/Creator di prova.
- Rimasti da v0.2.x e ancora validi per il rilascio di v0.3.0: collaudo di `ecologi_check` (chiave di test e reale) e
  di `close_period` in test mode; checklist `pre-release.md`, PWA merchant su telefono (HTTPS o tunnel).
- Lavoro di documentazione della fase 4 (AGENTS.md, overview, deploy, `.env.example`, ticket v0.3.0, planner) ancora
  **non committato**: va committato a parte rispetto ai ticket di codice.

## Debito noto

- Merchant creato dall'admin senza `auth_user_id`: la sua email non si può registrare (409). Si risolve con Supabase.
- `create_all()` non migra: serve `scripts.reset_db` (nessun dato di produzione da preservare per ora).
- `reset_db`/`seed_db` agiscono sul `DATABASE_URL` del `.env` (oggi Neon): per il collaudo usare un SQLite usa-e-getta
  (`.agents/workflows/deploy.md`).
- Il testo di `/privacy` è una bozza da far verificare; DPA con i merchant ancora da scrivere (roadmap).

## Note per chi riprende il lavoro

- Regole di business e vincoli: AGENTS.md ("Contesto di business" e "Vincoli e trade-off").
- Convenzioni di codice (functional core / imperative shell, docstring italiane): AGENTS.md regole 3-5 e README dei ticket.
- I test girano offline (SQLite in-memory, Ecologi e Zernio mockati): `python -m pytest`; il core puro in `tests/unit/`.
- Si lavora un ticket alla volta; a fine ticket: test verdi, commit in italiano "... (ticket NN)", riepilogo di 3 righe
  e attesa dell'approvazione.
- La vecchia logica alberi/Telegram è in `feature/trees` (branch di archivio, non mergiare).
