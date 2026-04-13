# app/main.py
# Entry point: crea app, configura DB, include i router

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


# --- App ---
app = FastAPI(title="Fidelitree MVP", lifespan=mcp_app.lifespan, redirect_slashes=False)
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


@app.on_event("startup")
async def on_startup():
    # Per facilitare lo sviluppo in locale anche con Neon Postgres, 
    # creiamo le tabelle se non esistono (questo non sovrascrive dati esistenti).
    # In produzione strutturata sarebbe ideale affidarsi esclusivamente ad Alembic.
    SQLModel.metadata.create_all(engine)
    
    # Avvia il bot Telegram in background
    asyncio.create_task(run_bot())


# --- Router ---
app.include_router(consumer_views_router)        # GET /download_card, GET /card/{id}
app.include_router(consumer_api_router, prefix="/api") # POST /api/get-card
app.include_router(merchant_api_router, prefix="/api") # POST /api/merchant/create
app.include_router(merchant_auth_router)         # POST /merchant/login, GET /merchant/logout
app.include_router(merchant_views_router)        # GET /merchant/... pagine HTML
app.include_router(telegram_auth_router)         # GET /merchant/telegram/...


# --- Health check ---
@app.get("/health")
async def health_check():
    return {"status": "ok", "app": "Fidelitree"}



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.APP_HOST, port=settings.APP_PORT)
