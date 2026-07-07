"""
Punto di ingresso principale dell'applicazione Fidelitree.
Configura l'istanza FastAPI, il database, i middleware e include tutti i router.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlmodel import SQLModel, create_engine

from app.core.config import settings
import asyncio
from app.services.telegram_bot import run_bot

# Import dei router
from mcp_server.server import mcp_app
from app.routes.consumer.views import router as consumer_views_router
from app.routes.consumer.api import router as consumer_api_router
from app.routes.merchant.api import router as merchant_api_router
from app.routes.merchant.auth import router as merchant_auth_router
from app.routes.merchant.views import router as merchant_views_router
from app.routes.merchant.telegram_auth import router as telegram_auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestisce il ciclo di vita dell'applicazione.
    Esegue le migrazioni del database all'avvio e inizializza il bot Telegram.
    """
    # Esegue migrazioni/creazione tabelle
    SQLModel.metadata.create_all(engine)
    
    # Avvia il bot Telegram in background
    bot_task = asyncio.create_task(run_bot())
    
    # Gestisce il lifespan di MCP se presente
    async with mcp_app.lifespan(app):
        yield
    
    # Shutdown (opzionale)
    # Se vuoi cancellare il task del bot alla chiusura:
    # bot_task.cancel()

# --- App ---
app = FastAPI(title="Fidelitree MVP", lifespan=lifespan, redirect_slashes=False)
app.mount("/mcp-app", mcp_app)
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
app.include_router(telegram_auth_router)         # GET /merchant/telegram/...


@app.get("/health")
async def health_check():
    """
    Endpoint per il controllo dello stato dell'applicazione.
    Utilizzato per monitoraggio e check di disponibilità.
    """
    return {"status": "ok", "app": "Fidelitree"}


@app.get("/debug-db")
async def debug_db():
    from sqlmodel import Session, select
    from app.models.models import TreeCard, Merchant
    with Session(engine) as session:
        cards_count = session.exec(select(TreeCard)).all()
        merchants_count = session.exec(select(Merchant)).all()
        return {
            "database_url_configured": settings.DATABASE_URL is not None,
            "cards_in_db": len(cards_count),
            "merchants_in_db": len(merchants_count),
            "engine_url": str(engine.url).split("@")[-1] # Mostra solo l'host per sicurezza
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.APP_HOST, port=settings.APP_PORT)
