"""
Errori di dominio.

Il core dei service solleva queste eccezioni, mai `HTTPException`: è
l'handler globale in `app/main.py` a tradurle in risposte HTTP.
Questo modulo non importa fastapi.
"""


class DomainError(Exception):
    """Base di tutti gli errori di dominio; `str(e)` è il messaggio per l'utente."""


class NotFoundError(DomainError):
    """Risorsa inesistente o non visibile a chi la richiede (HTTP 404)."""


class ForbiddenError(DomainError):
    """Operazione non consentita a chi la richiede (HTTP 403)."""


class ConflictError(DomainError):
    """La risorsa esiste già (HTTP 409)."""


class InvalidInputError(DomainError):
    """Dati in ingresso non validi, es. registrazione con campi errati (HTTP 400)."""


class AuthError(DomainError):
    """Credenziali o codice di accesso errati (HTTP 401)."""


class TooManyAttemptsError(DomainError):
    """
    Troppi tentativi di accesso falliti (HTTP 429). `retry_after` sono i secondi di attesa,
    arrotondati per eccesso (finiscono nell'header `Retry-After`). `suffix` chiude il messaggio: di default
    l'invito del merchant a chiedere il reset al founder; l'accesso admin ne passa uno suo.
    """

    DEFAULT_SUFFIX = "oppure chiedi al founder di reimpostare la password"

    def __init__(self, retry_after: int, suffix: str = DEFAULT_SUFFIX) -> None:
        self.retry_after = max(1, int(retry_after))
        minutes = -(-self.retry_after // 60)
        super().__init__(
            f"Troppi tentativi di accesso: riprova tra {minutes} minut{'o' if minutes == 1 else 'i'}"
            + (f", {suffix}" if suffix else "")
        )


class ExternalServiceError(DomainError):
    """Un servizio esterno (Zernio) non risponde o dà un errore inatteso (HTTP 502). Messaggio senza dettagli né segreti."""


class MessageTooLongError(InvalidInputError):
    """Un campo della card supera il limite della piattaforma (HTTP 400)."""


class InvalidSignatureError(AuthError):
    """Firma del webhook assente o errata (HTTP 401)."""


class InsufficientBalanceError(DomainError):
    """Un saldo (tree points o cashback) scenderebbe sotto zero (HTTP 400)."""


class InvalidThresholdsError(DomainError):
    """Soglie dei livelli incoerenti: devono essere ≥ 1 e crescenti (HTTP 400)."""


class PeriodAlreadyClosedError(DomainError):
    """Il periodo è già stato chiuso per quel negozio (HTTP 400)."""
