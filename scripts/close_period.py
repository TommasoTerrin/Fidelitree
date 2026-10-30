"""
Chiusura mensile: pianta su Ecologi gli alberi del pool di ogni negozio (chiave di piattaforma).

Mostra un'anteprima, chiede conferma ed è idempotente (rilanciarlo non pianta due volte).

Utilizzo (dalla root del progetto):
    python -m scripts.close_period                      # mese precedente, chiede conferma
    python -m scripts.close_period --month 2026-10      # mese specifico
    python -m scripts.close_period --cap 24             # nuovo cap per questa esecuzione
    python -m scripts.close_period --yes                # salta la conferma (NON il blocco cap)

Codici di uscita: 0 ok, 1 divergenze contatore/registro o cap sforato non autorizzato,
2 annullato dall'utente, 3 almeno un negozio fallito.
"""

import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime
from typing import Optional

from sqlmodel import Session

from app.core.clock import utc_now
from app.core.config import settings
from app.services import tree_service

logger = logging.getLogger(__name__)

COST_PER_TREE_EUR = 0.80  # stima del costo di un albero Ecologi


def _parse_month(value: str) -> str:
    """Valida 'YYYY-MM' (argparse mostra l'errore all'utente)."""
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise argparse.ArgumentTypeError("formato atteso YYYY-MM (es. 2026-10)")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.close_period",
        description="Pianta gli alberi del mese su Ecologi (anteprima, conferma, idempotente).",
    )
    parser.add_argument("--month", type=_parse_month, help="mese da chiudere (YYYY-MM); default: mese precedente")
    parser.add_argument("--cap", type=int, help="nuovo cap globale di alberi per questa esecuzione")
    parser.add_argument("--yes", action="store_true", help="salta la conferma interattiva (non il blocco cap)")
    return parser


def _print_preview(plan, test_mode: bool) -> None:
    """Stampa tabella di anteprima, totale, costo stimato e cap."""
    print(f"\nChiusura del periodo {plan.period}")
    if test_mode:
        print("MODALITÀ TEST (ECOLOGI_TEST_MODE=true): nessun addebito reale.")
    print(f"{'Negozio':<30}{'Punti':>8}  {'Livello':<8}{'Alberi':>7}")
    for line in plan.lines:
        print(f"{line.business_name[:29]:<30}{line.points:>8}  {line.level.value:<8}{line.trees:>7}")
    cost = plan.total_trees * COST_PER_TREE_EUR
    print(f"\nTotale alberi: {plan.total_trees} (costo stimato {cost:.2f} € a {COST_PER_TREE_EUR:.2f} €/albero)")
    print(f"Cap: {plan.global_cap}")
    if plan.exceeds_cap:
        print(f"!!! CAP SFORATO di {plan.excess} alberi !!!")


def main(
    argv: Optional[list[str]] = None,
    *,
    session: Optional[Session] = None,
    now: Optional[datetime] = None,
    input_fn=input,
) -> int:
    """
    Esegue la chiusura e ritorna il codice di uscita. `session`, `now` e `input_fn` sono
    iniettabili per i test; in uso normale si apre una sessione sul DB di `DATABASE_URL`.
    """
    args = _build_parser().parse_args(argv)
    now = now or utc_now()
    period = args.month or tree_service.period_label(*tree_service.previous_period(now.date()))
    cap = args.cap if args.cap is not None else settings.ECOLOGI_GLOBAL_MONTHLY_CAP

    if session is None:
        from app.main import engine  # import tardivo: evita di avviare l'app per --help
        with Session(engine) as own_session:
            return _run(own_session, period, cap, args, now, input_fn)
    return _run(session, period, cap, args, now, input_fn)


def _run(session: Session, period: str, cap: int, args, now: datetime, input_fn) -> int:
    """Corpo di `main`: controlli, anteprima, conferma, chiusura e report."""
    mismatches = tree_service.pool_mismatches(session, period)
    if mismatches:
        print(f"\n!!! DIVERGENZE contatore/registro nel periodo {period}: nessun albero piantato !!!")
        for m in mismatches:
            print(f"  negozio {m.merchant_id}: contatore={m.counter} registro={m.ledger}")
        return 1

    plan = tree_service.build_closure_plan(session, period, cap)
    _print_preview(plan, settings.ECOLOGI_TEST_MODE)
    if plan.total_trees == 0:
        print("\nNiente da piantare.")
        return 0

    if plan.exceeds_cap:
        # --yes non autorizza lo sforamento: serve --cap N o conferma esplicita interattiva
        if args.yes:
            print("Cap sforato: rilancia con --cap N per autorizzare un nuovo cap.")
            return 1
        authorized = input_fn("Autorizzi lo sforamento del cap? (s/n): ").strip().lower() == "s"
        if not authorized:
            print("Annullato: nessun albero piantato.")
            return 1
    elif not args.yes:
        if input_fn("Procedere con la piantumazione? (s/n): ").strip().lower() != "s":
            print("Annullato.")
            return 2

    report = asyncio.run(tree_service.close_period(
        session, period, global_cap=cap, confirm=lambda _plan: True, now=now,
    ))
    for entry in report.entries:
        suffix = f" — {entry.detail}" if entry.detail else ""
        print(f"  [{entry.status}] {entry.business_name}: {entry.trees} alberi{suffix}")
    return 3 if any(e.status == "failed" for e in report.entries) else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
