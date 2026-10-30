# 03 — Cifratura, indice cieco e token del link

## Obiettivo
Un modulo unico per i segreti, `app/core/crypto.py`, con quattro compiti:
- cifrare e decifrare la chiave Zernio e il secret del webhook (AES-256-GCM);
- calcolare l'**indice cieco** dell'IGSID;
- derivare il **token del link** della carta e il suo hash;
- confrontare in tempo costante.

## Contesto
Decisioni del 2026-10-22, vedi AGENTS.md "Vincoli e trade-off".
- **IGSID**: solo indice cieco `HMAC-SHA256(IGSID_HMAC_KEY, igsid)`, nessuna copia cifrata. Per rispondere si usa il
  `conversation.id` di Zernio. Limite accettato: la chiave HMAC non si può ruotare, perché senza IGSID in chiaro non
  si ricalcola l'indice; cambiarla scollega tutte le carte dai profili Instagram.
- **Token del link**: `base64url(HMAC-SHA256(CARD_LINK_KEY, f"{card_id}:{link_version}"))` senza padding. Si
  ricalcola quando serve (stesso link a ogni messaggio); nel DB c'è solo `SHA-256(token)` per la ricerca. Revoca:
  `link_version += 1`.
- **Cifratura**: `cryptography` (`AESGCM`, chiave da 32 byte), nonce casuale da 12 byte, formato salvato
  `"<ENCRYPTION_KEY_ID>:<base64url(nonce + cifrato)>"`. L'id della chiave serve alla rotazione futura (script in
  roadmap): decifrare con un id diverso da quello configurato è un errore esplicito.
- **Perché `cryptography` torna** (era stata tolta in v0.2.0): la chiave Zernio deve essere recuperabile per usarla, e
  la libreria standard non ha cifratura autenticata. `cryptography` è la libreria di riferimento (wheel precompilati,
  nessuna dipendenza nativa da installare).

`crypto.py` è funzionale ma usa le chiavi delle settings. Per testarlo senza env le funzioni ricevono la chiave come
argomento opzionale (default: quella delle settings), come l'iniezione del tempo negli altri core.

## Dipendenze
02.

## Modifiche
1. **`requirements.txt`**: `cryptography` con un commento sul perché.
2. **`app/core/crypto.py`** (nuovo, docstring in italiano, niente fastapi né DB):
   - `encrypt_secret(plaintext, *, key=None, key_id=None) -> str` e `decrypt_secret(stored, *, keys=None) -> str`.
     Formato errato, id sconosciuto o autenticazione fallita sollevano `SecretDecryptionError(Exception)`. Il messaggio
     non deve mai contenere il dato.
   - `igsid_blind_index(igsid, *, key=None) -> str` (hex).
   - `card_link_token(card_id, link_version, *, key=None) -> str`.
   - `token_hash(token) -> str` (SHA-256 hex).
   - `constant_time_equals(a, b) -> bool` (`hmac.compare_digest`).
   - `mask_secret(value) -> str`: `"…" + ultime 4` (o `"(vuota)"`), per log e pannello.
   - `validate_keys()`: chiamata nel `lifespan` di `app/main.py`. Solleva `RuntimeError` se `ENCRYPTION_KEY` non
     decodifica a 32 byte o se le chiavi HMAC sono più corte di 32 caratteri: l'app non parte.

## File coinvolti
`requirements.txt`, `app/core/crypto.py` (nuovo), `app/main.py` (lifespan), `tests/unit/test_crypto.py` (nuovo),
`tests/test_core_infra.py`.

## Test da superare
**Unit (senza DB, chiavi passate come argomento):**
- **Cifratura, casi base**:
  - `decrypt_secret(encrypt_secret("sk_x"))` restituisce `"sk_x"`;
  - due cifrature dello stesso testo danno risultati diversi (nonce casuale);
  - il risultato inizia con `"<id>:"`.
- **Cifratura, errori**: ognuno di questi casi solleva `SecretDecryptionError` **senza** il testo in chiaro nel
  messaggio:
  - un byte del cifrato alterato;
  - un id di chiave sconosciuto;
  - una chiave sbagliata;
  - una stringa senza `:`.
- **Indice cieco**: deterministico, diverso per IGSID diversi e per chiavi diverse, 64 caratteri hex, e non contiene
  l'IGSID.
- **Token del link**:
  - deterministico per `(card_id, versione)`;
  - cambia se cambia la versione;
  - è base64url senza `=`, di almeno 43 caratteri;
  - `token_hash(token)` è diverso dal token.
- **`mask_secret`**: `"sk_abcdef1234"` → `"…1234"`; stringa vuota → `"(vuota)"`.
- **`constant_time_equals`**: vero e falso nei casi ovvi.

**Integrazione:**
- `validate_keys()` con `ENCRYPTION_KEY` non valida (troppo corta, non base64) → `RuntimeError`; con le chiavi del
  conftest → nessun errore.

## Fuori scope
Script di rotazione della chiave (roadmap), uso nei service (05-08).

## Definition of Done
Suite verde, `cryptography` installata nel venv e in `requirements.txt`, nessun segreto in chiaro nei messaggi di errore.
