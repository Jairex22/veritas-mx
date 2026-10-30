"""Contenedor de dependencias de la aplicación."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

import httpx

from .connectors.base import HttpClientFactory
from .connectors.factorylogix import ConnectorRegistry, load_json_config
from .core.db import Database
from .core.security import AuthProviders, SessionStore
from .data.demo import DemoDataSource
from .data.external import AuxCsvDataSource, ODataDataSource, validate_odata_mapping
from .data.source import ProductionDataSource, UnavailableDataSource
from .services.audit import AuditService
from .services.diagnostics import DiagnosticsEngine
from .services.labels import LabelService
from .services.operations import OperationsService
from .settings import Settings


def _load_secret(settings: Settings) -> bytes:
    if settings.secret_key:
        return settings.secret_key.encode()
    path = settings.data_dir / "secret.key"
    if path.is_file():
        return path.read_bytes()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    path.write_bytes(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


class Container:
    def __init__(self, settings: Settings, *, db_path: str | Path | None = None,
                 http_transport: httpx.BaseTransport | None = None, demo_source: DemoDataSource | None = None):
        self.settings = settings
        self.db = Database(db_path or settings.data_dir / "gpv_command_center.db")
        self.audit = AuditService(self.db, settings.mode.value)
        self.sessions = SessionStore(self.db, settings.session_ttl_minutes)
        self.auth = AuthProviders(settings.demo_login_enabled, settings.proxy_auth_header, settings.proxy_auth_trusted_ips,
                                  settings.config_dir / settings.user_roles_file)
        self.http = HttpClientFactory(settings.http_timeout_seconds, settings.verify_tls, settings.ca_bundle, http_transport)
        self.connectors = ConnectorRegistry(settings, self.http)
        self.source_note: str = ""
        self.source = self._select_source(demo_source)
        self.diagnostics = DiagnosticsEngine()
        self.secret = _load_secret(settings)
        self.operations = OperationsService(settings, self.db, self.audit, self.source, self.secret)
        self.labels = LabelService(settings, self.db, self.audit)

    def _select_source(self, demo_source: DemoDataSource | None) -> ProductionDataSource:
        s = self.settings
        if s.is_demo:
            return demo_source or DemoDataSource()
        if s.real_data_source == "odata":
            if not s.odata_base_url:
                return UnavailableDataSource("Modo REAL con fuente OData, pero GPV_ODATA_BASE_URL no está configurada.")
            mapping = load_json_config(s.config_dir, s.odata_mapping_file)
            errors = validate_odata_mapping(mapping)
            if errors:
                self.source_note = " ".join(errors)
                return UnavailableDataSource(
                    f"Mapeo OData no válido ({s.config_dir / s.odata_mapping_file}): " + " ".join(errors))
            return ODataDataSource(self.connectors.odata, mapping)
        if s.real_data_source == "aux":
            if not s.aux_dir:
                return UnavailableDataSource("Modo REAL con fuente auxiliar, pero GPV_AUX_DIR no está configurado.")
            return AuxCsvDataSource(Path(s.aux_dir))
        return UnavailableDataSource(
            "Modo REAL sin fuente de datos configurada (GPV_REAL_DATA_SOURCE=odata|aux). "
            "No se muestran datos sintéticos en modo REAL.")
