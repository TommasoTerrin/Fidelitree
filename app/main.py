"""
Punto di ingresso principale dell'applicazione Fidelitree.
Configura l'istanza FastAPI, il database, i middleware e include tutti i router.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import SQLModel, create_engine

from app.core.auth import get_auth_provider
from app.core.config import settings
from app.core.crypto import validate_keys
from app.core.errors import (
    AuthError, ConflictError, DomainError, ExternalServiceError, ForbiddenError, NotFoundError,
    TooManyAttemptsError,
)
from app.core.logging_filters import install_access_log_filter
from app.version import get_version

# Import dei router
from app.routes.admin import router as admin_router
from app.routes.consumer.views import router as consumer_views_router
from app.routes.merchant.api import router as merchant_api_router
from app.routes.merchant.auth import router as merchant_auth_router
from app.routes.merchant.views import router as merchant_views_router
from app.routes.webhooks import router as webhooks_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestisce il ciclo di vita dell'applicazione.
    Verifica le chiavi di cifratura e il provider di autenticazione (l'app non parte con chiavi non valide né con
    `AUTH_PROVIDER=dev` in produzione), installa il filtro che maschera token del link e `hook_id` nei log di
    accesso e crea le tabelle del database se non esistono.
    """
    validate_keys()
    get_auth_provider()
    install_access_log_filter()
    SQLModel.metadata.create_all(engine)
    yield

# --- App ---
app = FastAPI(title="Fidelitree MVP", lifespan=lifespan, redirect_slashes=False)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """
    Traduce gli errori di dominio del core in risposte HTTP `{"detail": ...}`:
    AuthError → 401, NotFoundError → 404, ForbiddenError → 403, ConflictError → 409,
    TooManyAttemptsError → 429 (con `Retry-After`), ExternalServiceError → 502, tutti gli altri → 400.
    """
    if isinstance(exc, TooManyAttemptsError):
        return JSONResponse(
            status_code=429, content={"detail": str(exc)}, headers={"Retry-After": str(exc.retry_after)},
        )
    if isinstance(exc, AuthError):
        status = 401
    elif isinstance(exc, NotFoundError):
        status = 404
    elif isinstance(exc, ForbiddenError):
        status = 403
    elif isinstance(exc, ConflictError):
        status = 409
    elif isinstance(exc, ExternalServiceError):
        status = 502
    else:
        status = 400
    return JSONResponse(status_code=status, content={"detail": str(exc)})


# --- Database ---
engine = create_engine(
    url=settings.DATABASE_URL,
    pool_pre_ping=True,  # Fix per timeout SSL con Neon DB
    pool_recycle=300,    # Ricicla connessioni ogni 5 min
    pool_size=5,
    max_overflow=10
)


# --- Router ---
app.include_router(admin_router)                 # /admin: dashboard del founder (login, lista, azioni)
app.include_router(consumer_views_router)        # GET /c/{token}, /carta-di-prova, /privacy
app.include_router(merchant_api_router, prefix="/api") # /api/merchant/...: API del merchant, onboarding Instagram, API admin (X-Admin-Key)
app.include_router(merchant_auth_router)         # POST /merchant/register, POST /merchant/login, GET /merchant/logout
app.include_router(merchant_views_router)        # GET /merchant/... pagine HTML
app.include_router(webhooks_router)              # POST /webhooks/zernio/{hook_id}


@app.get("/sw.js", include_in_schema=False)
async def service_worker() -> FileResponse:
    """
    Service worker della PWA del merchant servito dalla radice, con scope ristretto a `/merchant/`
    (`Service-Worker-Allowed`): la pagina carta del cliente non ha service worker. Da `/static/` lo scope
    massimo sarebbe `/static/`. `Cache-Control: no-cache` fa arrivare subito le nuove versioni.
    """
    return FileResponse(
        "app/static/sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/merchant/", "Cache-Control": "no-cache"},
    )


@app.get("/health")
async def health_check():
    """
    Endpoint per il controllo dello stato dell'applicazione.
    Utilizzato per monitoraggio e check di disponibilità.
    Include la versione dell'app (da pyproject.toml).
    """
    return {"status": "ok", "app": "Fidelitree", "version": get_version()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.APP_HOST, port=settings.APP_PORT)
