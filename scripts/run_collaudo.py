"""
Avvio del server per il collaudo manuale (vedi .agents/workflows/collaudo.md).

Avvia lo stesso `app.main:app` di `local_main.py` (senza hot-reload) e in più mostra i log `info` dell'app con l'ora,
che servono a leggere gli esiti del webhook. Prima di partire controlla il DB: accetta solo un SQLite usa-e-getta
o il branch Neon `development`, e si rifiuta con qualsiasi altro host (in particolare `production`).
Stampa solo l'id dell'endpoint, mai l'URL.

Utilizzo (dalla root del progetto, una riga):
    python -m scripts.run_collaudo | Tee-Object -FilePath collaudo.log
"""

import logging
import sys
from urllib.parse import urlparse

from app.core.config import settings

# Id dell'endpoint del branch Neon `development` (non è un segreto: è parte dell'host)
DEV_HOST_FRAGMENT = "ep-morning-credit"


def check_database_url(url: str) -> str:
    """Ritorna una descrizione del DB se è ammesso per il collaudo; esce con errore altrimenti."""
    if url.startswith("sqlite"):
        return "SQLite usa-e-getta"
    host = urlparse(url).hostname or ""
    if DEV_HOST_FRAGMENT not in host:
        sys.exit(f"RIFIUTATO: il DB ({host.split('.')[0] or 'sconosciuto'}) non è Neon development né SQLite")
    return host.split(".")[0]


def main() -> None:
    """Controlla il DB, configura i log dell'app e avvia uvicorn su 127.0.0.1:8001."""
    print("DB:", check_database_url(settings.DATABASE_URL))
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(name)s %(message)s"))
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    app_logger.addHandler(handler)

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8001)


if __name__ == "__main__":
    main()
