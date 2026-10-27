# Deploy — DigitalOcean App Platform + Neon

## Come funziona

- L'app su **DigitalOcean App Platform** builda il `Dockerfile` e fa **auto-deploy a ogni push su `main`**.
- Il container ascolta su `$PORT` (iniettata da DO; default 8000 in locale).
- Il database è **PostgreSQL** (Neon oggi, Supabase in un rilascio successivo): l'app lo raggiunge tramite `DATABASE_URL`.
- Lo schema viene creato da `create_all()` all'avvio: crea **solo le tabelle mancanti**. Non aggiunge colonne a una tabella già esistente, né la modifica o la elimina (verificato: su una tabella `merchant` creata prima, una colonna nuova come `is_paused` non compare). Un DB già creato con un modello precedente va resettato con `python -m scripts.reset_db`.

## Env vars richieste su DigitalOcean

Se ne manca una l'app **crasha all'avvio** (Settings pydantic con campi obbligatori):

| Variabile | Descrizione |
|---|---|
| `DATABASE_URL` | URL Postgres completo (`postgresql://...?sslmode=require`) |
| `JWT_SECRET_KEY` | firma dei token di sessione |
| `ADMIN_SECRET_KEY` | chiave per gli endpoint admin (`X-Admin-Key`) e **password della dashboard `/admin`**. Non lasciarla vuota: con un valore vuoto l'accesso admin resta chiuso |
| `ENCRYPTION_KEY` | (v0.3.0) chiave AES-256-GCM, 32 byte in base64 urlsafe: cifra chiave Zernio e secret del webhook dei merchant |
| `IGSID_HMAC_KEY` | (v0.3.0) indice cieco dell'IGSID dei clienti. **Non ruotabile**: cambiarla scollega tutte le carte |
| `CARD_LINK_KEY` | (v0.3.0) deriva il token dei link delle carte; cambiarla invalida tutti i link già inviati |

Generazione (una per variabile, valori diversi): `python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`.
Conservale anche fuori da DigitalOcean (password manager): perderle significa perdere le chiavi Zernio dei merchant e il collegamento delle carte.

Variabili **opzionali** (hanno un default), introdotte con v0.2.0:

| Variabile | Default | Descrizione |
|---|---|---|
| `ENVIRONMENT` | `development` | mettere `production` in produzione (con `AUTH_PROVIDER=dev` l'app **non parte**; il cookie di sessione diventa `Secure`) |
| `AUTH_PROVIDER` | `dev` | `dev` (solo locale/test), **`local`** (password nel nostro DB, **da usare in produzione**) o `supabase` (stub). Con `local` serve solo questa variabile: nessun'altra chiave (i token usano `JWT_SECRET_KEY`) |
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
| `ZERNIO_CHECK_API_KEY` | vuota | (v0.3.0) **solo locale**, per `scripts.zernio_check` senza `--merchant-id`: chiave Zernio di prova, letta dal `.env` o dall'ambiente (campo opzionale di `Settings`, mai stampato). Vuota = lo script la chiede a video. Non serve in produzione |

Eliminate da v0.2.0 (cancellabili da DO): `MERCHANT_PASSWORD`. Storiche non più usate: `HUMANI_*`, `TELEGRAM_BOT_TOKEN`, `BASE_URL`, `DATABASE_PASSWORD`.

> ⚠️ **`ENCRYPTION_KEY` torna in v0.3.0 con un significato nuovo** (AES-256-GCM per le chiavi Zernio). Se su DigitalOcean
> è rimasta la vecchia chiave Fernet di v0.1.0, **sostituiscila con una generata da zero**: ha lo stesso formato e
> verrebbe accettata in silenzio. Lo stesso vale per `IGSID_HMAC_KEY` e `CARD_LINK_KEY`: tre valori nuovi e diversi.

> ⚠️ **Schema v0.3.0**: `create_all()` non modifica le tabelle esistenti. Il passaggio al nuovo modello (email, pool, carte con indice cieco, webhook, `AuthCredential`, `Merchant.is_paused` e `Merchant.created_at`...) richiede il reset del DB (`python -m scripts.reset_db`): i dati di v0.1.0 non si migrano. **Anche un DB di sviluppo o di collaudo creato prima del ticket 12** (Neon di sviluppo, `collaudo*.db`) va resettato: senza le colonne nuove l'app dà errore alla prima lettura dei merchant. Vedi «Primo deploy di v0.3.0».

> **Accesso in produzione**: con `ENVIRONMENT=production` il provider `dev` non parte e `supabase` è uno stub, quindi si usa **`AUTH_PROVIDER=local`** (i merchant si registrano da `/merchant/register`, accedono e cambiano la password dalle impostazioni). Il founder li gestisce dalla dashboard **`/admin`** (password = `ADMIN_SECRET_KEY`): avvia (approva), mette in pausa, riattiva e reimposta le password (vedi «Procedure del founder»). Auth locale (ticket 11), stato del servizio (12) e dashboard (13) sono fatti: il primo deploy aspetta solo il collaudo end-to-end (ticket 14) e l'ok esplicito al merge.

## Primo deploy di v0.3.0 (ordine delle operazioni)

v0.3.0 è la prima release dopo v0.1.0: schema e variabili cambiano insieme. Ordine:

1. **Env var su DigitalOcean, prima del merge**: genera da zero `ENCRYPTION_KEY`, `IGSID_HMAC_KEY` e `CARD_LINK_KEY` (tre valori diversi, comando sopra) e salvale nel password manager; imposta `PUBLIC_BASE_URL` = dominio https di produzione, `ENVIRONMENT=production`, **`AUTH_PROVIDER=local`**; lascia `DEV_AUTH_PASSWORD` non impostata. Senza le tre chiavi l'app non parte; la vecchia `ENCRYPTION_KEY` Fernet va sostituita.
2. **Reset del DB di produzione** (distruttivo: i dati di v0.1.0 non si migrano). In locale, in un terminale dedicato e solo dopo aver controllato **a quale DB punta**:
   ```powershell
   $env:DATABASE_URL = "<URL Postgres di produzione>"    # solo in questo terminale
   python -m scripts.reset_db                             # chiede conferma
   Remove-Item Env:DATABASE_URL
   ```
   Il seed non è per la produzione (richiede `AUTH_PROVIDER=dev`). Eventuali tabelle di versioni precedenti non più nel modello (per esempio `customer`) restano nel DB come orfane, innocue: si possono eliminare a mano dalla console. Il reset lascia l'app vecchia senza schema valido fino al deploy: fallo subito prima del merge.
3. Procedura di release (sotto): merge su `main`, deploy, smoke test.
4. **Verifica del login (dopo il deploy)**: registra un negozio di prova e sbaglia la password: dal 3° errore la risposta avvisa del blocco, al 6° tentativo (anche con la password giusta) arriva 429 con l'invito a chiedere il reset al founder; dopo 15 minuti si rientra. Il freno è **per email** e il contatore sta in **memoria** (un solo processo: non impostare `--workers` né più istanze su DO finché non è spostato su DB; vedi roadmap).
4b. **Verifica della dashboard (dopo il deploy)**: apri `https://<app>/admin`, accedi con `ADMIN_SECRET_KEY` (in produzione il cookie è `Secure`: serve https), controlla che il negozio di prova del passo 4 compaia «In attesa» con nome ed email, «Avvia» lo rende «Attivo», «Metti in pausa» e «Riattiva» funzionano, «Reimposta password» mostra una password di 12 caratteri una sola volta; poi elimina il negozio di prova (API admin: `DELETE /api/merchant/{id}` con `X-Admin-Key`, che toglie anche la sua credenziale). Lo smoke test controlla già `/admin/login` e l'API admin.
5. **Onboarding dei merchant pilota**: ogni merchant, dalle impostazioni, incolla la **propria** chiave Zernio e sceglie il suo account Instagram; il DM di prova collega Instagram, e il founder lo **avvia** dalla dashboard (finché non è avviato i clienti nuovi vedono la carta di prova). Zernio deve poter raggiungere `PUBLIC_BASE_URL`. Se `PUBLIC_BASE_URL` cambia, ogni merchant deve rifare l'onboarding (scollega/ricollega): il webhook su Zernio punta al vecchio URL.
6. **`/privacy`**: il testo è una bozza; il founder la fa verificare (e prepara il DPA, fuori scope) prima di dare il link ai primi clienti.
7. **Istruzioni ai merchant, una riga sul QR in negozio**: per stampare un QR che apre la chat, contattare il founder, che lo prepara a mano da `https://ig.me/m/<username>`.

## Procedure del founder (dashboard `/admin`)

**Accesso**: apri `https://<app>/admin` (in locale `http://127.0.0.1:8001/admin`) e inserisci `ADMIN_SECRET_KEY`. La sessione dura 12 ore; «Esci» è in alto a destra.
Dopo 5 password sbagliate in 15 minuti il form si ferma per 15 minuti (il contatore è uno solo e in memoria: lo stesso limite vale per chiunque provi, quindi
può scattare anche senza colpa tua; si azzera da solo, o al riavvio dell'app). In quel caso, o per uno script, usa l'API con l'header:
`curl -H "X-Admin-Key: <chiave>" https://<app>/admin/api/merchants` (la chiave non va incollata in chat, in un ticket o in un log). Per non esporre la chiave nella
history della shell, mettila in una variabile d'ambiente del terminale.

**Iscrizione di un nuovo merchant**
1. Mandagli il link `https://<app>/merchant/register` (nome attività al massimo 80 caratteri, perché è il titolo della card; telefono facoltativo con `+39`).
2. Il merchant si iscrive, accede e collega il suo Instagram dalle impostazioni con la propria chiave Zernio. Finché non lo avvii è **«In attesa»**: può fare la prova,
   ma i suoi clienti nuovi vedono la carta di prova (`/carta-di-prova`) e lo scanner può solo togliere saldo.
3. Ti scrive (per esempio su WhatsApp). In `/admin` lo trovi in cima alla lista (dai più recenti), con nome attività, email e telefono; controlla che l'Instagram sia
   «Collegato con Zernio» (o «in attesa del DM di prova») e premi **«Avvia»**: da quel momento è **«Attivo»**.
4. Dagli le istruzioni (testo sotto).

**Password dimenticata** (anche dopo un «Accesso sospeso»)
1. Il merchant ti scrive. In `/admin` cercalo per nome o email e premi **«Reimposta password»**, poi conferma.
2. Appare la **password temporanea** (12 caratteri, senza caratteri ambigui): copiala con «Copia» e comunicala a mano, su un canale privato. **Si vede una sola volta**:
   se chiudi il riquadro senza averla copiata, rifai il reset (quella vecchia non vale comunque più).
3. Il reset annulla la vecchia password e le sessioni aperte del merchant e sblocca il suo accesso. Il merchant entra con la temporanea e la cambia da
   Impostazioni → «Cambia password».
4. Il pulsante è grigio per i merchant creati dall'API admin: non hanno una password (si risolve con Supabase).

**Prova finita / abbonamento non pagato**
- **«Metti in pausa»**: il merchant vede il banner «Servizio in pausa» e non può aggiungere punti né cashback, ma può toglierli; il **cliente non vede nessuna differenza**
  (la pagina carta resta com'è). La chiusura mensile conta ancora i punti raccolti prima (conta `is_approved`).
- **«Riattiva»**: quando il merchant ha pagato; torna «Attivo». «Metti in pausa» e «Riattiva» valgono solo per un negozio già avviato: su uno «In attesa» danno un errore (usa «Avvia»).

**Testo da dare ai merchant** (bozza, da adattare)
- *Dopo l'avvio*: «Il tuo Fidelitree è attivo. I tuoi clienti ricevono la carta scrivendo CARTA in DM al tuo Instagram (anche dal menu «🌳 La mia carta»). Per aggiungere punti
  apri `https://<app>/merchant/scanner` dal telefono, installa l'app («Aggiungi a schermata Home») e inquadra il QR che il cliente ha sulla carta. Se dimentichi la password
  scrivimi: te la reimposto io. Per stampare un QR che apre la chat, contattami: lo preparo io.»
- *In pausa*: «Il servizio è in pausa: puoi ancora togliere punti e cashback già presenti, ma non aggiungerne. Scrivimi per riattivarlo.»

## Procedura di release

1. Completa la checklist `.agents/checklists/pre-release.md` e i passi 1-2 di «Primo deploy di v0.3.0» (solo la prima volta).
2. `git checkout main && git merge develop && git push` → parte il deploy automatico.
3. Attendi il deploy dalla console DO (build + health check su `/health`).
4. Smoke test: `python scripts/smoke_test_prod.py https://<app>.ondigitalocean.app <ADMIN_SECRET_KEY>` (controlla versione `0.3.0`, `/privacy`, `/carta-di-prova`, `/admin/login`, `/c/<inesistente>` 404, webhook con hook sconosciuto 404, manifest e service worker, pagine del vecchio flusso 404, API admin senza chiave 403, `/admin/api/merchants` 401 senza credenziali e 200 con `X-Admin-Key`).
5. Verifica il DB (console Neon/Supabase → tabelle `merchant`, `authcredential`, `card`, `pointtransaction`, `merchantpool`, `treeplanting`, `processedwebhookevent`, `zerniosendcounter` presenti).
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
python -m scripts.seed_db --links                # stampa credenziali, id delle carte e (con --links) link /c/<token> di prova
python local_main.py                             # http://127.0.0.1:8001
```

Per tornare al DB del `.env`: chiudi il terminale o `Remove-Item Env:DATABASE_URL`. Checklist completa: `pre-release.md`.

### Collaudo end-to-end del flusso Instagram (v0.3.0)

Zernio deve raggiungere il server locale via https: si usa un tunnel rapido **cloudflared** (gratuito, nessun account;
installazione: `winget install --id Cloudflare.cloudflared`). Servono: un account Instagram **Business o Creator** di
prova (il "negozio") collegato a un account Zernio gratuito; un profilo personale **A** che **segue** il negozio e uno
**B** che **non** lo segue; uno smartphone (PWA e Instagram mobile); ManyChat scollegato dal negozio (salvo il passo 9).
Tre terminali PowerShell nella root del progetto. **Mai** incollare in chat chiavi, token dei link, IGSID o testo dei
messaggi: negli esiti si scrive solo «ok/non ok» e i numeri misurati.

**Passo 1 — tunnel, DB usa-e-getta, server con log**

```powershell
# Terminale 1: tunnel. Copia l'URL https://<nome>.trycloudflare.com stampato (cambia a ogni avvio)
cloudflared tunnel --url http://127.0.0.1:8001
```

```powershell
# Terminale 2: server. Le env var del terminale vincono sul .env: il DB vero NON viene toccato
$env:DATABASE_URL = "sqlite:///collaudo11.db"
$env:PUBLIC_BASE_URL = "https://<nome>.trycloudflare.com"
python -m scripts.reset_db --force
python -c "import logging,sys; h=logging.StreamHandler(sys.stdout); h.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d %(name)s %(message)s')); a=logging.getLogger('app'); a.setLevel(logging.INFO); a.addHandler(h); import uvicorn; uvicorn.run('app.main:app', host='127.0.0.1', port=8001)" | Tee-Object -FilePath collaudo11.log
```

Il comando `python -c` avvia lo stesso `app.main:app` di `local_main.py` (senza hot-reload) ma mostra anche i log
`info` dell'app con l'ora (`local_main.py` mostra solo quelli di uvicorn) e li copia in `collaudo11.log` (ignorato da
git). Prima di lanciare gli script, nel **terminale 3** imposta lo stesso `$env:DATABASE_URL = "sqlite:///collaudo11.db"`
(gli script `--merchant-id` leggono il DB da lì) e verifica con `$env:DATABASE_URL` che non punti a Neon.

**Passo 2 — registrazione e onboarding**: nel browser apri `http://127.0.0.1:8001/merchant/register`, registra un
negozio (nome ≤ 80 caratteri: è il titolo della card), poi `/merchant/settings` → sezione Instagram: incolla la tua
chiave Zernio, «COLLEGA ZERNIO», scegli l'account, «COLLEGA ACCOUNT». Controlla: il pannello passa allo stato «in attesa del DM di prova»; su Zernio
(dashboard) compare un webhook con URL `<tunnel>/webhooks/zernio/…`; nella chat del negozio su Instagram (mobile)
compare il menu «🌳 La mia carta». Poi, nel terminale 3: `python -m scripts.zernio_check conversations --merchant-id 1`
(stampa lo stato del negozio con la chiave mascherata e le conversazioni: `id  data`).

**Passo 2b — approva il negozio** (dal ticket 12): un negozio appena registrato è «in attesa», quindi il DM `CARTA` di un cliente nuovo porta alla **carta di prova** (`/carta-di-prova`), non a `/c/<token>`, e lo scanner non aggiunge nulla. Per provare la carta vera avvia il negozio dalla dashboard: apri `http://127.0.0.1:8001/admin`, accedi con `ADMIN_SECRET_KEY` del tuo `.env` (non incollarla in chat né nei log) e premi «Avvia» (in alternativa `POST http://127.0.0.1:8001/api/merchant/1/approve` con l'header `X-Admin-Key`). Se vuoi provare anche la carta di prova, fai prima il passo 3 **senza** approvare: deve aprirsi `/carta-di-prova` con l'etichetta «CARTA DI PROVA», senza QR e senza dati; poi approva e riscrivi `CARTA`.

**Passo 3 — DM da un follower**: da **A** scrivi `CARTA` al negozio. Annota l'ora sul telefono in cui invii, l'ora
della riga `Webhook: negozio=1 evento=… esito=sent` nel terminale 2 e l'ora in cui la card compare sul telefono (per
la latenza). Tocca «Apri la carta» (il link passa dal tunnel): deve aprirsi `/c/<token>` con i punti a 0 e il QR. Il
pannello del negozio passa allo stato «attivo». Sul telefono del merchant apri `<tunnel>/merchant/login`, accedi, installa la
PWA (menu del browser → «Aggiungi a schermata Home»), apri lo **scanner**, inquadra il QR della pagina carta
(mostrata su un altro schermo), aggiungi **60 tree points**: toast di conversione; ricarica la pagina carta: punti e
cashback nuovi.

**Passo 4 — voce di menu**: da **A**, nella chat del negozio tocca «🌳 La mia carta»: arriva la stessa card con lo stesso
link (riga di log `esito=sent`; se non arriva nulla annota anche se compare una riga di log).

**Passo 5 — non follower**: da **B** scrivi `CARTA`. Annota: la riga di log (`esito=follow_requested` = `isFollower`
falso, testo di invito consegnato; `sent`/`fallback_sent` = la card è partita, quindi `isFollower` era `true`/`null`;
nessuna riga = il webhook non è arrivato, per esempio DM in **Requests**: guarda anche i tentativi di consegna del
webhook nella dashboard Zernio, se li mostra), dove compare il messaggio su Instagram (Generale o Requests) e se la
risposta è arrivata. Poi **B segue il negozio** e riscrive `CARTA` subito dopo (se arriva ancora l'invito, riprova dopo
uno-due minuti e annota il ritardo di `isFollower`): deve arrivare la card. Se la dashboard Zernio mostra i payload
consegnati, annota il valore di `isFollower` visto (`true`, `false`, `null` o assente).

**Passo 6 — evento duplicato** (terminale 3; usa un `conversation.id` di `zernio_check conversations --merchant-id 1`,
è quello della chat di **A**; il server proverà un invio **vero** su quella chat):

```powershell
python -m scripts.replay_webhook --merchant-id 1 --conversation-id <ID> --follower si --event-id collaudo-dup-1
python -m scripts.replay_webhook --merchant-id 1 --conversation-id <ID> --follower si --event-id collaudo-dup-1
```

Atteso: entrambe `HTTP 200`, **una sola** card in arrivo sul telefono di A, nel log una riga `evento già visto`. Altre
prove con lo stesso comando (ogni volta un `--event-id` nuovo): senza `--follower` (`isFollower` assente → card),
`--follower no` (invito), `--standby` (esito `standby` e avviso nel pannello del negozio), `--hours-ago 25` (esito
`out_of_window`, nessun invio).

**Passo 7 — controllo dei log** (a fine collaudo, nel terminale 3):

```powershell
Select-String -Path collaudo11.log -Pattern "/c/|/webhooks/zernio/"     # solo /c/*** e /webhooks/zernio/***
Select-String -Path collaudo11.log -Pattern "sk_|zrk_|igsid|Authorization|secret"   # nessun risultato
```

In più cerca nel log il testo che un cliente ha scritto e, se la conosci, la parte finale del token del tuo link:
non devono comparire. Il log mostra solo id del negozio, id dell'evento ed esito.

**Passo 8 — «Scollega»**: dal pannello, «Scollega»: il webhook sparisce dalla dashboard Zernio (la voce di menu resta
su Instagram, è atteso); il pannello torna al form di collegamento; una nuova `CARTA` non riceve risposta. Se vuoi
ripetere il collaudo, ricollega (nuovo webhook) o riparti dal passo 1.

**Passo 9 — ManyChat/standby (facoltativo)**: collega ManyChat (o un'altra app di messaggistica) all'account del
negozio, imposta il negozio come in passo 2 e scrivi `CARTA` da **A**: annota se la card parte, se la riga di log è
`esito=standby`, e se il pannello mostra l'avviso sull'altra app. Poi scollega ManyChat.

Esiti nel [log del collaudo](../architecture/zernio-notes.md) (tabella «Collaudo finale del ticket 14»). Il tunnel rapido
cambia URL a ogni avvio: dopo un riavvio del tunnel riavvia il server con il nuovo `PUBLIC_BASE_URL` e rifai l'onboarding.
A fine collaudo: chiudi i terminali (le env var spariscono) ed elimina `collaudo11.db` e `collaudo11.log`.

## Reset/seed del DB remoto (distruttivo!)

Solo se i dati sono sacrificabili (il seed richiede `AUTH_PROVIDER=dev`, quindi non è per la produzione vera).
In locale, con il `DATABASE_URL` remoto nel `.env`:

```bash
python -m scripts.reset_db      # chiede conferma (--force per saltare)
python -m scripts.seed_db       # solo con AUTH_PROVIDER=dev
```
