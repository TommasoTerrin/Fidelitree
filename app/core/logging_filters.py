"""
Filtro dei log di accesso: maschera i segreti che stanno nel percorso dell'URL.

- `/c/<token>`: il token del link della carta (chi lo ha apre la carta);
- `/webhooks/zernio/<hook_id>`: l'id opaco del webhook di un negozio.

Il filtro si installa sul logger `uvicorn.access` all'avvio (lifespan), quindi vale per `local_main.py`
e per il `CMD` del Dockerfile. I log della piattaforma di hosting restano fuori dal nostro controllo
(trade-off accettato, vedi AGENTS.md).
"""

import logging
import re

ACCESS_LOGGER = "uvicorn.access"
MASK = "***"

# --- Core puro ---

# Il percorso deve iniziare a inizio testo, dopo uno spazio o dopo un apice (`GET /c/...`, `"/c/..."`):
# così `/static/c/x` non viene toccato. Il segreto arriva fino al primo `/`, `?`, `#`, spazio o virgolette.
_SECRET_PATHS = re.compile(r"""(?<![^\s"'])(/c/|/webhooks/zernio/)[^\s"'/?#]+""")


def mask_sensitive_paths(text: str) -> str:
    """
    Sostituisce il segreto dei percorsi `/c/<token>` e `/webhooks/zernio/<hook_id>` con `***`
    (es. `GET /c/abc?x=1 HTTP/1.1` → `GET /c/***?x=1 HTTP/1.1`). Gli altri percorsi restano invariati.
    """
    return _SECRET_PATHS.sub(lambda m: m.group(1) + MASK, text)


# --- Shell ---

class AccessLogMaskFilter(logging.Filter):
    """
    Filtro di `logging` che applica `mask_sensitive_paths` al messaggio e a ogni argomento testuale del
    record. uvicorn logga `'%s - "%s %s HTTP/%s" %d'` con il percorso (query compresa) negli argomenti,
    quindi non basta riscrivere il messaggio. Gli argomenti non testuali (lo status) restano come sono.
    Non scarta mai un record.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Maschera `record.msg` e gli argomenti (tupla o dizionario); ritorna sempre `True`."""
        if isinstance(record.msg, str):
            record.msg = mask_sensitive_paths(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(mask_sensitive_paths(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: mask_sensitive_paths(v) if isinstance(v, str) else v for k, v in record.args.items()}
        return True


def install_access_log_filter() -> None:
    """Installa `AccessLogMaskFilter` su `uvicorn.access`, una sola volta (più chiamate non duplicano il filtro)."""
    logger = logging.getLogger(ACCESS_LOGGER)
    if not any(isinstance(f, AccessLogMaskFilter) for f in logger.filters):
        logger.addFilter(AccessLogMaskFilter())


def remove_access_log_filter() -> None:
    """Toglie da `uvicorn.access` i filtri di questo modulo (serve ai test per lasciare il logger pulito)."""
    logger = logging.getLogger(ACCESS_LOGGER)
    for f in [f for f in logger.filters if isinstance(f, AccessLogMaskFilter)]:
        logger.removeFilter(f)
