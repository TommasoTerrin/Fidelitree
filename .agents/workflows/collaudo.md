# Collaudo manuale prima del deploy

Il collaudo manuale si fa **in locale, prima di ogni merge su `main` che cambia il codice**: app avviata direttamente
(non in Docker) su Neon `development`, con un tunnel https per Instagram/Zernio e il telefono. I test automatici non
lo sostituiscono: girano su SQLite e non vedono Postgres, Instagram, il browser e la PWA.

**Come si aggiorna**: ogni feature (o ticket) aggiunge **una sezione in fondo** con i suoi passi: URL, cosa fare, cosa
ci si aspetta. La parte fissa (setup, regole, chiusura) non si ripete. La checklist `pre-release.md` rimanda qui.

## Parte fissa

### Regole

- **Mai** incollare in chat, ticket o log: chiavi, password, token dei link, IGSID, URL del DB, testo dei messaggi dei
  clienti. Negli esiti si scrive solo **ok / non ok** e i tempi misurati.
- **Comandi su una riga, uno alla volta.** Un blocco su più righe incollato in PowerShell arriva spezzato (`IndentationError`
  in un `python -c`, percorsi lunghi tagliati a metà). Per questo il server si avvia con uno script e non con un `python -c`.
- **Nel browser si usa sempre l'URL del tunnel**, non `127.0.0.1`: con `ENVIRONMENT=production` i cookie sono `Secure`, e così
  si prova anche il controllo `Origin`/`Host` dietro un proxy come su DigitalOcean.

### Setup: tre terminali PowerShell nella root del progetto

**Terminale 1, tunnel** (`winget install --id Cloudflare.cloudflared` se manca):
```powershell
cloudflared tunnel --url http://127.0.0.1:8001
```
Copia l'URL `https://<nome>.trycloudflare.com`. Cambia a ogni avvio del tunnel: in quel caso riavvia il server con il nuovo
`PUBLIC_BASE_URL` e rifai l'onboarding Zernio (il webhook punta al vecchio URL).

**Terminale 2, server** (una riga per volta):
```powershell
.venv\Scripts\activate
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
$env:ENVIRONMENT = "production"
$env:AUTH_PROVIDER = "local"
$env:PUBLIC_BASE_URL = "https://<nome>.trycloudflare.com"
python -m scripts.run_collaudo | Tee-Object -FilePath collaudo.log
```
Il DB è quello del `.env`, cioè Neon `development`. `scripts.run_collaudo` stampa `DB: ep-morning-credit-…` e **si rifiuta** con
qualsiasi altro DB (in particolare `production`). `collaudo.log` è ignorato da git.

Variante con un SQLite usa-e-getta (per non toccare nemmeno `development`): prima del server
`$env:DATABASE_URL = "sqlite:///collaudo.db"` e `python -m scripts.reset_db --force`. `reset_db` **solo** su SQLite o `development`,
mai su `production`.

**Terminale 3, script** (`zernio_check`, `replay_webhook`):
```powershell
.venv\Scripts\activate
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
```
(con la variante SQLite imposta qui lo stesso `$env:DATABASE_URL`).

Neon sospende la macchina dopo ~5 minuti senza richieste: il primo DM dopo una pausa misura anche il risveglio (il webhook
deve rispondere entro 5 s).

### Chiusura

1. **«Scollega»** Instagram dal pannello del merchant: altrimenti Zernio continua a chiamare l'URL del tunnel, che sparisce.
2. **Controllo dei log** (terminale 3), prima di fermare il server:
   ```powershell
   Select-String -Path collaudo.log -Pattern "/c/|/webhooks/zernio/"
   Select-String -Path collaudo.log -Pattern "sk_|zrk_|igsid|Authorization|secret|scrypt"
   ```
   La prima riga deve mostrare solo `/c/***` e `/webhooks/zernio/***`; la seconda nessun risultato. Cerca anche, digitandoli
   solo nel terminale, l'eventuale password temporanea e la parte finale di un token di link: nessun risultato.
3. Chiudi i terminali (le env var spariscono), cancella `collaudo.log` (e `collaudo.db`).
4. Scrivi gli esiti nel ticket o in `.agents/architecture/zernio-notes.md` (flusso Instagram).

---

## v0.3.0 — carta via DM Instagram (Zernio)

**Serve**: un account Instagram **Business o Creator** di prova (il «negozio») collegato a un account Zernio gratuito; un
profilo **A** che segue il negozio e uno **B** che non lo segue; uno smartphone; ManyChat scollegato dal negozio.

URL (sempre con il prefisso del tunnel `https://<nome>.trycloudflare.com`):

| Cosa | Percorso |
|---|---|
| Controllo del server | `/health` |
| Registrazione / login merchant | `/merchant/register`, `/merchant/login` |
| Impostazioni (Instagram/Zernio) | `/merchant/settings` |
| Scanner (dal telefono) | `/merchant/scanner` |
| Dashboard admin | `/admin` (password = `ADMIN_SECRET_KEY` del `.env`, digitata a mano) |
| Carta di prova / carta del cliente | `/carta-di-prova`, `/c/<token>` (il link arriva nella card) |

0. **Server**: `/health` → `"status": "ok"`, versione attesa. Un 502 del tunnel vuol dire server non avviato.
1. **Registrazione**: `/merchant/register`, nome attività ≤ 80 caratteri (è il titolo della card).
2. **Onboarding Zernio**: `/merchant/settings` → incolla la chiave Zernio, «COLLEGA ZERNIO», scegli l'account, «COLLEGA ACCOUNT».
   Atteso: pannello «in attesa del DM di prova»; su Zernio un webhook `<tunnel>/webhooks/zernio/…`; nella chat del negozio
   il menu «🌳 La mia carta». Terminale 3: `python -m scripts.zernio_check conversations --merchant-id 1` (annota l'`id` della chat di A).
3. **Negozio in attesa**: dopo 5-6 minuti di pausa, da A scrivi `CARTA` → il link porta a `/carta-di-prova` (senza QR né dati).
4. **Avvio**: `/admin` → il negozio è «In attesa» con nome ed email → «Avvia» → «Attivo».
5. **Carta vera**: da A `CARTA` → card; «Apri la carta» → `/c/<token>` con punti a 0 e QR. Sul telefono del merchant
   `/merchant/login`, installa la PWA («Aggiungi a schermata Home»), `/merchant/scanner`, inquadra il QR, **+60 tree points**:
   toast di conversione; ricaricando la carta, punti e cashback aggiornati.
6. **Voce di menu**: tocca «🌳 La mia carta» → stessa card, stesso link (bug aperto: il tocco può non produrre eventi).
7. **Non follower**: da B `CARTA` → solo l'invito a seguire (`esito=follow_requested`); il primo DM di un non follower può
   arrivare dopo minuti (cartella Richieste). Poi B segue e riscrive → card.
8. **Evento duplicato** (facoltativo, invio vero): due volte
   `python -m scripts.replay_webhook --merchant-id 1 --conversation-id <ID> --follower si --event-id collaudo-dup-1` → entrambe
   `HTTP 200`, una sola card, nel log `evento già visto`.
9. **Pausa**: `/admin` → «Metti in pausa» → nello scanner banner e pulsanti di aggiunta grigi (togliere funziona), pagina carta
   identica; «Riattiva».
10. **Freno al login**: in una finestra anonima, `/merchant/login` con 6 password sbagliate → avviso dal 3°, 429 al 6°.
11. **Reset password**: `/admin` → «Reimposta password» → «Copia» (si vede una volta); con la temporanea si entra, con la vecchia no,
    la sessione aperta decade; poi Impostazioni → «Cambia password». Il reset sblocca anche il freno del passo 10. «Esci» dalla dashboard.
12. **Scollega** e controllo dei log (parte fissa, «Chiusura»).

**Esiti**: 2026-10-28 su SQLite usa-e-getta (tabella «Collaudo finale del ticket 14» in `zernio-notes.md`). 2026-10-30 su
Neon `development` con `ENVIRONMENT=production`: ok secondo il founder; dal log registrazione, onboarding, carta di prova,
«Avvia», 3 card `sent`, `/c/***` aperta, pausa, 429, reset password e «Scollega» (200), 0 segreti e 0 errori 5xx.
Non confermati dal log: «Riattiva», cambio password, evento duplicato con `replay_webhook`.
