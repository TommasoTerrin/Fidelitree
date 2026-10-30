# Deploy — DigitalOcean App Platform + Neon

## Come funziona

- **Due ambienti, nessuno staging** (AGENTS.md «Ambienti»): locale = app avviata direttamente con `.env` su Neon `development`;
  produzione = app DO **`fidelitree`** (id `afc495df-7eb6-4da0-81f0-879446e1e710`, regione `fra`, `basic-xxs`, **1 istanza**,
  dominio `https://fidelitree.app`) su Neon `production` (progetto `still-firefly-21838974`).
- L'app builda il `Dockerfile` e fa **auto-deploy a ogni push su `main`** (con «Wait for CI» attivo DO aspetta prima la CI di
  GitHub; controllarlo nella console, impostazioni della sorgente GitHub del componente).
- Il container ascolta su `$PORT` (DO la imposta a 8080 = `http_port`), **un solo processo** uvicorn: il freno ai tentativi
  di login sta in memoria, quindi niente `--workers` né più istanze finché non passa su DB.
- **Health check** su `/health` (non tocca il DB) con 30 s di ritardo iniziale: all'avvio l'app crea le tabelle mancanti su Neon,
  che può essere sospeso.
- **Deploy fallito → DO torna da solo al deploy precedente** («automated rollback after failed deployment»): container che esce
  con errore o health check che non passa. Il sito resta sulla versione di prima.
- **Dipendenze fissate** in `requirements.txt` (`==`): senza versioni il build prendeva l'ultima release di tutto, e al primo
  deploy di v0.3.0 SQLAlchemy 2.1 ha rotto l'avvio (per `postgresql://` sceglie psycopg 3, non installato). La CI gira su SQLite
  e non lo vede: per aggiornarle vedi «Aggiornare le dipendenze».
- **Database**: Neon, endpoint **diretto** (host senza `-pooler`). L'app è un processo con il suo pool SQLAlchemy
  (5 connessioni, `pool_pre_ping`) e psycopg2: il pooler (PgBouncer in transaction mode) servirebbe con molti processi o istanze.
- Lo schema viene creato da `create_all()` all'avvio: crea **solo le tabelle mancanti**, non aggiunge colonne né modifica tabelle
  esistenti. **Dal 2026-10-30 in produzione ci sono dati veri: ogni modifica allo schema richiede prima uno script SQL/Alembic
  provato su un branch Neon, e un branch di backup** (AGENTS.md «Modifiche allo schema»).

## Env vars su DigitalOcean

**Dove**: a livello del **componente `fidelitree`**, non «App-Level Environment Variables». Se la stessa variabile esiste in
entrambi vince quella del componente (un vecchio `DATABASE_URL` sul componente scavalcherebbe quello nuovo dell'app).

**Come (consigliato)**: Settings → card **App Spec** → Edit, incollando lo spec intero. Nello spec ogni variabile ha
`scope: RUN_TIME`; quelle sensibili hanno `type: SECRET` e DO le **cifra al salvataggio** (poi compaiono come `EV[...]`, anche
in `doctl`). Lo spec sostituisce tutte le variabili del componente, quindi toglie anche le vecchie. In alternativa la console
del componente (editor in blocco): lì le variabili arrivano in chiaro, vanno cifrate e messe a «Run time» una per una e quelle
vecchie cancellate a mano.

> ⚠️ **Salvare lo spec o una variabile ridistribuisce subito il commit attivo**, anche con «Wait for CI». Prima del primo deploy
> di v0.3.0 il commit attivo era v0.1.0: il suo deploy è fallito (`MERCHANT_PASSWORD` mancante) e DO è tornato da solo al
> precedente, come atteso. **v0.1.0 stampa le variabili nel suo errore di validazione**: i log di quel deploy fallito
> (`98569d46`) contengono frammenti di segreti. v0.3.0 no (`hide_input_in_errors`).

> Una volta cifrato, `DATABASE_URL` non è più leggibile da `doctl`: l'host si verifica dopo il deploy registrando un negozio di
> prova e controllando su quale branch Neon compare.

Se ne manca una l'app **crasha all'avvio** (Settings pydantic con campi obbligatori):

| Variabile | Descrizione |
|---|---|
| `DATABASE_URL` | URL Postgres del branch **`production`**, endpoint **diretto**: `neon connection-string production --project-id still-firefly-21838974` (restituisce il diretto con `sslmode=require&channel_binding=require`; **non stamparlo**: passalo in una variabile o in un file temporaneo fuori da OneDrive) |
| `JWT_SECRET_KEY` | firma dei token di sessione. Generazione: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `ADMIN_SECRET_KEY` | chiave degli endpoint admin (`X-Admin-Key`) e **password della dashboard `/admin`**. Lunga (≥ 20 caratteri; anche una passphrase di parole a caso): l'header `X-Admin-Key` **non ha freno ai tentativi**. Vuota = accesso admin chiuso |
| `ENCRYPTION_KEY` | chiave AES-256-GCM, 32 byte in base64 urlsafe: cifra chiave Zernio e secret del webhook dei merchant |
| `IGSID_HMAC_KEY` | indice cieco dell'IGSID dei clienti. **Non ruotabile**: cambiarla scollega tutte le carte |
| `CARD_LINK_KEY` | deriva il token dei link delle carte; cambiarla invalida tutti i link già inviati |

Generazione delle tre chiavi a 32 byte (una per variabile, valori diversi):
`python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`.
Conserva tutte le chiavi anche fuori da DigitalOcean (password manager): perderle significa perdere le chiavi Zernio dei merchant
e il collegamento delle carte. Le chiavi di produzione sono **diverse** da quelle del `.env` locale.

Variabili **opzionali** (hanno un default):

| Variabile | Default | Descrizione |
|---|---|---|
| `ENVIRONMENT` | `development` | mettere `production` in produzione (con `AUTH_PROVIDER=dev` l'app **non parte**; il cookie di sessione diventa `Secure`) |
| `AUTH_PROVIDER` | `dev` | `dev` (solo locale/test), **`local`** (password nel nostro DB, **da usare in produzione**) o `supabase` (stub). Con `local` serve solo questa variabile: nessun'altra chiave (i token usano `JWT_SECRET_KEY`) |
| `DEV_AUTH_PASSWORD` | `dev-password` | **solo locale** (provider `dev`): password dei merchant creati dal seed. **Non impostarla in produzione** |
| `ECOLOGI_BASE_URL` | `https://public.ecologi.com` | URL dell'API Ecologi, **unico** per test e produzione (non esiste un sandbox: la prova è il flag `"test": true`) |
| `ECOLOGI_API_KEY` | vuota | chiave Ecologi **reale** di piattaforma (paga il founder); usata con `ECOLOGI_TEST_MODE=false` |
| `ECOLOGI_TEST_API_KEY` | vuota | chiave Ecologi **di prova**; usata con `ECOLOGI_TEST_MODE=true`. Nessun fallback tra le due chiavi |
| `ECOLOGI_TEST_MODE` | `true` | `true` = chiave di test + flag `test` (nessun addebito, nulla sul profilo Ecologi); `false` SOLO in produzione, con `ECOLOGI_API_KEY` |
| `ECOLOGI_GLOBAL_MONTHLY_CAP` | `20` | massimo alberi piantati in una chiusura mensile |
| `TIER_BRONZE_POINTS` / `TIER_SILVER_POINTS` / `TIER_GOLD_POINTS` | `100` / `300` / `600` | soglie di default dei livelli del pool (override per negozio nel DB) |
| `ENCRYPTION_KEY_ID` | `1` | id della chiave di cifratura salvato con ogni dato cifrato (rotazione futura) |
| `PUBLIC_BASE_URL` | `http://127.0.0.1:8001` | URL pubblico **https** dell'app: link delle carte e URL del webhook su Zernio. In produzione `https://fidelitree.app`. **Se cambia, i merchant devono rifare l'onboarding Instagram** (il webhook su Zernio punta al vecchio URL) |
| `ZERNIO_BASE_URL` | `https://zernio.com/api` | URL dell'API Zernio (valore della spec ufficiale, confermato nel collaudo del ticket 05) |
| `INSTAGRAM_CARD_KEYWORD` | `CARTA` | parola chiave che il cliente scrive in DM al negozio |
| `ZERNIO_MONTHLY_SEND_LIMIT` | `10000` | invii gratuiti al mese per team Zernio (solo per l'avviso: è Zernio a fermare gli invii) |
| `ZERNIO_SEND_WARN_PERCENT` | `75` | soglia di avviso nel pannello del merchant |
| `ZERNIO_CHECK_API_KEY` | vuota | **solo locale**, per `scripts.zernio_check` senza `--merchant-id`. Non serve in produzione |

**In produzione dal 2026-10-30** (10 variabili, tutte `RUN_TIME`): `ENVIRONMENT=production`, `AUTH_PROVIDER=local`,
`PUBLIC_BASE_URL=https://fidelitree.app`, `ECOLOGI_TEST_MODE=true` in chiaro; `DATABASE_URL`, `ENCRYPTION_KEY`, `IGSID_HMAC_KEY`,
`CARD_LINK_KEY`, `ADMIN_SECRET_KEY`, `JWT_SECRET_KEY` come `SECRET`. **Manca `ECOLOGI_TEST_API_KEY`** (serve a `ecologi_check` e
`close_period` dalla console, non all'avvio). Tolte dallo spec le variabili di v0.1.0: `HUMANI_*`, `TELEGRAM_BOT_TOKEN`,
`MERCHANT_PASSWORD`, `DATABASE_PASSWORD`, `BASE_URL`, `ECOLOGI_URL`, `ECOLOGI_SANDBOX_URL`, `ECOLOGI_SANDBOX_API_KEY`.

## Primo deploy di v0.3.0 (fatto il 2026-10-30)

Com'è andato davvero, in ordine. Vale anche come procedura per un ambiente nuovo.

1. **Collaudo in locale** su Neon `development` con tunnel, `ENVIRONMENT=production` e `AUTH_PROVIDER=local` (`collaudo.md`).
2. **Password del DB di produzione ruotata.** I branch Neon nati da `production` ereditano ruolo e password: `development` aveva la
   stessa password di `production`, ed era in chiaro su DO e nel `.env`. Il reset vale per un solo branch:
   `neon api /projects/still-firefly-21838974/branches/<id-branch>/roles/neondb_owner/reset_password -X POST`
   (la risposta contiene la password nuova: non stamparla). Il `.env` (development) non cambia.
3. **Env var su DO** con lo spec (sezione sopra). Il salvataggio ha ridistribuito v0.1.0, fallito, e DO è tornato al precedente.
4. **Backup e azzeramento di Neon `production`**, subito prima del merge su `main` (dopo il punto 3: se v0.1.0 fosse ripartito su
   `production` avrebbe potuto ricreare le sue tabelle):
   - backup: `neon branches create --project-id still-firefly-21838974 --name backup-pre-v0.3.0 --parent production --no-compute --no-secrets`;
   - azzeramento: `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` e poi `SQLModel.metadata.create_all(engine)`, con uno script
     usa-e-getta che riceve l'URL in una variabile d'ambiente, **verifica l'host atteso** (`ep-proud-darkness`) e non stampa l'URL.
     **Non `scripts.reset_db`**: fa `drop_all` delle sole tabelle del modello attuale, lascia le tabelle orfane delle versioni
     precedenti (`treecard`, `alembic_version`) e fallisce sulle loro chiavi esterne;
   - verifica: 8 tabelle (`authcredential`, `card`, `merchant`, `merchantpool`, `pointtransaction`, `processedwebhookevent`,
     `treeplanting`, `zerniosendcounter`), 0 righe, enum `webhookoutcome` con `SEND_UNCERTAIN`.
5. **PR e deploy**: `feature/instagram-cards` → `develop` (PR #2) → `main` (PR #3), CI verde a ogni passo. Il deploy di `956583c` è
   fallito all'avvio (`No module named 'psycopg'`, SQLAlchemy 2.1): corretto con le dipendenze fissate (PR #4 e #5), deploy riuscito
   su **`a83cd64`**, `/health` 0.3.0, log di avvio senza segreti. Tag **`v0.3.0`** su `a83cd64`.
6. **Dopo il deploy** (passi del founder):
   - smoke test (sotto, «Procedura di release»);
   - **verifica del login**: registra un negozio di prova e sbaglia la password: dal 3° errore la risposta avvisa, al 6° tentativo
     (anche con la password giusta) arriva 429 con l'invito a chiedere il reset; dopo 15 minuti si rientra;
   - **verifica della dashboard**: `https://fidelitree.app/admin`, accedi con `ADMIN_SECRET_KEY`; il negozio di prova compare «In
     attesa», «Avvia» lo rende «Attivo», «Metti in pausa» e «Riattiva» funzionano, «Reimposta password» mostra una password di 12
     caratteri una sola volta;
   - **DM in produzione**: collega Instagram al negozio di prova (`/merchant/settings`), `CARTA` da un profilo che segue → card →
     `https://fidelitree.app/c/<token>`;
   - **DB giusto**: il negozio di prova deve comparire su Neon `production` e non su `development` (prova che il `DATABASE_URL`
     cifrato punta al branch giusto);
   - negozio di prova: tenerlo come demo del founder, oppure scollegarlo ed eliminarlo (`DELETE /api/merchant/{id}` con `X-Admin-Key`,
     toglie anche la credenziale).
7. **Prima di dare il link ai pilota**: `/privacy` verificata (il testo è una bozza; DPA fuori scope); ai merchant una riga sul QR in
   negozio: per stamparlo contattano il founder, che lo prepara a mano da `https://ig.me/m/<username>`. Onboarding di ogni merchant
   con la **propria** chiave Zernio; il founder lo **avvia** dalla dashboard (finché non è avviato i clienti nuovi vedono la carta di prova).

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

1. **Collaudo manuale** in locale (`collaudo.md`) e checklist `pre-release.md`.
2. **Se cambia lo schema**: script SQL/Alembic provato su un branch Neon, e branch di backup di `production` subito prima del merge
   (vedi «Rollback»). Se cambiano le env var: spec DO aggiornato prima del merge (ricorda che il salvataggio ridistribuisce il commit attivo).
3. **PR** `feature/<nome>` → `develop` (`gh pr create --base develop`), CI verde, merge; poi PR `develop` → `main`, CI verde, merge:
   parte il deploy automatico. Nessun merge su `develop`/`main` senza l'ok esplicito del founder.
4. **Segui il deploy**: console DO, oppure `doctl apps list-deployments afc495df-7eb6-4da0-81f0-879446e1e710` (fasi
   `PENDING_BUILD` → `BUILDING` → `DEPLOYING` → `ACTIVE`). Se compare `automated rollback after failed deployment`, il deploy è
   fallito e il sito è rimasto com'era: leggi la causa con
   `doctl apps logs afc495df-7eb6-4da0-81f0-879446e1e710 --deployment <id> --type deploy` (senza incollare in chat righe con valori).
5. **Smoke test** con la chiave admin digitata nascosta (una riga per volta; lo script legge `ADMIN_SECRET_KEY` dall'ambiente se non
   gliela passi come argomento, così non finisce nella history):
   ```powershell
   $k = Read-Host "Chiave admin" -AsSecureString
   $env:ADMIN_SECRET_KEY = [Net.NetworkCredential]::new('', $k).Password
   python scripts/smoke_test_prod.py https://fidelitree.app
   Remove-Item Env:ADMIN_SECRET_KEY; Remove-Variable k
   ```
   Controlla versione, `/privacy`, `/carta-di-prova`, `/admin/login`, `/c/<inesistente>` 404, webhook con hook sconosciuto 404,
   manifest e service worker, pagine del vecchio flusso 404, API admin senza chiave rifiutata e con `X-Admin-Key` 200, creazione e
   cancellazione di un merchant di prova.
6. **Verifica il DB** (console Neon, branch `production`): le 8 tabelle presenti.
7. **Tag**, con l'ok del founder: `git tag -a vX.Y.Z <commit di main> -m "..."` e `git push origin vX.Y.Z` (stesso valore di `pyproject.toml`).
8. **Riallinea develop**: `git checkout develop`, `git merge --ff-only origin/main`, `git push`.

## Rollback

- **Deploy fallito**: non serve fare nulla, DO torna da solo al deploy precedente (successo due volte al primo deploy di v0.3.0).
- **Deploy riuscito ma con un bug grave** (codice):
  1. subito: console DO → **Activity / Deployments** → deploy precedente → **«Rollback»** (torna all'immagine di prima, senza build);
  2. poi: `git revert -m 1 <commit di merge su main>` su un branch, PR verso `main` e merge: senza questo il prossimo push su `main`
     ripubblica il bug. In alternativa al punto 1 basta il revert (nuovo deploy, qualche minuto di build).
- **Schema o dati** (git non basta: il codice torna indietro, il DB no):
  1. **prima** di ogni modifica allo schema, un branch di backup:
     `neon branches create --project-id still-firefly-21838974 --name backup-<AAAA-MM-GG> --parent production --no-compute --no-secrets`;
  2. per tornare indietro: `neon branches restore production backup-<AAAA-MM-GG> --preserve-under-name production-rotto --project-id still-firefly-21838974`
     (il branch `production` riprende i dati del backup, quello rotto resta come `production-rotto` per capire cosa è successo). Secondo
     la documentazione Neon il ripristino mantiene branch ed endpoint, quindi `DATABASE_URL` non cambia: **da provare la prima volta su
     un branch di prova** (per esempio `development` ripristinato da un suo backup);
  3. senza backup, un istante del passato: `neon branches restore production ^self@<timestamp ISO> --preserve-under-name production-rotto`
     (solo entro la finestra di cronologia del piano Neon);
  4. **codice e schema tornano indietro insieme**: un codice vecchio che si aspetta lo schema vecchio vuole anche il DB ripristinato
     (e i dati scritti dopo il backup si perdono).
- **Env var**: i valori `SECRET` di uno spec precedente non si rileggono dalla console: le chiavi stanno nel password manager. Un
  `IGSID_HMAC_KEY` o un `CARD_LINK_KEY` diversi scollegano le carte o invalidano i link.
- Backup esistenti: `backup-pre-v0.3.0` (resti del prototipo v0.1.0 prima dell'azzeramento del 2026-10-30, nessun dato di valore:
  si può eliminare).

## Aggiornare le dipendenze

Le versioni in `requirements.txt` sono fissate. Per aggiornarle:
1. nel venv: `pip install -U <pacchetti>` (SQLAlchemy resta `<2.1` finché il driver è psycopg2), poi `pip check`;
2. `python -m pytest`;
3. **avvio vero su Neon `development`**: `python -m scripts.run_collaudo`, poi `/health` e una pagina che legge il DB
   (`/admin` → lista dei merchant). La CI non lo fa: gira su SQLite;
4. riporta in `requirements.txt` le versioni installate (`pip show <pacchetto>`), PR: la CI ripete pytest, build Docker e pip-audit.

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

## Collaudo manuale

Procedura, regole e passi per feature: [collaudo.md](collaudo.md).

## Reset/seed di un DB (distruttivo!)

- **Mai su Neon `production`**: lì ci sono dati veri. Per lo schema vale «Modifiche allo schema = migrazione preparata prima».
- `scripts.reset_db` e `scripts.seed_db` agiscono sul `DATABASE_URL` del `.env` (Neon `development`) o su quello del terminale
  (SQLite usa-e-getta: `collaudo.md`). Il seed richiede `AUTH_PROVIDER=dev`.
- `reset_db` non elimina le tabelle che non sono nel modello attuale: per ripartire davvero da zero su un branch Neon serve
  `DROP SCHEMA public CASCADE; CREATE SCHEMA public;` e `create_all` (punto 4 di «Primo deploy di v0.3.0»).
