"""
Conversioni tra euro e centesimi interi.

Il denaro nel database e nel core è sempre in centesimi (int, mai float):
questi helper si usano solo ai bordi (API, template). Solo libreria standard.
"""

import math
from decimal import Decimal, ROUND_HALF_UP


def euro_to_cents(euro: float) -> int:
    """
    Converte un importo in euro in centesimi interi, arrotondando al centesimo
    (metà verso l'alto). Passa da `str` per evitare gli errori dei float
    (0.1 + 0.2 → 30).

    Solleva `ValueError` se l'importo non è un numero finito.
    """
    if not math.isfinite(euro):
        raise ValueError("L'importo deve essere un numero finito")
    cents = (Decimal(str(euro)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def cents_to_euro(cents: int) -> float:
    """Converte centesimi interi in euro (solo per la presentazione)."""
    return cents / 100
