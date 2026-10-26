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
| `ENCRYPTION_KEY` | (v0.3.0) chiave AES-256-GCM, 32 byte in base64 urlsafe: cifra chiave Zernio e secret del webhook dei merchant |
| `IGSID_HMAC_KEY` | (v0.3.0) indice cieco dell'IGSID dei clienti. **Non ruotabile**: cambiarla scollega tutte le carte |
| `CARD_LINK_KEY` | (v0.3.0) deriva il token dei link delle carte; cambiarla invalida tutti i link già inviati |

Generazione (una per variabile, valori diversi): `python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`.
Conservale anche fuori da DigitalOcean (password manager): perderle significa perdere le chiavi Zernio dei merchant e il collegamento delle carte.

Variabili **opzionali** (hanno un default), introdotte con v0.2.0:

| Variabile | Default | Descrizione |
|---|---|---|
| `ENVIRONMENT` | `development` | mettere `production` in produzione (il login `dev` si rifiuta) |
| `AUTH_PROVIDER` | `dev` | `dev` (solo locale/test) o `supabase` |
| `DEV_AUTH_PASSWORD` | `dev-password` | **solo locale** (provider `dev`): password dei merchant creati dal seed. **Non impostarla in produzione** |
| `ECOLOGI_BASE_URL` | `https://public.ecologi.com` | URL dell'API Ecologi, **unico** per test e produzione (non esiste un sandbox: la prova è il flag `"test": true`) |
| `ECOLOGI_API_KEY` | vuota | chiave Ecologi **reale** di piattaforma (paga il founder); usata con `ECOLOGI_TEST_MODE=false` |
| `ECOLOGI_TEST_API_KEY` | vuota | chiave Ecologi **di prova**; usata con `ECOLOGI_TEST_MODE=true`. Nessun fallback tra le due chiavi |
| `ECOLOGI_TEST_MODE` | `true` | `true` = chiave di test + flag `test` (nessun addebito, nulla sul profilo Ecologi); `false` SOLO in produzione. In produzione: `ECOLOGI_TEST_MODE=false` + `ECOLOGI_API_KEY`; in locale: `true` + `ECOLOGI_TEST_API_KEY` |
| `ECOLOGI_GLOBAL_MONTHLY_CAP` | `20` | massimo alberi piantati in una chiusura mensile |
| `TIER_BRONZE_POINTS` / `TIER_SILVER_POINTS` / `TIER_GOLD_POINTS` | `100` / `300` / `600` | soglie di default dei livelli del pool (override per negozio nel DB) |
| `ENCRYPTION_KEY_ID` | `1` | (v0.3.0) id della chiave di cifratura salvato con ogni dato cifrato (rotazione futura) |
| `PUBLIC_BASE_URL` | `http://127.0.0.1:8001` | (v0.3.0) URL pubblico **https** dell'app: link delle carte e URL del webhook su Zernio. In produzione il dominio dell'app. **Se cambia, i merchant devono rifare l'onboarding Instagram** (il webhook su Zernio punta al vecchio URL) |
| `ZERNIO_BASE_URL` | `https://zernio.com/api` | (v0.3.0) URL dell'API Zernio (valore della spec ufficiale, confermato nel collaudo del ticket 05) |
| `INSTAGRAM_CARD_KEYWORD` | `CARTA` | (v0.3.0) parola chiave che il cliente scrive in DM al negozio |
| `ZERNIO_MONTHLY_SEND_LIMIT` | `10000` | (v0.3.0) invii gratuiti al mese per team Zernio (solo per l'avviso: è Zernio a fermare gli invii) |
| `ZERNIO_SEND_WARN_PERCENT` | `75` | (v0.3.0) soglia di avviso nel pannello del merchant |

Eliminate da v0.2.0 (cancellabili da DO): `MERCHANT_PASSWORD`. Storiche non più usate: `HUMANI_*`, `TELEGRAM_BOT_TOKEN`, `BASE_URL`, `DATABASE_PASSWORD`.

> ⚠️ **`ENCRYPTION_KEY` torna in v0.3.0 con un significato nuovo** (AES-256-GCM per le chiavi Zernio). Se su DigitalOcean
> è rimasta la vecchia chiave Fernet di v0.1.0, **sostituiscila con una generata da zero**: ha lo stesso formato e
> verrebbe accettata in silenzio. Lo stesso vale per `IGSID_HMAC_KEY` e `CARD_LINK_KEY`: tre valori nuovi e diversi.

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

- **Prima volta in assoluto**: prova con `ECOLOGI_TEST_MODE=true` (chiave di test + flag `test`, nessun addebito). Per la chiusura vera serve `ECOLOGI_TEST_MODE=false` e `ECOLOGI_API_KEY` reale.
- **Verifica della chiave reale prima della prima chiusura**: `ECOLOGI_TEST_MODE=false python -m scripts.ecologi_check` (console DigitalOcean, oppure in locale con la chiave reale nel `.env`). Fa una chiamata vera con `"test": true`: nessun addebito, nulla sul profilo Ecologi. Mostra il nome che comparirà nella foresta e il `treeUrl`; senza `ECOLOGI_TEST_MODE=false` prova invece la chiave di test.
- Considera solo i negozi **approvati** (`is_approved`). È **idempotente**: rilanciarlo non pianta due volte lo stesso negozio.
- Codici di uscita: `0` ok · `1` divergenze contatore/registro o cap sforato non autorizzato · `2` annullato · `3` almeno un negozio fallito (si ritenta rilanciando).
- Lo scan del merchant non pianta mai alberi: la piantumazione avviene solo qui.

## Collaudo locale (DB usa-e-getta)

`reset_db` e `seed_db` agiscono sul `DATABASE_URL` del `.env`: **se punta a Neon/Supabase cancellano i dati veri**.
Per il collaudo usa un SQLite su file, sovrascrivendo la variabile solo nel terminale (le env var vincono sul `.env`):

```powershell
$env:DATABASE_URL = "sqlite:///collaudo.db"     # file ignorato da git (*.db)
python -m scripts.reset_db --force
python -m scripts.seed_db --links                # stampa credenziali, id delle carte e link /c/<token> di prova
python local_main.py                             # http://127.0.0.1:8001
```

Per tornare al DB del `.env`: chiudi il terminale o `Remove-Item Env:DATABASE_URL`. Checklist completa: `pre-release.md`.

### Collaudo del flusso Instagram (v0.3.0)

Zernio deve raggiungere il server locale via https: si usa un tunnel rapido **cloudflared** (gratuito, nessun account).

```powershell
cloudflared tunnel --url http://127.0.0.1:8001        # stampa https://<nome>.trycloudflare.com
$env:PUBLIC_BASE_URL = "https://<nome>.trycloudflare.com"   # in un ALTRO terminale, prima di avviare il server
$env:DATABASE_URL = "sqlite:///collaudo.db"
python local_main.py
```

- Serve un account Instagram **Business o Creator** di prova collegato a un account Zernio gratuito, più due profili
  personali (uno che segue il negozio, uno no). Procedura completa nei ticket 05, 07 e 11 di v0.3.0.
- L'URL del tunnel rapido **cambia a ogni avvio**: dopo un riavvio del tunnel rifai l'onboarding del merchant
  (scollega/ricollega) così il webhook su Zernio punta al nuovo URL.
- `python -m scripts.zernio_check accounts` verifica la chiave senza toccare il DB; `python -m scripts.replay_webhook`
  rigioca un evento firmato verso il server locale (il server invierà davvero la card sulla conversazione indicata).

## Reset/seed del DB remoto (distruttivo!)

Solo se i dati sono sacrificabili (il seed richiede `AUTH_PROVIDER=dev`, quindi non è per la produzione vera).
In locale, con il `DATABASE_URL` remoto nel `.env`:

```bash
python -m scripts.reset_db      # chiede conferma (--force per saltare)
python -m scripts.seed_db       # solo con AUTH_PROVIDER=dev
```
