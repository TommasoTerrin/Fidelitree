"""
Client per l'Impact API di Ecologi (https://docs.ecologi.com).
Si usa una sola chiave di piattaforma: paga il founder.

Con settings.ECOLOGI_TEST_MODE=True si usano chiave e URL dell'ambiente di prova di Ecologi
(`ECOLOGI_TEST_API_KEY` / `ECOLOGI_TEST_BASE_URL`) e le richieste portano anche il flag "test":
nessun addebito reale. Con False si usano `ECOLOGI_API_KEY` / `ECOLOGI_BASE_URL` (addebito vero).
"""

import uuid
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

TIMEOUT = 15.0  # secondi

# Campi della risposta Ecologi che possono identificare l'acquisto, in ordine di preferenza
_REF_KEYS = ("id", "purchaseId", "treeUrl")


class EcologiError(Exception):
    """Errore nella comunicazione con Ecologi (rete, auth o risposta inattesa)."""


def _credentials() -> tuple[str, str]:
    """
    (api_key, base_url) dell'ambiente attivo: test se `ECOLOGI_TEST_MODE`, reale altrimenti.
    Solleva `EcologiError` se chiave o URL dell'ambiente attivo non sono configurati.
    """
    if settings.ECOLOGI_TEST_MODE:
        api_key, base_url, label = settings.ECOLOGI_TEST_API_KEY, settings.ECOLOGI_TEST_BASE_URL, "di test"
    else:
        api_key, base_url, label = settings.ECOLOGI_API_KEY, settings.ECOLOGI_BASE_URL, "di piattaforma"
    if not api_key:
        raise EcologiError(f"Chiave Ecologi {label} non configurata")
    if not base_url:
        raise EcologiError(f"URL Ecologi {label} non configurato")
    return api_key, base_url.rstrip("/")


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
    """Identificativo dell'acquisto ricavato dalla risposta di Ecologi, `None` se assente."""
    if not isinstance(response, dict):
        return None
    for key in _REF_KEYS:
        value = response.get(key)
        if value:
            return str(value)
    return None


async def purchase_trees(
    number: int,
    name: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """
    Pianta `number` alberi sull'account Ecologi di piattaforma e ritorna la risposta JSON.
    `name` è un'etichetta visibile sul profilo pubblico Ecologi (MAI dati personali dei clienti).
    `idempotency_key` va deterministico per le chiusure di periodo (vedi `close_period`).
    Solleva `EcologiError` su chiave/URL mancanti, errore di rete o risposta non 200/201.
    """
    api_key, base_url = _credentials()
    headers = _headers(api_key, idempotency_key)
    payload: dict = {"number": number}
    if name:
        payload["name"] = name
    if settings.ECOLOGI_TEST_MODE:
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

    logger.info("Piantati %d alberi via Ecologi (test=%s)", number, settings.ECOLOGI_TEST_MODE)
    try:
        return r.json()
    except ValueError as e:
        raise EcologiError("Risposta di Ecologi non valida (JSON atteso)") from e
