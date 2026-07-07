# Architettura Fidelitree

## Vista d'insieme

Monolite FastAPI con rendering server-side (Jinja2) e API JSON. Un solo processo, un solo database.

```
Browser (cliente / merchant)
   │  HTML (Jinja2) + fetch JSON
   ▼
FastAPI (app/main.py)
   │  routes → services → db_crud
   ▼
PostgreSQL (Neon)
```

## Modello dati

Due tabelle (definite in `app/models/models.py`, schema creato da `create_all()` all'avvio):

**Merchant** — l'esercente
| Campo | Tipo | Note |
|---|---|---|
| id | int PK | autoincrement |
| business_name | str | |
| phone_number | str | validato: `+39` + 9-10 cifre |
| password | str | **cifrata Fernet** (vedi vincoli in AGENTS.md) |
| type | str | 'test' \| 'free' \| 'pro' |

**Card** — la carta fedeltà (relazione 1:N con Merchant, cascade delete)
| Campo | Tipo | Note |
|---|---|---|
| id | UUID PK | generato server-side; funge da capability URL |
| merchant_id | int FK | |
| cashback_point | float | credito in euro, mai sotto zero |

⚠️ Nota SQLModel: con `table=True` i validatori pydantic **non girano sul costruttore**.
Per validare usa `Merchant.model_validate(...)` (come fa `merchant_crud`).

## Autenticazione

- **Merchant**: `POST /merchant/login` (form telefono+password) → confronto con password decifrata → JWT (HS256, 7 giorni) in cookie `access_token` httpOnly → dependency `get_current_merchant`.
- **Admin**: header `X-Admin-Key` confrontato con `ADMIN_SECRET_KEY` → dependency `require_admin_key`.
- **Cliente finale**: nessuna auth; conoscere l'UUID della carta equivale a possederla.

## Endpoint

| Metodo e path | Protezione | Scopo |
|---|---|---|
| GET /health | pubblico | health check (monitoraggio DO) |
| GET /download_card | pubblico | pagina "ottieni la carta" (`?m=<merchant_id>`) |
| GET /card/{id} | pubblico | pagina carta con QR e saldo |
| POST /api/get-card | pubblico | crea carta, ritorna link WhatsApp |
| GET /api/card/{id} | pubblico | dati carta (JSON) |
| POST /merchant/login | pubblico | login, setta cookie |
| GET /merchant/logout | pubblico | cancella cookie |
| GET /merchant/scanner | cookie merchant | pagina scanner QR |
| GET /merchant/card/{id}/manage | cookie merchant | pagina gestione cashback |
| POST /api/merchant/add-point/{id} | cookie merchant | +/- cashback (body: `{"cb_points": float}`) |
| DELETE /api/merchant/card/{id} | cookie merchant | elimina carta propria |
| CRUD /api/merchant/... | X-Admin-Key | gestione merchant (crea/lista/leggi/aggiorna/elimina) |

## Flusso principale (release 1)

1. Cliente apre `/download_card?m=<merchant_id>` → `POST /api/get-card` crea la Card.
2. Il backend ritorna un link `wa.me` verso il numero del merchant con placeholder `{card_url}`; il JS lo sostituisce con `window.location.origin + card_path`.
3. Il cliente si auto-invia la carta su WhatsApp e apre `/card/{uuid}` → QR generato client-side (qrcodejs).
4. Il merchant fa login → `/merchant/scanner` (html5-qrcode) → scan → redirect a `/merchant/card/{uuid}/manage`.
5. Da lì aggiunge/rimuove cashback via `POST /api/merchant/add-point/{uuid}`.

## Scelte tecniche rilevanti

- **Engine DB** creato in `app/main.py` con `pool_pre_ping=True` e `pool_recycle=300` (workaround per i timeout SSL di Neon).
- **`get_session`** importa l'engine lazy da `app.main` per evitare import circolari; nei test viene sovrascritta con SQLite in-memory (vedi `tests/conftest.py`).
- **QR code** generato client-side (niente dipendenze server).
- **Lifespan**: esegue solo `SQLModel.metadata.create_all(engine)`.
