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

1. **Planner**: leggi/aggiorna `.agents/planner/current.md` con cosa stai per fare.
2. **Branch**: `git checkout develop && git pull && git checkout -b feature/<nome>`.
3. **Sviluppo**: commit piccoli e frequenti; il progetto deve restare funzionante dopo ogni commit.
4. **Test automatici**: `python -m pytest` (obbligatorio verde prima del merge). Aggiungi test per la nuova feature.
5. **Test manuali**: `python local_main.py` e verifica il flusso toccato (vedi flusso principale in `.agents/architecture/overview.md`).
6. **Merge in develop**: `git checkout develop && git merge feature/<nome>` e push.
7. **Release** (solo quando develop è pronto): segui `.agents/checklists/pre-release.md`, poi merge in `main` + tag.
8. **Post-deploy**: `.agents/workflows/deploy.md` per la verifica su DigitalOcean e Neon.
9. **Documentazione**: aggiorna AGENTS.md / .agents/ se sono cambiati comandi, endpoint o architettura; sposta l'item da `current.md` al changelog di `roadmap.md`.

## Convenzioni

- Messaggi di commit in italiano, descrittivi, al presente ("aggiunge X", "rimuove Y").
- Route → service → crud: la business logic sta nei service, mai nelle route.
- Nuove variabili d'ambiente: aggiungile a `.env.example`, a `.agents/workflows/deploy.md` e alle env vars su DigitalOcean PRIMA del deploy (l'app non parte se mancano).
