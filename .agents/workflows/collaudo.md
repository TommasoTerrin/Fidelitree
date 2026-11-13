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

## v0.4.1 — campagne

> Aggiunti dal ticket 02 (dashboard admin). Altri passi (webhook, commenti, scanner) arrivano con i ticket 03-05.

1. `/admin` → «Campagne» di un negozio attivo → crea `NATALE` (testo, importo 2,50 €, nessun limite): compare «attiva»
   con contatori a 0.
2. Crea una seconda campagna `natale!` → errore 409 leggibile; crea `CARTA` → 409; nome di 2 caratteri → 400.
3. Modifica importo e limite; «Archivia» → «archiviata»; «Ripristina» → «attiva»; «Elimina» → conferma → sparisce.
4. «Metti in pausa» il negozio → le sue campagne risultano archiviate; «Riattiva» → restano archiviate.

> Aggiunti dal ticket 03 (webhook dei DM). Su un negozio attivo con la campagna `NATALE` (passo 1 sopra), con
> `python -m scripts.replay_webhook` o con un DM vero.

5. `--text NATALE` → DM con la promo e la riga «Per utilizzare questa offerta devi avere la nostra carta fedeltà…»; in
   `/admin` richieste da DM = 1.
6. `--text "natale!!"` → stessa risposta; `--text "natale per me"` → nessuna risposta, contatore invariato.
7. Campagna con limite 1 e una richiesta già contata → `--text NATALE` → «Le offerte disponibili sono terminate…».
8. Campagna archiviata o negozio in pausa → nessuna risposta, contatori invariati.
9. `--text CARTA` → la card di oggi, invariata.

> Aggiunti dal ticket 04 (commenti), da fare con Instagram vero nel ticket 07.

10. «Scollega» e ricollega il profilo del negozio (sottoscrive `comment.received`).
11. Da un profilo cliente commenta `NATALE` sotto un post → arriva un DM con la promo; sotto il post nessuna risposta
    pubblica; in `/admin` richieste da commento = 1.
12. Commenta `CARTA` → DM «Per ricevere la tua carta scrivici CARTA qui in chat»; poi DM `CARTA` → card di oggi.
13. Commenta `NATALE` una seconda volta dallo stesso profilo → seconda risposta privata (un commento nuovo è una richiesta nuova).
14. Da un profilo che **non segue** il negozio: commento `NATALE` → DM consegnato? (esito in `zernio-notes.md`).

> Aggiunti dal ticket 05 (scanner «Applica»), da fare nel ticket 07. Negozio attivo con la campagna `NATALE` (2,50 €) e una seconda
> campagna senza importo; si prova dal telefono (PWA) o dal browser, dopo aver scansionato una carta.

15. Pagina di gestione della carta → in fondo i bottoni «Applica NATALE (+2,50 €)» e «Applica <nome>».
16. «Applica NATALE» → finestra di conferma con l'etichetta → «ANNULLA»: nulla cambia, nessuna richiesta.
17. «Applica NATALE» → «SÌ, CONFERMO» → toast «Accreditati € 2.50 di cashback», dopo l'aggiornamento il cashback è
    +2,50 €; in `/admin` utilizzi = 1.
18. «Applica» sulla campagna senza importo → cashback invariato, toast «Campagna applicata», utilizzi +1.
19. Negozio senza campagne (o con tutte archiviate) → pagina come prima, nessun blocco di bottoni.
20. Negozio in attesa con campagne: «Applica» con importo disattivato e banner; quello senza importo resta attivo.
21. `/c/<token>` della carta → mostra solo il nuovo saldo cashback; livello e alberi invariati.

> Aggiunti dal ticket 06 (completamento della sezione). Si fanno nel ticket 07, insieme ai passi 10-21.

22. **Risposta a una storia**: dal profilo cliente rispondi alla storia del negozio scrivendo `NATALE` → arriva il DM con la
    promo (stessa risposta del passo 5); in `/admin` richieste da DM +1. Se non arriva nulla il payload di Zernio per le
    storie è diverso da quello atteso (`message.received` con `metadata.storyReply`): **fermati e chiedi**, esito in
    `zernio-notes.md`.
23. **Commento senza Instagram** (prova locale del flusso, con il server avviato e un negozio attivo con `NATALE`):
    `python -m scripts.replay_webhook --merchant-id 1 --comment NATALE` → `HTTP 200` ed esito `sent` (o l'esito di
    errore di Zernio, perché `post-id` e `comment-id` finti non esistono: l'invio è comunque **vero**, quindi lo si fa solo
    per vedere il giro del server). Con `--comment CARTA` l'invito a scrivere `CARTA`; con `--comment "natale per me"`
    nessuna risposta (`ignored`). `--post-id` e `--comment-id` si possono fissare, e con `--event-id` uguale due volte si
    prova il retry (un solo invio). Non sostituisce i passi 10-14, che provano anche la consegna di Meta.
24. **Log**: dopo i passi 5-23 la «Chiusura» (controllo dei log) non deve trovare né il testo di un commento, né
    il testo delle promo, né id di commento o di post: nel log compaiono solo id della campagna e canale.
25. **«Scollega» e ricollega** alla fine: dopo il ricollegamento il webhook su Zernio ha di nuovo gli eventi
    `message.received` e `comment.received` (passo 10).
