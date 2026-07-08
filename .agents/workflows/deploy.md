# Deploy — DigitalOcean App Platform + Neon

## Come funziona

- L'app su **DigitalOcean App Platform** builda il `Dockerfile` e fa **auto-deploy a ogni push su `main`**.
- Il container ascolta su `$PORT` (iniettata da DO; default 8000 in locale).
- Il database è **PostgreSQL su Neon**: l'app lo raggiunge tramite `DATABASE_URL`.
- Lo schema viene creato/aggiornato da `create_all()` all'avvio (solo tabelle/colonne NUOVE: non elimina né modifica colonne esistenti).

## Env vars richieste su DigitalOcean

Se ne manca una l'app **crasha all'avvio** (Settings pydantic con campi obbligatori):

| Variabile | Descrizione |
|---|---|
| `DATABASE_URL` | URL Postgres Neon completo (`postgresql://...?sslmode=require`) |
| `ENCRYPTION_KEY` | chiave Fernet per cifrare le password merchant |
| `JWT_SECRET_KEY` | firma dei token di sessione |
| `MERCHANT_PASSWORD` | password del merchant di test creato dal seed |
| `ADMIN_SECRET_KEY` | chiave per gli endpoint admin (`X-Admin-Key`) |

Variabili storiche NON più usate (rimuovibili da DO): `HUMANI_*`, `ECOLOGI_*`, `TELEGRAM_BOT_TOKEN`, `BASE_URL`, `DATABASE_PASSWORD`.

## Procedura di release

1. Completa la checklist `.agents/checklists/pre-release.md`.
2. `git checkout main && git merge develop && git push` → parte il deploy automatico.
3. Attendi il deploy dalla console DO (build + health check su `/health`).
4. Smoke test: `python scripts/smoke_test_prod.py https://<app>.ondigitalocean.app <ADMIN_SECRET_KEY>`.
5. Verifica Neon (console Neon → tabelle `merchant` e `card` presenti e coerenti).
6. Tag: `git tag vX.Y.Z && git push --tags`.
7. Riallinea develop: `git checkout develop && git merge main && git push`.

## Rollback

Dalla console DigitalOcean: Deployments → seleziona il deploy precedente → "Rollback".
In alternativa: `git revert` del merge su main e push (nuovo deploy).

## Reset/seed del DB di produzione (distruttivo!)

Solo se i dati sono sacrificabili. In locale, con `DATABASE_URL` di Neon nel `.env`:

```bash
python -m scripts.reset_db      # chiede conferma (--force per saltare)
python -m scripts.seed_db
```
