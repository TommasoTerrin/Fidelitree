# 01 — Versione 0.3.0

## Obiettivo
Portare la versione a **0.3.0** su `feature/instagram-cards`, così `/health` distingue il nuovo ramo da v0.2.1.

## Contesto
La fonte unica della versione è `[project] version` in `pyproject.toml`, letta da `app/version.py` ed esposta da
`GET /health`. v0.2.1 **non** andrà su `main`: si rilascia direttamente v0.3.0 (decisione 2026-10-22).

## Dipendenze
Nessuna.

## Modifiche
1. `pyproject.toml`: `version = "0.3.0"`.
2. Il test della versione si aggiorna se confronta un valore fisso.

## File coinvolti
`pyproject.toml`, `tests/test_version.py` (se serve).

## Test da superare
- `GET /health` → `version == "0.3.0"`.

## Fuori scope
Tag git e merge su `main` (ticket 11, con l'ok dell'utente).

## Definition of Done
Suite verde, `/health` riporta 0.3.0.
