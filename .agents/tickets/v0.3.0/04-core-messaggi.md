# 04 — Core dei messaggi: trigger, card, finestra 24 ore, quota

## Obiettivo
Tutte le regole del flusso Instagram come **funzioni pure** in `app/services/instagram_service.py` (sezione
`# --- Core puro ---`), testate in `tests/unit/` senza DB né mock:
- lettura del payload `message.received`;
- verifica della firma;
- riconoscimento del trigger;
- costruzione e limiti della card;
- finestra delle 24 ore;
- stato della quota.

## Contesto
Vincoli e fonti in [zernio-notes.md](../../architecture/zernio-notes.md). Decisioni del 2026-10-22:
- **Trigger**: una parola chiave **unica di piattaforma** (`INSTAGRAM_CARD_KEYWORD`, default `CARTA`) oppure il tocco
  sulla voce del menu persistente (postback con payload fisso `FIDELITREE_CARD`).
  - Normalizzazione: maiuscole, accenti, spazi, punteggiatura ed emoji ignorati. `"carta"`, `" Carta! "`, `"/carta"`,
    `"CARTA 🌳"` e `"cartà"` valgono; `"vorrei la carta"` no.
  - Corrispondenza esatta dopo la normalizzazione.
  - Il riconoscitore riceve un messaggio già normalizzato in `InboundMessage`, con un campo `source`, così un giorno si
    aggiungono commenti e risposte alle storie senza toccare il resto.
- **Card**: un solo elemento generic template.
  - Titolo = nome del negozio.
  - Sottotitolo fisso `"La tua carta fedeltà: punti, cashback e alberi 🌳"`.
  - Un bottone URL `"Apri la carta"` verso `<PUBLIC_BASE_URL>/c/<token>`.
  - **Nessun dato dinamico** (punti, livello, cashback).
  - Limiti: `title` ≤ 80, `subtitle` ≤ 80, titolo del bottone ≤ 20, URL `https://`.
- **Ripiego testo** (solo se Meta rifiuta la card a un non follower): testo fisso
  `"La tua carta fedeltà di <negozio>: <link>"`, limite prudente di 640 caratteri (il minimo documentato in
  zernio-notes).
- **Finestra**: si risponde solo se `now - sentAt < 24 h`, dove `sentAt` è quello del messaggio del cliente e non
  l'ora di consegna del webhook. I retry di Zernio arrivano fino a ~51 h dopo.
- **Quota**: contatore mensile per ambito, soglia `ZERNIO_MONTHLY_SEND_LIMIT`, avviso a `ZERNIO_SEND_WARN_PERCENT`.
  Non blocchiamo noi: lo stato serve al pannello e ai log.

## Dipendenze
02.

## Modifiche
1. **`app/services/instagram_service.py`** (nuovo). Sezione core con docstring di modulo sulle regole di business, come
   negli altri service:
   - **Costanti**: `CARD_POSTBACK_PAYLOAD = "FIDELITREE_CARD"`, `MENU_ITEM_TITLE = "🌳 La mia carta"`,
     `CARD_SUBTITLE`, `CARD_BUTTON_TITLE`, `REPLY_WINDOW = timedelta(hours=24)`, i limiti di caratteri (con la fonte in
     commento).
   - **`InboundMessage(BaseModel)`**: `event_id`, `source` (`"dm_text"` | `"dm_postback"`), `account_id`,
     `conversation_id`, `sender_id`, `direction`, `text`, `postback_payload`, `sent_at` (aware), `standby`.
   - **`parse_message_received(payload: dict, event_id: str) -> InboundMessage | None`**:
     - `None` se `event != "message.received"`;
     - `InvalidInputError` se mancano `account.accountId`, `conversation.id`, `message.sender.id` o `message.sentAt`;
     - `metadata.postbackPayload` → `source="dm_postback"`; `metadata.standby` → `standby` (default `False`).
   - **`verify_signature(secret: str, raw_body: bytes, signature: str | None) -> bool`**: HMAC-SHA256 hex del corpo
     grezzo, confronto con `hmac.compare_digest`; firma assente → `False`.
   - **`normalize_text(text: str | None) -> str`**: NFKD, via i segni diacritici, `casefold`, solo lettere, cifre e
     spazi, spazi compattati, `strip`.
   - **`Trigger(str, Enum)`** con `CARD_REQUEST` e `detect_trigger(msg: InboundMessage, keyword: str) -> Trigger | None`.
     Restituisce `None` per i messaggi `outgoing`.
   - **`CardMessage(BaseModel)`** (`title`, `subtitle`, `button_title`, `button_url`) e
     `build_card_message(business_name, card_url) -> CardMessage`. Solleva:
     - `MessageTooLongError` per un campo oltre il limite, con il nome del campo, il limite e la lunghezza; mai il link;
     - `InvalidInputError` per un URL non `https://` o un nome vuoto.
   - **`build_fallback_text(business_name, card_url) -> str`**, con lo stesso controllo dei limiti.
   - **`can_reply(last_inbound_at, now) -> bool`**.
   - **`QuotaStatus(BaseModel)`** (`sent`, `limit`, `percent`, `warning`, `exhausted`) e
     `quota_status(sent, limit, warn_percent) -> QuotaStatus`.
2. **`app/services/merchant_service.py`**: `validate_registration` e l'aggiornamento del nome rifiutano un
   `business_name` oltre 80 caratteri, così la card del negozio è sempre costruibile. Errore `InvalidInputError` in
   italiano.

## File coinvolti
`app/services/instagram_service.py` (nuovo), `app/services/merchant_service.py`, `tests/unit/test_instagram_core.py`
(nuovo), `tests/unit/test_merchant_validation.py`.

## Test da superare
**Unit (senza DB e senza mock):**
- **`parse_message_received`**:
  - dal payload di esempio di zernio-notes (completato con `sentAt`) estrae account, conversazione, sender, testo e
    `standby=False`;
  - un payload con `metadata.postbackPayload` dà `source="dm_postback"`;
  - `metadata.standby: true` → `standby=True`;
  - `event: "message.sent"` → `None`;
  - un campo obbligatorio mancante → `InvalidInputError`.
- **`verify_signature`**: firma corretta → `True`; un byte del corpo cambiato, secret diverso, firma `None` o vuota →
  `False`.
- **`normalize_text`**: `" Carta! "`, `"/carta"`, `"CARTA 🌳"`, `"cartà"` → `"carta"`; `None` → `""`.
- **`detect_trigger`**:
  - `CARD_REQUEST` per il testo `"Carta!"` con keyword `"CARTA"`;
  - `CARD_REQUEST` per il postback `FIDELITREE_CARD` anche con testo diverso;
  - `None` per `"vorrei la carta"`, per un postback diverso, per testo vuoto e per `direction="outgoing"`.
- **`build_card_message`**:
  - "Bar Demo" → titolo "Bar Demo", sottotitolo e bottone fissi, URL invariato;
  - nome di 81 caratteri → `MessageTooLongError` che cita `title`;
  - URL `http://...` → `InvalidInputError`;
  - i limiti valgono anche per le costanti (il sottotitolo fisso sta in 80 caratteri, il bottone in 20).
- **`build_fallback_text`**: contiene nome e link e rispetta i 640 caratteri.
- **`can_reply`**: 23 h 59 m → `True`; 24 h esatte → `False`; 51 h → `False`.
- **`quota_status`**:
  - 7.499 su 10.000 al 75% → nessun avviso;
  - 7.500 → `warning`;
  - 10.000 → `exhausted`;
  - `limit` 0 non divide per zero.
- **Merchant**: `validate_registration` con nome di 81 caratteri → errore; 80 → ok.

## Fuori scope
I/O: DB, Zernio e route (05-07).

## Definition of Done
Suite verde, il core non importa `sqlmodel`, `httpx` né `fastapi` e non chiama `datetime.now()`.
