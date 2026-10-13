# Deploy — DigitalOcean App Platform + Neon

## Come funziona

- L'app su **DigitalOcean App Platform** builda il `Dockerfile` e fa **auto-deploy a ogni push su `main`**.
- Il container ascolta su `$PORT` (iniettata da DO; default 8000 in locale).
- Il database è **PostgreSQL** (Neon oggi, Supabase in un rilascio successivo): l'app lo raggiunge tramite `DATABASE_URL`.
- Lo schema viene creato/aggiornato da `create_all()` all'avvio (solo tabelle/colonne NUOVE: non elimina né modifica colonne esistenti).

## Env vars richieste su DigitalOcean

Se ne manca una l'app **crasha all'avvio** (Settings pydantic con campi obbligatori):

| Variabile | Descrizione |
|---|---|
| `DATABASE_URL` | URL Postgres completo (`postgresql://...?sslmode=require`) |
| `JWT_SECRET_KEY` | firma dei token di sessione |
| `ADMIN_SECRET_KEY` | chiave per gli endpoint admin (`X-Admin-Key`) |

Variabili **opzionali** (hanno un default), introdotte con v0.2.0:

| Variabile | Default | Descrizione |
|---|---|---|
| `ENVIRONMENT` | `development` | mettere `production` in produzione (il login `dev` si rifiuta) |
| `AUTH_PROVIDER` | `dev` | `dev` (solo locale/test) o `supabase` |
| `DEV_AUTH_PASSWORD` | `dev-password` | **solo locale** (provider `dev`): password dei merchant creati dal seed. **Non impostarla in produzione** |
| `ECOLOGI_API_KEY` | vuota | chiave Ecologi **di piattaforma** (paga il founder); necessaria per `close_period` |
| `ECOLOGI_BASE_URL` | `https://public.ecologi.com` | URL dell'API Ecologi **reale** (usato con `ECOLOGI_TEST_MODE=false`) |
| `ECOLOGI_TEST_API_KEY` | vuota | chiave dell'ambiente di **prova** di Ecologi (usata con `ECOLOGI_TEST_MODE=true`) |
| `ECOLOGI_TEST_BASE_URL` | vuota | URL dell'ambiente di **prova** di Ecologi (usato con `ECOLOGI_TEST_MODE=true`) |
| `ECOLOGI_TEST_MODE` | `true` | `true` = chiave/URL di test, nessun addebito reale; `false` SOLO in produzione (chiave/URL reali) |
| `ECOLOGI_GLOBAL_MONTHLY_CAP` | `20` | massimo alberi piantati in una chiusura mensile |
| `TIER_BRONZE_POINTS` / `TIER_SILVER_POINTS` / `TIER_GOLD_POINTS` | `100` / `300` / `600` | soglie di default dei livelli del pool (override per negozio nel DB) |

Eliminate da v0.2.0 (cancellabili da DO): `ENCRYPTION_KEY`, `MERCHANT_PASSWORD`. Storiche non più usate: `HUMANI_*`, `TELEGRAM_BOT_TOKEN`, `BASE_URL`, `DATABASE_PASSWORD`.

> ⚠️ **Schema v0.2.0**: `create_all()` non modifica le tabelle esistenti. Il passaggio al nuovo modello (email, clienti, pool...) richiede il reset del DB (`python -m scripts.reset_db`): i dati di v0.1.0 non si migrano.

## Procedura di release

1. Completa la checklist `.agents/checklists/pre-release.md`.
2. `git checkout main && git merge develop && git push` → parte il deploy automatico.
3. Attendi il deploy dalla console DO (build + health check su `/health`).
4. Smoke test: `python scripts/smoke_test_prod.py https://<app>.ondigitalocean.app <ADMIN_SECRET_KEY>`.
5. Verifica il DB (console Neon/Supabase → tabelle `merchant`, `customer`, `card`, `pointtransaction`, `merchantpool`, `treeplanting` presenti).
6. Tag: `git tag vX.Y.Z && git push --tags`.
7. Riallinea develop: `git checkout develop && git merge main && git push`.

## Rollback

Dalla console DigitalOcean: Deployments → seleziona il deploy precedente → "Rollback".
In alternativa: `git revert` del merge su main e push (nuovo deploy).

## Chiusura mensile degli alberi (`scripts.close_period`)

Lo lancia il founder a mano, di norma nei primi giorni del mese per il **mese precedente**. Gira in locale
con `DATABASE_URL` e `ECOLOGI_*` della produzione nel `.env` (oppure in una console del container):

```bash
python -m scripts.close_period                  # mese precedente: anteprima + conferma
python -m scripts.close_period --month 2026-10  # mese specifico
python -m scripts.close_period --cap 30         # autorizza un cap diverso per questa esecuzione
python -m scripts.close_period --yes            # salta la conferma (NON il blocco cap)
```

- **Prima volta in assoluto**: prova con `ECOLOGI_TEST_MODE=true` (chiave/URL di test, nessun addebito). Per la chiusura vera serve `ECOLOGI_TEST_MODE=false` e `ECOLOGI_API_KEY` reale.
- Considera solo i negozi **approvati** (`is_approved`). È **idempotente**: rilanciarlo non pianta due volte lo stesso negozio.
- Codici di uscita: `0` ok · `1` divergenze contatore/registro o cap sforato non autorizzato · `2` annullato · `3` almeno un negozio fallito (si ritenta rilanciando).
- Lo scan del merchant non pianta mai alberi: la piantumazione avviene solo qui.

## Collaudo locale (DB usa-e-getta)

`reset_db` e `seed_db` agiscono sul `DATABASE_URL` del `.env`: **se punta a Neon/Supabase cancellano i dati veri**.
Per il collaudo usa un SQLite su file, sovrascrivendo la variabile solo nel terminale (le env var vincono sul `.env`):

```powershell
$env:DATABASE_URL = "sqlite:///collaudo.db"     # file ignorato da git (*.db)
python -m scripts.reset_db --force
python -m scripts.seed_db                        # stampa link e credenziali di prova
python local_main.py                             # http://127.0.0.1:8001
```

Per tornare al DB del `.env`: chiudi il terminale o `Remove-Item Env:DATABASE_URL`. Checklist completa: `pre-release.md`.

## Reset/seed del DB remoto (distruttivo!)

Solo se i dati sono sacrificabili (il seed richiede `AUTH_PROVIDER=dev`, quindi non è per la produzione vera).
In locale, con il `DATABASE_URL` remoto nel `.env`:

```bash
python -m scripts.reset_db      # chiede conferma (--force per saltare)
python -m scripts.seed_db       # solo con AUTH_PROVIDER=dev
```
