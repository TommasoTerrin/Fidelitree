# 11 — Documentazione, collaudo end-to-end e release

## Obiettivo
Documentazione allineata al codice reale di v0.3.0, collaudo completo con un account Instagram Business di test via
tunnel, e progetto pronto al merge. **Nessun merge su `develop` né su `main` senza l'ok dell'utente.**

## Contesto
Durante l'analisi (2026-10-22) AGENTS.md, overview, roadmap, `.env.example` e deploy.md sono stati scritti per la
versione **target**, con un banner di transizione. Qui si tolgono i banner e si corregge tutto ciò che
l'implementazione ha cambiato.

## Dipendenze
Tutti.

## Modifiche
1. **AGENTS.md**:
   - via il banner "in sviluppo";
   - versione corrente v0.3.0;
   - verifica di "Come funziona", mappa del codice, comandi e "Vincoli e trade-off" contro il codice reale.
2. **`.agents/architecture/overview.md`**: via il banner; endpoint, modello dati e flussi verificati.
3. **`.agents/architecture/zernio-notes.md`**: esiti dei collaudi 05 e 07, nessuna riga "non verificato" rimasta tra
   quelle che il collaudo poteva chiudere.
4. **`.agents/workflows/deploy.md`**:
   - nuove env var su DigitalOcean **prima** del deploy. `ENCRYPTION_KEY`, `IGSID_HMAC_KEY` e `CARD_LINK_KEY` vanno
     **generate da zero**: la vecchia `ENCRYPTION_KEY` Fernet di v0.1.0 ha lo stesso formato e verrebbe accettata;
   - `PUBLIC_BASE_URL` = dominio di produzione;
   - reset del DB di produzione (i dati v0.1.0 non si migrano);
   - collaudo locale con cloudflared;
   - i merchant devono rifare l'onboarding se cambia `PUBLIC_BASE_URL`.
5. **`.agents/checklists/pre-release.md`**: voci per l'onboarding con una chiave Zernio vera, il DM di prova, la card
   su mobile, la pagina carta, lo scan, `zernio_check`, `/privacy` verificata dal founder e l'assenza di segreti nei log
   di DigitalOcean (a parte quelli di piattaforma, accettati).
6. **Planner**:
   - in `current.md` v0.3.0 è "pronta al merge", e il punto "merge v0.2.1" diventa "assorbito da v0.3.0";
   - changelog in `roadmap.md`.
7. **README** del repo, se descrive ancora il wallet o l'OTP.
8. **QR in negozio**: nelle istruzioni ai merchant una sola riga: per stampare un QR che apre la chat, contattare il
   founder (lo prepara a mano da `https://ig.me/m/<username>`).

## Collaudo end-to-end (a cura del founder, documentato in deploy.md)
1. SQLite usa-e-getta: `reset_db --force`, server locale, `cloudflared tunnel --url http://127.0.0.1:8001` e
   `PUBLIC_BASE_URL` = URL del tunnel. L'URL cambia a ogni avvio del tunnel rapido: in quel caso l'onboarding va rifatto.
2. Registrazione del merchant e onboarding con la propria chiave Zernio. Su Zernio compaiono il webhook e la voce di
   menu.
3. DM "CARTA" da un profilo che segue il negozio → card in meno di qualche secondo → link → pagina carta → scan dalla
   PWA merchant (installata sul telefono) → +punti → la pagina mostra i punti nuovi.
4. Voce di menu "🌳 La mia carta" → stessa card, stesso link.
5. DM da un profilo che non segue il negozio → arriva il testo di invito a seguire, nessuna carta; poi il profilo segue,
   riscrive "CARTA" e riceve la card. Annotare anche come si comporta `isFollower` quando è `null` o in ritardo.
6. `python -m scripts.replay_webhook` con un evento duplicato → un solo invio.
7. Controllo dei log del server: nessun token, IGSID o chiave.
8. "Scollega" → il webhook sparisce da Zernio.

## File coinvolti
`AGENTS.md`, `.agents/architecture/overview.md`, `.agents/architecture/zernio-notes.md`, `.agents/workflows/deploy.md`,
`.agents/checklists/pre-release.md`, `.agents/planner/current.md`, `.agents/planner/roadmap.md`, `README.md`.

## Test da superare
Suite intera verde. Nessun test nuovo obbligatorio, salvo quelli per le discrepanze emerse dal collaudo.

## Fuori scope
Merge e tag (dopo l'ok dell'utente), migrazione alla chiave Zernio unica, DPA.

## Definition of Done
Documentazione allineata, collaudo 1-8 eseguito, riepilogo all'utente con l'elenco di cosa serve per il deploy (env
var, reset DB, onboarding dei merchant pilota).
