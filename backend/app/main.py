"""
FastAPI application entry point.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables, seed if empty, pre-train models."""
    from app.models.db import create_all_tables, SessionLocal, SalesHistory
    create_all_tables()
    logger.info("Database tables created/verified.")

    db = SessionLocal()
    try:
        count = db.query(SalesHistory).count()
        if count == 0:
            logger.info("Database is empty — running seed script...")
            from app.data.seed import save_fixtures, seed_database
            from datetime import datetime
            ref = datetime.now()
            save_fixtures(ref)
            seed_database(ref)
            logger.info("Database seeded successfully.")
        else:
            logger.info(f"Database has {count} sales history records.")
    finally:
        db.close()

    # Pre-train forecasting models in background (non-blocking)
    try:
        from app.services.forecasting import get_forecasting_service
        svc = get_forecasting_service()
        logger.info("Pre-training forecast models (this may take a moment)...")
        svc.train_all()
        logger.info("Forecast models ready.")
    except Exception as e:
        logger.warning(f"Model pre-training failed (non-fatal): {e}")

    yield
    logger.info("Shutting down Production Scheduler API.")


app = FastAPI(
    title="Production Scheduling & Demand Forecasting API",
    description=(
        "Multi-agent system for manufacturing production scheduling. "
        "Combines Prophet demand forecasting with OR-Tools CP-SAT constraint optimization, "
        "orchestrated by a Claude LLM agent."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the React dashboard
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
from app.routers import data, forecast, schedule, agent as agent_router

app.include_router(data.router, prefix="/api", tags=["Data / ERP"])
app.include_router(forecast.router, prefix="/api", tags=["Forecasting"])
app.include_router(schedule.router, prefix="/api", tags=["Schedule"])
app.include_router(agent_router.router, prefix="/api", tags=["Agent"])


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "service": "Production Scheduler", "version": "0.1.0"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
