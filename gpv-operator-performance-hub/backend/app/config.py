"""
Configuración central del backend. Todos los valores sensibles (credenciales de
FactoryLogix, secreto de JWT, etc.) se leen de variables de entorno — nunca se
escriben aquí ni se envían al frontend. Ver `.env.example` para la lista completa.
"""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    # --- General ---
    app_name: str = os.getenv("APP_NAME", "GPV Operator Performance Hub")
    plant_name: str = os.getenv("PLANT_NAME", "Planta Querétaro - GPV")
    environment: str = os.getenv("ENVIRONMENT", "demo")
    timezone: str = os.getenv("APP_TIMEZONE", "America/Mexico_City")

    # --- Base de datos (demo = SQLite; producción = SQL Server vía DATABASE_URL) ---
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./veritas_mx.db")

    # --- Seguridad / sesiones ---
    jwt_secret: str = os.getenv("JWT_SECRET", "CAMBIA-ESTE-VALOR-EN-PRODUCCION")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
    login_max_attempts: int = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
    login_lockout_minutes: int = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))

    # --- CORS ---
    cors_origins: list[str] = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
    ]

    # --- Datos simulados ---
    use_simulated_data: bool = _bool("USE_SIMULATED_DATA", "true")
    seed_random_state: int = int(os.getenv("SEED_RANDOM_STATE", "2026"))

    # --- FactoryLogix OData (opcional; ver MANUAL_FACTORYLOGIX.md) ---
    flx_enabled: bool = _bool("FACTORYLOGIX_ENABLED", "false")
    flx_base_url: str = os.getenv("FACTORYLOGIX_BASE_URL", "")
    flx_username: str = os.getenv("FACTORYLOGIX_USERNAME", "")
    flx_password: str = os.getenv("FACTORYLOGIX_PASSWORD", "")
    flx_timeout_seconds: int = int(os.getenv("FACTORYLOGIX_TIMEOUT_SECONDS", "15"))
    flx_max_retries: int = int(os.getenv("FACTORYLOGIX_MAX_RETRIES", "2"))

    # Nombres de entidad OData configurables (ver README de integraciones).
    flx_entity_production_activity: str = os.getenv("FLX_ENTITY_PRODUCTION_ACTIVITY", "ProductionActivity")
    flx_entity_unit_history: str = os.getenv("FLX_ENTITY_UNIT_HISTORY", "UnitHistory")
    flx_entity_wip: str = os.getenv("FLX_ENTITY_WIP", "WIP")
    flx_entity_active_tracking: str = os.getenv("FLX_ENTITY_ACTIVE_TRACKING", "ActiveProductTracking")
    flx_entity_active_tracking_detail: str = os.getenv(
        "FLX_ENTITY_ACTIVE_TRACKING_DETAIL", "ActiveProductTrackingDetail"
    )
    flx_entity_quality: str = os.getenv("FLX_ENTITY_QUALITY", "Quality")
    flx_entity_faults: str = os.getenv("FLX_ENTITY_FAULTS", "Faults")
    flx_entity_validation_exceptions: str = os.getenv(
        "FLX_ENTITY_VALIDATION_EXCEPTIONS", "ValidationExceptions"
    )
    flx_entity_non_conformance: str = os.getenv("FLX_ENTITY_NON_CONFORMANCE", "NonConformance")
    flx_entity_user_certification: str = os.getenv("FLX_ENTITY_USER_CERTIFICATION", "UserCertification")
    flx_entity_test_measurement: str = os.getenv("FLX_ENTITY_TEST_MEASUREMENT", "TestAndMeasurement")
    flx_entity_work_orders: str = os.getenv("FLX_ENTITY_WORK_ORDERS", "WorkOrders")
    flx_entity_stations: str = os.getenv("FLX_ENTITY_STATIONS", "Stations")
    flx_entity_products: str = os.getenv("FLX_ENTITY_PRODUCTS", "Products")
    flx_entity_users: str = os.getenv("FLX_ENTITY_USERS", "Users")

    # --- Motor de puntaje (pesos por defecto; editables desde Configuración) ---
    score_weight_quality: float = float(os.getenv("SCORE_WEIGHT_QUALITY", "0.35"))
    score_weight_cycle: float = float(os.getenv("SCORE_WEIGHT_CYCLE", "0.25"))
    score_weight_productivity: float = float(os.getenv("SCORE_WEIGHT_PRODUCTIVITY", "0.20"))
    score_weight_consistency: float = float(os.getenv("SCORE_WEIGHT_CONSISTENCY", "0.10"))
    score_weight_rework: float = float(os.getenv("SCORE_WEIGHT_REWORK", "0.10"))
    score_min_units: int = int(os.getenv("SCORE_MIN_UNITS", "20"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
