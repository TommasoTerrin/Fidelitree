"""
Orologio dell'applicazione.

`utc_now()` è l'unico punto in cui la shell legge l'ora: il core puro non
chiama mai l'orologio, riceve il tempo come argomento.
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Ritorna l'istante corrente come datetime *aware* in UTC."""
    return datetime.now(timezone.utc)
