"""
Enumerazioni di dominio condivise da modelli e core puro.

Solo libreria standard: questo modulo non deve dipendere da SQLModel né da
FastAPI, perché lo importano sia i modelli sia il core dei service.
"""

from enum import Enum


class PointTransactionKind(str, Enum):
    """Tipo di movimento di tree points nel registro."""
    SCAN = "scan"              # accredito/addebito del merchant (conta nel pool)
    CONVERSION = "conversion"  # conversione automatica in cashback (non tocca il pool)


class Level(str, Enum):
    """Livello raggiunto dal pool mensile di un negozio."""
    NONE = "none"
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
