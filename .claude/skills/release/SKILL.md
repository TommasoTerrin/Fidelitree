---
name: release
description: "Fidelitree — dopo il merge su develop: checklist pre-release, collaudo manuale in locale guidato passo passo, migrazioni e env var, poi (con l'ok esplicito del founder a ogni passo) PR develop→main, deploy automatico su DigitalOcean, smoke test, tag e chiusura della versione."
argument-hint: "[vX.Y.Z]"
disable-model-invocation: true
---

# /release — collaudo da `develop` e pubblicazione su `main`

Versione: **$ARGUMENTS** (se vuoto: quella del blocco «Harness» di `current.md`, fase `collaudo`).

**Il push su `main` deploya automaticamente in produzione** (`https://fidelitree.app`, Neon `production`, dati
veri). Ogni passo verso l'esterno (merge, tag, comandi su `production`) chiede **un ok esplicito e separato**. Un
«ok» dato prima non vale per il passo dopo.

Procedure di riferimento, da seguire e non riscrivere: `.agents/workflows/collaudo.md`,
`.agents/checklists/pre-release.md`, `.agents/workflows/deploy.md` («Procedura di release», «Rollback»).

## Regole per i comandi che lancia il founder

- Comandi PowerShell **uno per riga e corti**; niente blocchi su più righe, niente `python -c` lunghi (meglio uno
  script in `scripts/`), percorsi brevi, nessuna punteggiatura subito dopo un comando.
- I segreti (chiave admin, password Neon, chiavi Zernio) li digita il founder nel suo terminale
  (`Read-Host -AsSecureString`), mai in chat né come argomenti. Se ne incolla uno in chat: fallo notare una volta,
  non riusarlo, annotalo da ruotare.
- Negli esiti si scrive solo ok / non ok e i tempi misurati.

## Passo 1 — Preparazione (su `develop`)

1. `git checkout develop`, `git pull`; `python -m pytest -q` verde.
2. Crea `.agents/tickets/vX.Y.Z/pre-release.md` copiando l'elenco di `.agents/checklists/pre-release.md` **senza
   spunte**, e aggiungi le voci della versione: passi della sua sezione di `collaudo.md`, migrazioni, env var nuove,
   servizi esterni da verificare, punti segnati nel rapporto di `/review`.
3. Spunta tu le voci che puoi verificare da solo (test, import, versione di `pyproject.toml` uguale a
   `EXPECTED_VERSION` di `scripts/smoke_test_prod.py`, `.env.example`, nessun segreto nel diff, dipendenze fissate).

## Passo 2 — Collaudo manuale in locale

Dai al founder i passi **in ordine**, un blocco alla volta, aspettando l'esito prima del successivo:
1. setup della parte fissa di `collaudo.md` (tre terminali, tunnel `cloudflared`, `scripts.run_collaudo`, Neon
   `development` o SQLite usa-e-getta), riscritto come elenco numerato con i comandi su una riga;
2. i passi della sezione della versione: **elenco numerato** con l'URL completo (quello del tunnel), cosa fare, cosa
   ci si aspetta;
3. la chiusura della parte fissa (scollegare Instagram, controllo dei log senza segreti, pulizia).

Scrivi gli esiti nel `pre-release.md` della versione (e in `zernio-notes.md` per Instagram/Zernio).

**Se un passo fallisce**: fermati. Il problema diventa una voce di `/fix` sulla versione, un branch `fix/<nome>` da
`develop`, `/implement` per i suoi ticket, PR verso `develop` con l'ok del founder, poi si ripete il collaudo dei
passi toccati (e di quelli che potrebbero averne risentito). Non si pubblica con un passo bloccante fallito.

## Passo 3 — Schema ed env var (prima del merge su `main`)

Se la versione cambia lo schema (cartella `migrations/` o modelli toccati):
1. branch di backup di `production` (comando in `deploy.md`, «Rollback»);
2. `development` rifatto da `production`, script SQL applicato, app avviata e provata su `development`;
3. l'ordine tra script in produzione e deploy è quello scritto nella spec della versione (piano di rollback): se non
   è scritto, fermati e chiedi.

Se ci sono env var nuove: il founder le aggiunge su DigitalOcean (App Spec) **prima** del merge; ricorda che il
salvataggio dello spec ridistribuisce il commit attivo.

## Passo 4 — Pubblicazione (ogni punto con l'ok esplicito)

1. **PR `develop` → `main`**: `gh pr create --base main --head develop`, titolo `Release vX.Y.Z — <titolo>`, corpo
   con obiettivo, ticket, esiti del collaudo, migrazioni, env var, piano di rollback e la riga di attribuzione
   indicata dal sistema. Aspetta la CI verde (`gh pr checks <n> --watch`).
2. **Merge** (`gh pr merge <n> --merge`): parte il deploy.
3. **Segui il deploy** con `doctl` (comandi in `deploy.md`, punto 4) fino ad `ACTIVE`. Se compare «automated rollback
   after failed deployment», il sito è rimasto com'era: leggi la causa e fermati.
4. **Smoke test**: il founder lancia `scripts/smoke_test_prod.py` con la chiave admin digitata nascosta (righe in
   `deploy.md`, punto 5). Se uno schema è cambiato, verifica delle tabelle sulla console Neon `production`.
5. **Verifiche in produzione** della versione (le voci «dopo il deploy» del `pre-release.md`): passi numerati per il
   founder, esiti nel file.
6. **Tag** `vX.Y.Z` annotato sul commit di `main` e push del tag.
7. **Riallinea `develop`**: `git checkout develop`, `git merge --ff-only origin/main`, `git push`.

Se qualcosa va storto dopo il deploy: «Rollback» di `deploy.md` (rollback dalla console DO, poi `git revert` del
merge; per lo schema il branch Neon di backup). Proponi la strada e aspetta l'ok.

## Passo 5 — Chiusura della versione

Su un branch `docs/chiusura-vX.Y.Z` da `develop`:
1. `.agents/tickets/vX.Y.Z/STORICO.md`: cronologia breve (formato di `v0.2.0/STORICO.md`) presa da `current.md` e dai
   ticket; esito della release;
2. `roadmap.md`: riga nel «Changelog», versione segnata come rilasciata, idee rimandate aggiunte al backlog;
3. `.agents/specs/` (da v0.5.0 in poi): togli le note «(da vX.Y.Z, non ancora in produzione)»; controlla che ogni
   riga di «Aree toccate» della spec sia riportata nel file dell'area;
4. `AGENTS.md`: riga «Versione corrente» in cima; «Mappa del codice» e «Comandi» se cambiati; nessun vincolo nuovo
   (stanno in `.agents/decisions/`). **Eccezione v0.4.0**, l'ultima con il metodo di prima: i vincoli della sezione
   «v0.4.0 campagne promozionali» di AGENTS.md diventano quelli vigenti (togli «dal rilascio» e «non in produzione»);
5. `current.md`: tolto il lavoro della versione (resta in `STORICO.md`), blocco «Harness» → fase `nessuna`, prossimo
   comando `/new-feature` o `/fix`; restano gli elenchi «cosa manca» (bloccanti / consigliati / opzionali);
6. `.agents/checklists/pre-release.md`: aggiornato se la release ha insegnato una voce nuova che vale per tutte.

Commit, push e PR verso `develop` con l'ok del founder (finisce su `main` con la release successiva: sono solo
documenti).

## Fine

Riepilogo: versione in produzione, tag, esiti, cosa resta aperto. Poi due proposte, senza avviarle:
- `/improve-architecture`, se `ft-standards` in `/review` ha segnalato smell rimandati o un modulo ha superato ~600
  righe;
- una breve **retrospettiva**: 3-5 miglioramenti alle skill, ad `AGENTS.md` o agli script nati da quello che è andato
  storto in questa versione, dal più grave. Si applicano solo con l'ok del founder.
