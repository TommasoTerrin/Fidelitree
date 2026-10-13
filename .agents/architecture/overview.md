# Architettura Fidelitree (v0.2.0)

## Vista d'insieme

Monolite FastAPI con rendering server-side (Jinja2) e API JSON. Un solo processo, un solo database.
Il wallet del cliente è una **PWA** (manifest + service worker che mette in cache solo la shell statica).

```
Browser (cliente: PWA / merchant)
   │  HTML (Jinja2) + fetch JSON
   ▼
FastAPI (app/main.py)
   │  routes → services (core puro + shell) → db_crud
   ▼
PostgreSQL (Neon oggi, Supabase al collegamento del provider auth)

Script a mano (fuori dall'app): reset_db · seed_db · close_period · smoke_test_prod
   └─ close_period ──► Ecologi Impact API (chiave unica di piattaforma)
```

## Modello dati

Definito in `app/models/models.py`; lo schema nasce da `create_all()` all'avvio.
Denaro in **centesimi interi** (`*_cents`), timestamp **UTC aware**, mese = `period` `'YYYY-MM'` (UTC) fissato in scrittura.

| Tabella | Campi principali | Note |
|---|---|---|
| **Merchant** | `email` (unica, minuscolo), `auth_user_id` (unico, nullable), `contact_phone` (opz.), `type`, `is_approved` (default `False`), `conversion_enabled`, `conversion_threshold`, `conversion_value_cents`, `bronze/silver/gold_threshold` (override admin, opz.) | nessuna password nel DB |
| **Customer** | `email` (unica), `auth_user_id` (unico), `created_at` | creato al primo accesso |
| **Card** | `id` UUID, `merchant_id`, `customer_id`, `cashback_cents`, `tree_points` | `UNIQUE(merchant_id, customer_id)`: una carta per negozio |
| **PointTransaction** | `merchant_id`, `card_id` (non FK), `kind` (`scan`\|`conversion`), `delta`, `period`, `created_at` | **registro = fonte di verità** e audit |
| **MerchantPool** | PK `(merchant_id, period)`, `points` | contatore del pool = cache di `SUM(delta)` dei soli `scan`; aggiornato nella **stessa transazione** dello scan |
| **TreePlanting** | `merchant_id`, `period`, `level`, `tree_count`, `pool_points` (snapshot), `ecologi_ref`, `test` | `UNIQUE(merchant_id, period, test)`: idempotenza della chiusura |

⚠️ Nota SQLModel: con `table=True` i validatori pydantic **non girano sul costruttore**: per validare usa `Model.model_validate(...)` (come fanno i `db_crud`).

## Il pool del negozio

```
 Cliente A ─┐                                   ┌─ conversione in cashback (card):
 Cliente B ─┼─ scan +N tree points ─► PointTransaction(scan)   al raggiungimento della soglia
 Cliente C ─┘            │                         PointTransaction(conversion) — NON tocca il pool
                         ▼ (stessa transazione)
              MerchantPool(merchant, 'YYYY-MM').points += N
                         │
        fine mese: scripts.close_period  (anteprima → conferma → idempotente)
                         ▼
   livello = f(points, soglie effettive)   soglie = default TIER_* + override del negozio
   🥉 Bronzo → 1 albero · 🥈 Argento → 3 · 🥇 Oro → 5   (totali del mese, non cumulativi)
                         ▼
   Ecologi (chiave di piattaforma) → TreePlanting(snapshot pool_points, ecologi_ref)
   Il mese successivo il pool riparte da zero (nuova riga MerchantPool).
```

Guardie della chiusura: solo negozi **approvati**; si ferma se contatore e registro **divergono**
(`pool_mismatches`) o se il totale supera il **cap globale** (`ECOLOGI_GLOBAL_MONTHLY_CAP`, `--cap` per autorizzare);
un errore su un negozio non blocca gli altri (resta non chiuso e si ritenta).

## Autenticazione

Tutto passa da `AuthProvider` (`app/core/auth.py`); nel DB non ci sono password, solo `auth_user_id` ed email.

- **Provider `dev`** (locale/test): utenti in memoria, OTP sempre `000000`, password `DEV_AUTH_PASSWORD` per i merchant non registrati nel processo (così funzionano gli account del seed), token = JWT firmato con `JWT_SECRET_KEY`. Con `ENVIRONMENT=production` l'app **rifiuta** di usarlo.
- **Provider `supabase`**: stub, si collega in un rilascio successivo.
- **Merchant**: `POST /merchant/register` (nasce non approvato, lavora subito) e `POST /merchant/login` (email + password) → cookie `access_token` httpOnly → `get_current_merchant`.
- **Cliente**: OTP via email (`/api/customer/otp/{request,verify}`) → stesso cookie → `get_current_customer` (crea il cliente al primo accesso). La carta è visibile **solo al proprietario** (altrui → 404).
- **Admin**: header `X-Admin-Key` = `ADMIN_SECRET_KEY` → `require_admin_key`.
- ⚠️ Un merchant creato dall'admin (`POST /api/merchant/`) non ha `auth_user_id`: finché non c'è Supabase non può accedere né registrare la stessa email (409). Limite noto (vedi roadmap).

## Endpoint

| Metodo e path | Protezione | Scopo |
|---|---|---|
| GET /health | pubblico | health check con `version` (da `pyproject.toml`) |
| GET /sw.js | pubblico | service worker PWA (scope `/`) |
| GET /customer/login, POST /api/customer/otp/{request,verify}, GET /customer/logout | pubblico | login OTP del cliente |
| GET /join/{merchant_id} | pubblico | QR statico del negozio: iscrizione |
| POST /api/customer/join/{merchant_id} | cliente | crea (o riapre) la carta |
| GET /wallet, GET /api/customer/wallet | cliente | carte del cliente con livello del negozio |
| GET /card/{id}, GET /api/card/{id} | cliente proprietario | carta con QR, saldo e pool del negozio |
| GET /merchant/login, /merchant/register | pubblico | pagine di accesso |
| POST /merchant/register, POST /merchant/login, GET /merchant/logout | pubblico | auth merchant |
| GET /merchant/scanner, /merchant/settings, /merchant/card/{id}/manage | cookie merchant | pagine merchant |
| GET /api/merchant/me, PUT /api/merchant/me/settings | cookie merchant | profilo e impostazioni di conversione |
| POST /api/merchant/add-tree-points/{id} | cookie merchant | scan: tree points (+ conversione automatica) |
| POST /api/merchant/add-point/{id} | cookie merchant | +/- cashback in euro |
| DELETE /api/merchant/card/{id} | cookie merchant | elimina carta propria |
| CRUD /api/merchant/…, POST /api/merchant/{id}/approve | X-Admin-Key | gestione merchant, approvazione, soglie |

## Flussi

1. **Cliente**: apre il QR `/join/{negozio}` → login OTP (se serve) → carta creata e aperta → compare nel `/wallet` (installabile come PWA).
2. **Merchant**: login → `/merchant/scanner` (html5-qrcode) → scan del QR della carta → `/merchant/card/{id}/manage` → +tree points → pool aggiornato e, se raggiunta la soglia, conversione in cashback (toast). Cashback a mano sempre possibile.
3. **Chiusura mensile**: `python -m scripts.close_period` (vedi `deploy.md`).

## Scelte tecniche rilevanti

- **Functional core / imperative shell** nello stesso modulo di `services/` (regole in AGENTS.md). Errori di dominio in `app/core/errors.py`, tradotti in HTTP da un handler globale.
- **Engine DB** in `app/main.py` con `pool_pre_ping=True` e `pool_recycle=300` (timeout SSL di Neon).
- **`get_session`** importa l'engine lazy da `app.main` (evita import circolari); nei test viene sostituita da SQLite in-memory (`tests/conftest.py`).
- **QR code** generato client-side (niente dipendenze server).
- **Lifespan**: esegue solo `SQLModel.metadata.create_all(engine)` (niente Alembic: il DB si resetta con `scripts.reset_db`).
- **Ecologi**: `ECOLOGI_TEST_MODE=true` usa chiave/URL di **test** distinti da quelli reali (nessun addebito).
