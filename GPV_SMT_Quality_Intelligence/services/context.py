"""Contexto de aplicación: configuración vigente, fuente de datos y repositorios."""
from __future__ import annotations

import logging
import threading

from backend.config import apply_overrides, load_config, resolve_path
from database.db import Database
from repositories.audit_repository import AuditRepository
from repositories.cache_repository import CacheRepository
from repositories.settings_repository import SettingsRepository
from services.demo_source import DemoDataSource
from services.odata_client import FactoryLogixODataClient

log = logging.getLogger("gpv.context")


class AppContext:
    def __init__(self, base_config: dict | None = None, db: Database | None = None, demo_source=None,
                 live_client_factory=None):
        self.base_config = base_config or load_config()
        self.db = db or Database(resolve_path(self.base_config, "database"))
        self.audit = AuditRepository(self.db)
        self.cache = CacheRepository(self.db)
        self.settings = SettingsRepository(self.db)
        self._demo = demo_source or DemoDataSource()
        self._live_factory = live_client_factory or (
            lambda cfg: FactoryLogixODataClient(cfg, on_result=self.audit.record_query))
        self._lock = threading.Lock()
        self.reload()

    def reload(self) -> None:
        with self._lock:
            self.config = apply_overrides(self.base_config, self.settings.all())
            if self.config["mode"] == "live":
                self.source = self._live_factory(self.config)
            else:
                self.source = self._demo
            log.info("Modo activo: %s", self.config["mode"])

    @property
    def data_source(self) -> str:
        return "live" if self.config["mode"] == "live" else "demo"

    def execute(self, spec):
        """Ejecuta una consulta y registra auditoría para la fuente demo
        (el cliente real la registra por callback)."""
        result = self.source.execute(spec)
        if self.data_source == "demo":
            log.info("ODATA-DEMO | %s | %s | HTTP=%s | %.0f ms | filas=%s | %s | %s", result.entity,
                     result.status.value, result.http_status, result.elapsed_ms, len(result.rows),
                     result.query_description, result.error or "")
            self.audit.record_query(result)
        return result
