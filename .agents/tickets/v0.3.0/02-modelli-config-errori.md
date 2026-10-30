# 02 — Modelli, config ed errori

## Obiettivo
Preparare lo schema, la configurazione e gli errori di dominio del nuovo flusso, senza rompere il vecchio:
- il modello dati è quello target del [README](README.md);
- nuove env var;
- enum `InstagramStatus` e `WebhookOutcome`;
- errori `MessageTooLongError` e `InvalidSignatureError`.

## Contesto
Fino al ticket 09 il vecchio flusso cliente (OTP, `/join`, wallet) resta in piedi: per questo `Card.customer_id`
diventa **facoltativo** invece di sparire e `Customer` resta. Le nuove colonne sono tutte facoltative o con default.
Non c'è Alembic: i DB locali si ricreano con `scripts.reset_db` (`create_all()` non aggiunge colonne a tabelle esistenti).

## Dipendenze
01.

## Modifiche
1. **`app/core/enums.py`**:
   - `InstagramStatus(str, Enum)`: `NOT_CONNECTED`, `AWAITING_TEST_DM`, `ACTIVE`, `KEY_INVALID`;
   - `WebhookOutcome(str, Enum)`: `RECEIVED` (stato iniziale, prima dell'elaborazione), `SENT`, `FALLBACK_SENT`,
     `IGNORED`, `STANDBY`, `SEND_FAILED`, `OUT_OF_WINDOW`.
2. **`app/models/models.py`**:
   - **`Merchant`**: i campi Zernio/Instagram del modello target. `zernio_account_id` e `webhook_hook_id` sono unique
     e nullable.
   - **`Card`**:
     - `customer_id` diventa `Optional[int]`;
     - nuovi campi `igsid_hash`, `link_version` (default 1), `link_token_hash` (unique, index),
       `zernio_conversation_id`, `last_inbound_at` (UTC aware, colonna con timezone), `created_at`;
     - la `UniqueConstraint` diventa `("merchant_id", "customer_id")` **più** `("merchant_id", "igsid_hash")`.
       Su SQLite e Postgres i `NULL` non collidono.
   - **`ProcessedWebhookEvent`** e **`ZernioSendCounter`** come nel modello target, con le relationship verso
     `Merchant` (cascade) dove c'è la FK.
3. **`app/core/config.py`**:
   - obbligatorie, senza default:
     - `ENCRYPTION_KEY`: 32 byte in base64 urlsafe;
     - `IGSID_HMAC_KEY`;
     - `CARD_LINK_KEY`;
   - con default:

     | Variabile | Default |
     |---|---|
     | `ENCRYPTION_KEY_ID` | `"1"` |
     | `PUBLIC_BASE_URL` | `"http://127.0.0.1:8001"` |
     | `ZERNIO_BASE_URL` | `"https://zernio.com/api"` |
     | `INSTAGRAM_CARD_KEYWORD` | `"CARTA"` |
     | `ZERNIO_MONTHLY_SEND_LIMIT` | `10000` |
     | `ZERNIO_SEND_WARN_PERCENT` | `75` |

   - commento di una riga su ciascuna, come le esistenti.
4. **`app/core/errors.py`**:
   - `MessageTooLongError(InvalidInputError)`: un campo della card supera il limite della piattaforma (400);
   - `InvalidSignatureError(AuthError)`: firma del webhook assente o errata (401).

   L'handler globale li copre già tramite le classi base.
5. **`tests/conftest.py`**: in cima, prima degli import dell'app, `os.environ.setdefault(...)` per le tre chiavi
   obbligatorie con valori di test fissi.
6. **`.env.example`** e **`.agents/workflows/deploy.md`**: le nuove variabili sono già documentate dalla fase di
   analisi (2026-10-22). Verifica che nomi e default coincidano con `Settings` e correggi le differenze.
   Il `.env` locale va aggiornato a mano dal founder: scrivilo nel riepilogo.

## File coinvolti
`app/core/enums.py`, `app/models/models.py`, `app/core/config.py`, `app/core/errors.py`, `tests/conftest.py`,
`tests/test_models.py`, `tests/test_core_infra.py`, `.env.example`, `.agents/workflows/deploy.md`.

## Test da superare
- **`Card` con IGSID**:
  - si crea una carta con `igsid_hash` e senza `customer_id`;
  - una seconda carta con stesso `(merchant_id, igsid_hash)` → `IntegrityError`;
  - stesso `igsid_hash` su due negozi diversi → ok.
- **`Card` del vecchio flusso**: si crea ancora con `customer_id` e senza `igsid_hash`, quindi i test esistenti restano
  verdi.
- **`link_token_hash`**: due carte con lo stesso valore → `IntegrityError`.
- **`ProcessedWebhookEvent`**: un secondo insert con lo stesso `event_id` → `IntegrityError`.
- **Cascade**: eliminare il merchant elimina carte, eventi e (se FK) contatori.
- **`ZernioSendCounter`**: PK composta `(quota_scope, period)`.
- **`Merchant` nuovo**: ha `instagram_status == NOT_CONNECTED` e `persistent_menu_set is False`.
- **Config**:
  - `Settings(_env_file=None)` con `monkeypatch.delenv` di `ENCRYPTION_KEY` (o `IGSID_HMAC_KEY`, `CARD_LINK_KEY`) →
    errore di validazione. Così il test non dipende dal `.env` locale;
  - i default delle variabili nuove sono quelli sopra.
- **Errori**: `MessageTooLongError` → 400 e `InvalidSignatureError` → 401 tramite l'handler globale. Usa una route di
  prova come nei test esistenti degli errori.

## Fuori scope
Cifratura (03), logica dei messaggi (04), rimozione di `Customer` (09).

## Definition of Done
Suite verde (i test del vecchio flusso compresi), `python -c "import app.main"` ok con le nuove variabili nel `.env`.
