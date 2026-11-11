# Workflow di sviluppo

## Branch

```
main            ← produzione. Push = deploy automatico su DigitalOcean. MAI lavorare qui.
develop         ← integrazione. Parte sempre allineato a main.
feature/<nome>  ← una feature = un branch, parte da develop.
feature/trees   ← ARCHIVIO: vecchia logica Tree Points (Humani/Ecologi/Telegram).
                  Non mergiarlo: usarlo solo come riferimento per re-implementare.
```

Flusso: `develop` → `feature/<nome>` → merge in `develop` → (quando pronta la release) merge in `main` + tag `vX.Y.Z`.

## Ciclo di una feature

La procedura passo passo sta nelle skill del progetto, `.claude/skills/<nome>/SKILL.md` (markdown semplice: con
Claude Code si lanciano come comandi, con un altro agente si seguono a mano). Ordine e gate: tabella in
[`CLAUDE.md`](../../CLAUDE.md). In sintesi:

1. **`/new-feature`**: versione e branch decisi insieme (`feature/<nome>` da `develop` aggiornato), cartella
   `.agents/tickets/vX.Y.Z/`, grilling a giri con domande bloccanti / consigliate / opzionali.
2. **`/spec`**: spec con casi d'uso e criteri `AC-NN` (**gate 1**), poi modello di dominio, contract congelato, triage
   e ticket (**gate 2**). Le decisioni vanno subito nella documentazione viva (`.agents/decisions/`,
   `.agents/glossario.md`, `.agents/specs/`), non in AGENTS.md.
3. **`/implement NN`**: un ticket per sessione, TDD con `ft-test-writer` e `ft-implementer` separati; `python -m pytest`
   verde, commit locale piccolo, `current.md` e `HANDOFF.md` aggiornati, passi in `collaudo.md` se cambia ciò che vede
   un utente.
4. **`/fix`** (in qualsiasi momento): aggiunta, bug o decisione cambiata → voce `F-NN` nella spec, criteri e ticket
   nuovi, contract riapprovato se cambia.
5. **`/review`** (**gate 3**): tracciabilità, review sulla spec e sulle regole, poi push, PR `feature/<nome>` →
   `develop`, CI verde e merge, ogni passo con l'ok del founder.
6. **`/release`**: collaudo manuale **in locale da `develop`** (`collaudo.md`), checklist `pre-release.md` della versione,
   migrazioni ed env var, PR `develop` → `main` (deploy automatico), smoke test, tag, `develop` riallineato, chiusura
   della versione (`STORICO.md`, changelog di `roadmap.md`, `current.md`). Se il collaudo fallisce: `/fix`, branch
   `fix/<nome>` da `develop`, PR verso `develop`, collaudo ripetuto.
7. **`/improve-architecture`** (ogni tanto, o a fine versione): dove il codice si sta aggrovigliando.

## Rito di release (versione)

La versione ha **una sola fonte**: `[project] version` in `pyproject.toml` (SemVer 0.x), esposta da `GET /health`.

1. Bump di `version` in `pyproject.toml`.
2. Merge su `main` (deploy automatico).
3. Tag git `vX.Y.Z` **identico** al valore in `pyproject.toml` (`git tag vX.Y.Z && git push --tags`).
4. Dopo il deploy verifica che `/health` riporti la nuova versione.

## Convenzioni

- Messaggi di commit in italiano, descrittivi, al presente ("aggiunge X", "rimuove Y").
- Route → service → crud: la business logic sta nei service, mai nelle route.
- Nuove variabili d'ambiente: aggiungile a `.env.example`, a `.agents/workflows/deploy.md` e alle env vars su DigitalOcean PRIMA del deploy (l'app non parte se mancano).
