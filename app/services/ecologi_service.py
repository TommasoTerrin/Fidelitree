"""
Client per l'Impact API di Ecologi (https://docs.ecologi.com).
Paga il founder con la chiave di piattaforma. Ecologi non ha un URL sandbox: reale e prova
usano lo stesso `ECOLOGI_BASE_URL`, cambiano la chiave e il flag "test" nel body.

Con settings.ECOLOGI_TEST_MODE=True si usa `ECOLOGI_TEST_API_KEY` e le richieste portano
"test": true (risposta realistica, nessun addebito, nulla sul profilo). Con False si usa
`ECOLOGI_API_KEY` (addebito vero). Nessun fallback da una chiave all'altra.
"""

import uuid
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

TIMEOUT = 15.0  # secondi

class EcologiError(Exception):
    """Errore nella comunicazione con Ecologi (rete, auth o risposta inattesa)."""


def _credentials() -> tuple[str, str]:
    """
    (api_key, base_url): chiave di test se `ECOLOGI_TEST_MODE`, reale altrimenti; l'URL è sempre
    `ECOLOGI_BASE_URL`. Solleva `EcologiError` se la chiave dell'ambiente attivo è vuota
    (mai fallback sull'altra chiave) o se manca l'URL.
    """
    if settings.ECOLOGI_TEST_MODE:
        api_key, label = settings.ECOLOGI_TEST_API_KEY, "di test"
    else:
        api_key, label = settings.ECOLOGI_API_KEY, "di piattaforma"
    if not api_key:
        raise EcologiError(f"Chiave Ecologi {label} non configurata")
    if not settings.ECOLOGI_BASE_URL:
        raise EcologiError("URL Ecologi non configurato")
    return api_key, settings.ECOLOGI_BASE_URL.rstrip("/")


def _headers(api_key: str, idempotency_key: str | None) -> dict:
    """
    Header della richiesta. L'`Idempotency-Key` passato rende i retry sicuri (Ecologi non
    pianta due volte); se manca ne viene generato uno casuale.
    """
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Idempotency-Key": idempotency_key or str(uuid.uuid4()),
    }


def extract_ref(response: dict) -> str | None:
    """
    Riferimento dell'acquisto: il `treeUrl` (link alla tessera) è l'unico identificativo
    documentato, la risposta non ha un `id`. `None` se assente.
    """
    if not isinstance(response, dict):
        return None
    value = response.get("treeUrl")
    return str(value) if value else None


async def purchase_trees(
    number: int,
    name: str | None = None,
    idempotency_key: str | None = None,
    *,
    force_test: bool = False,
) -> dict:
    """
    Pianta `number` alberi sull'account Ecologi di piattaforma e ritorna la risposta JSON.
    `name` è l'etichetta "funded by" mostrata nella foresta Ecologi (pubblica): il nome del
    negozio, MAI dati personali dei clienti. Stesso `name` entro 24 ore = stessa tessera.
    `idempotency_key` va deterministico per le chiusure di periodo (vedi `close_period`).
    `force_test=True` aggiunge `"test": true` anche con `ECOLOGI_TEST_MODE=False`
    (verifica della chiave reale senza addebito, vedi `scripts/ecologi_check`).
    Solleva `EcologiError` su chiave/URL mancanti, errore di rete o risposta non 200/201.
    """
    api_key, base_url = _credentials()
    headers = _headers(api_key, idempotency_key)
    payload: dict = {"number": number}
    if name:
        payload["name"] = name
    is_test = settings.ECOLOGI_TEST_MODE or force_test
    if is_test:
        payload["test"] = True

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{base_url}/impact/trees",
                headers=headers,
                json=payload,
            )
    except httpx.HTTPError as e:
        raise EcologiError(f"Ecologi non raggiungibile: {e}") from e

    if r.status_code not in (200, 201):
        logger.error("Ecologi ha risposto %s: %s", r.status_code, r.text[:200])
        raise EcologiError(f"Ecologi ha rifiutato la richiesta (HTTP {r.status_code})")

    logger.info("Piantati %d alberi via Ecologi (test=%s)", number, is_test)
    try:
        return r.json()
    except ValueError as e:
        raise EcologiError("Risposta di Ecologi non valida (JSON atteso)") from e
