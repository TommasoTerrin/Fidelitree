"""
Punto di ingresso principale dell'applicazione Fidelitree.
Configura l'istanza FastAPI, il database, i middleware e include tutti i router.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlmodel import SQLModel, create_engine

from app.core.config import settings

# Import dei router
from app.routes.consumer.views import router as consumer_views_router
from app.routes.consumer.api import router as consumer_api_router
from app.routes.merchant.api import router as merchant_api_router
from app.routes.merchant.auth import router as merchant_auth_router
from app.routes.merchant.views import router as merchant_views_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestisce il ciclo di vita dell'applicazione.
    Crea le tabelle del database all'avvio se non esistono.
    """
    SQLModel.metadata.create_all(engine)
    yield

# --- App ---
app = FastAPI(title="Fidelitree MVP", lifespan=lifespan, redirect_slashes=False)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# --- Database ---
engine = create_engine(
    url=settings.DATABASE_URL,
    pool_pre_ping=True,  # Fix per timeout SSL con Neon DB
    pool_recycle=300,    # Ricicla connessioni ogni 5 min
    pool_size=5,
    max_overflow=10
)


# --- Router ---
app.include_router(consumer_views_router)        # GET /download_card, GET /card/{id}
app.include_router(consumer_api_router, prefix="/api") # POST /api/get-card
app.include_router(merchant_api_router, prefix="/api") # POST /api/merchant/create
app.include_router(merchant_auth_router)         # POST /merchant/login, GET /merchant/logout
app.include_router(merchant_views_router)        # GET /merchant/... pagine HTML


@app.get("/health")
async def health_check():
    """
    Endpoint per il controllo dello stato dell'applicazione.
    Utilizzato per monitoraggio e check di disponibilità.
    """
    return {"status": "ok", "app": "Fidelitree"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.APP_HOST, port=settings.APP_PORT)
