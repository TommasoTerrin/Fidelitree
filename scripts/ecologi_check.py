"""
Verifica reale della chiave Ecologi: una chiamata vera con "test": true (nessun addebito,
nulla sul profilo). Vale per la chiave di test e per quella reale: usa quella dell'ambiente
attivo (`ECOLOGI_TEST_MODE`) ma la richiesta è SEMPRE di prova. Non tocca il DB.

Utilizzo (dalla root del progetto):
    python -m scripts.ecologi_check
    python -m scripts.ecologi_check --trees 3 --merchant-name "Bar Demo" --month 2026-10

Codici di uscita: 0 chiave OK, 1 errore Ecologi (chiave mancante/rifiutata, rete, risposta).
"""

import argparse
import asyncio
import logging
import re
import sys
from typing import Optional

from app.core.clock import utc_now
from app.core.config import settings
from app.services import ecologi_service, tree_service
from app.services.ecologi_service import EcologiError


def _parse_month(value: str) -> str:
    """Valida 'YYYY-MM' (argparse mostra l'errore all'utente)."""
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise argparse.ArgumentTypeError("formato atteso YYYY-MM (es. 2026-10)")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.ecologi_check",
        description="Chiamata reale a Ecologi con test=true: verifica la chiave senza addebito.",
    )
    parser.add_argument("--trees", type=int, default=1, help="numero di alberi della prova (default 1)")
    parser.add_argument("--merchant-name", default="Negozio di prova", help="nome del negozio nell'etichetta")
    parser.add_argument("--month", type=_parse_month, help="mese dell'etichetta (YYYY-MM); default: mese UTC corrente")
    return parser


def _key_description() -> str:
    """Tipo di chiave in uso e ultimi 4 caratteri (mai la chiave intera)."""
    if settings.ECOLOGI_TEST_MODE:
        kind, key = "di test", settings.ECOLOGI_TEST_API_KEY
    else:
        kind, key = "REALE", settings.ECOLOGI_API_KEY
    return f"{kind} (…{key[-4:]})" if key else f"{kind} (non configurata)"


def main(argv: Optional[list[str]] = None) -> int:
    """Esegue la verifica e ritorna il codice di uscita."""
    args = _build_parser().parse_args(argv)
    month = args.month or tree_service.period_for(utc_now())
    name = tree_service.planting_name(args.merchant_name, month)

    print(f"Chiave Ecologi {_key_description()}")
    print(f"URL: {settings.ECOLOGI_BASE_URL.rstrip('/')}/impact/trees")
    print(f"Nome inviato: {name}")
    try:
        response = asyncio.run(ecologi_service.purchase_trees(args.trees, name=name, force_test=True))
    except EcologiError as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        return 1

    print(f"treeUrl: {ecologi_service.extract_ref(response) or '(assente)'}")
    print(f"Importo: {response.get('amount')} {response.get('currency')}")
    for project in response.get("projectDetails") or []:
        print(f"Progetto: {project.get('name')}")
    print("Chiave OK — nessun addebito (test=true)")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
