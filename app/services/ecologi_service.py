"""
Client per l'Impact API di Ecologi (https://docs.ecologi.com).
Ogni merchant usa la propria API key (salvata cifrata nel DB).

Con settings.ECOLOGI_TEST_MODE=True le richieste portano il flag "test":
Ecologi simula la risposta senza addebitare né registrare alberi.
"""

import uuid
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

TIMEOUT = 15.0  # secondi: la piantumazione avviene durante lo scan, non deve bloccare


class EcologiError(Exception):
    """Errore nella comunicazione con Ecologi (rete, auth o risposta inattesa)."""


def _headers(api_key: str) -> dict:
    if not api_key:
        raise EcologiError("API key Ecologi mancante")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # retry sicuri: se la richiesta viene ripetuta, Ecologi non pianta due volte
        "Idempotency-Key": str(uuid.uuid4()),
    }


async def purchase_trees(api_key: str, number: int = 1, name: str | None = None) -> dict:
    """
    Pianta `number` alberi sull'account Ecologi del merchant.
    `name` è un'etichetta visibile sul profilo pubblico Ecologi
    (usare identificativi carta, MAI dati personali del cliente).
    """
    payload: dict = {"number": number}
    if name:
        payload["name"] = name
    if settings.ECOLOGI_TEST_MODE:
        payload["test"] = True

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{settings.ECOLOGI_BASE_URL}/impact/trees",
                headers=_headers(api_key),
                json=payload,
            )
    except httpx.HTTPError as e:
        raise EcologiError(f"Ecologi non raggiungibile: {e}") from e

    if r.status_code not in (200, 201):
        logger.error("Ecologi ha risposto %s: %s", r.status_code, r.text[:200])
        raise EcologiError(f"Ecologi ha rifiutato la richiesta (HTTP {r.status_code})")

    logger.info("Piantati %d alberi via Ecologi (test=%s)", number, settings.ECOLOGI_TEST_MODE)
    return r.json()


async def validate_api_key(api_key: str) -> bool:
    """
    Verifica che una API key Ecologi sia valida facendo un acquisto
    con flag "test": nessun addebito, nessun albero registrato.
    Ritorna False su chiave non valida; solleva EcologiError su problemi di rete.
    """
    payload = {"number": 1, "test": True}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{settings.ECOLOGI_BASE_URL}/impact/trees",
                headers=_headers(api_key),
                json=payload,
            )
    except httpx.HTTPError as e:
        raise EcologiError(f"Ecologi non raggiungibile: {e}") from e

    if r.status_code in (200, 201):
        return True
    if r.status_code in (401, 403):
        return False
    logger.error("Validazione chiave Ecologi: risposta inattesa %s: %s", r.status_code, r.text[:200])
    raise EcologiError(f"Risposta inattesa da Ecologi (HTTP {r.status_code})")
