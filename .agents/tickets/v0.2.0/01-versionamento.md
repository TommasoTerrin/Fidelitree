# 01 — Versionamento con pyproject.toml

## Obiettivo
Introdurre un'unica fonte di verità per la versione dell'app (`v0.2.0`) e renderla visibile a runtime.

## Contesto
Oggi il versionamento è solo un tag git (`v0.1.0`). Non c'è nessun file di progetto. Le dipendenze restano in `requirements.txt` (usato dal Dockerfile): `pyproject.toml` serve **solo** per metadati e versione, non duplicare le dipendenze.

## Dipendenze
Nessuna.

## Modifiche
1. Crea `pyproject.toml` nella root con `[project]`: `name = "fidelitree"`, `version = "0.2.0"`, `description`, `requires-python = ">=3.12"`. Commento in testa: *"Le dipendenze restano in requirements.txt"*.
2. Crea `app/version.py` con `get_version() -> str`: legge `pyproject.toml` (via `tomllib`) risalendo dalla posizione del file; se non lo trova ritorna `"unknown"` (non deve mai far crashare l'app). Docstring in italiano.
3. Estendi `GET /health` in `app/main.py` per includere `"version"`.
4. Verifica che il `Dockerfile` copi `pyproject.toml` nell'immagine (e che `.dockerignore` non lo escluda); correggi se serve.
5. Documenta in `.agents/workflows/development.md` e `.agents/checklists/pre-release.md` il rito di release: bump in `pyproject.toml` → merge → tag `vX.Y.Z` identico.

## File coinvolti
`pyproject.toml` (nuovo), `app/version.py` (nuovo), `app/main.py`, `Dockerfile`/`.dockerignore` (se serve), `.agents/workflows/development.md`, `.agents/checklists/pre-release.md`, `tests/test_views.py` (o nuovo `tests/test_version.py`).

## Test da superare
- `get_version()` ritorna `"0.2.0"` ed è uguale al valore letto direttamente da `pyproject.toml`.
- `GET /health` → 200 con `{"status": ..., "version": "0.2.0"}` (mantiene le chiavi già presenti).
- Con `pyproject.toml` non raggiungibile (monkeypatch del path) `get_version()` ritorna `"unknown"` senza sollevare.
- La checklist pre-release contiene la voce di bump e tag (verifica manuale).

## Fuori scope
Pubblicazione su PyPI, `setuptools`, migrazione delle dipendenze in `pyproject.toml`.

## Definition of Done
Test sopra verdi, suite completa verde, `docker build` (o lettura del Dockerfile) conferma che il file è copiato.
