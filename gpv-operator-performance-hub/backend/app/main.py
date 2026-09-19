from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import Base, SessionLocal, engine
from .routers import (
    alerts,
    audit,
    auth,
    comparisons,
    config_routes,
    operators,
    performance,
    plant_summary,
    quality,
    stations,
    system,
    training,
)
from .seed_data import run_seed

logging.basicConfig(level=logging.INFO)
settings = get_settings()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.use_simulated_data:
        db = SessionLocal()
        try:
            run_seed(db)
        finally:
            db.close()
    yield


app = FastAPI(
    title=settings.app_name,
    description="Medición y visualización del rendimiento operativo a partir de datos de FactoryLogix Operations/Analytics.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


app.include_router(auth.router)
app.include_router(system.router)
app.include_router(plant_summary.router)
app.include_router(performance.router)
app.include_router(operators.router)
app.include_router(stations.router)
app.include_router(quality.router)
app.include_router(training.router)
app.include_router(comparisons.router)
app.include_router(alerts.router)
app.include_router(config_routes.router)
app.include_router(audit.router)
