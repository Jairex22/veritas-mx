"""Centralized configuration loading and validation.

All tunable values live in ``config.json``. This module merges the file with
safe defaults, validates ranges and exposes typed dataclasses so the rest of
the application never reads raw dictionaries.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

APP_NAME = "GPV SMT Production Pulse"
APP_VERSION = "1.1.4"
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.json"
ALLOWED_ENTITY_SET = "ProductivityOverTime"
FIELD_ROLES = ("timestamp", "quantity", "line", "station", "shift", "project", "work_order", "product")
# Descriptive dimensions shown when a confirmed field exists (never filtered against OData).
DIMENSION_ROLES = ("line", "station", "shift", "project", "work_order", "product")

logger = logging.getLogger("pulse.settings")


class ConfigError(ValueError):
    """Raised when config.json contains invalid or unsafe values."""


@dataclass(frozen=True)
class Limits:
    """Query and protection limits. Initial safety limits, not performance guarantees."""

    MAX_RECORDS: int = 50
    CACHE_TTL_SECONDS: int = 300
    REQUEST_TIMEOUT_SECONDS: int = 15
    MAX_CONCURRENT_REQUESTS: int = 1
    MIN_REFRESH_INTERVAL_SECONDS: int = 60
    AUTO_REFRESH_ENABLED: bool = False
    AUTO_REFRESH_INTERVAL_SECONDS: int = 300
    MAX_RESPONSE_BYTES: int = 2_000_000
    MAX_METADATA_BYTES: int = 10_000_000
    MAX_QUERY_RANGE_DAYS: int = 31
    MIN_SECONDS_BETWEEN_ODATA_REQUESTS: int = 5
    MAX_ODATA_REQUESTS_PER_SESSION_PER_HOUR: int = 30
    MAX_ODATA_REQUESTS_PER_HOUR_GLOBAL: int = 120
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    CIRCUIT_BREAKER_COOLDOWN_SECONDS: int = 300
    MIN_METADATA_CHECK_INTERVAL_SECONDS: int = 60
    MIN_PROBE_INTERVAL_SECONDS: int = 600
    PROBE_DELAY_SECONDS: int = 1


# (min, max) accepted for each numeric limit. Values outside are rejected.
_LIMIT_RANGES: dict[str, tuple[int, int]] = {
    "MAX_RECORDS": (1, 1000),
    "CACHE_TTL_SECONDS": (0, 86_400),
    "REQUEST_TIMEOUT_SECONDS": (1, 120),
    "MAX_CONCURRENT_REQUESTS": (1, 1),
    "MIN_REFRESH_INTERVAL_SECONDS": (10, 86_400),
    "AUTO_REFRESH_INTERVAL_SECONDS": (60, 86_400),
    "MAX_RESPONSE_BYTES": (10_000, 50_000_000),
    "MAX_METADATA_BYTES": (10_000, 100_000_000),
    "MAX_QUERY_RANGE_DAYS": (1, 366),
    "MIN_SECONDS_BETWEEN_ODATA_REQUESTS": (0, 3600),
    "MAX_ODATA_REQUESTS_PER_SESSION_PER_HOUR": (1, 1000),
    "MAX_ODATA_REQUESTS_PER_HOUR_GLOBAL": (1, 5000),
    "CIRCUIT_BREAKER_FAILURE_THRESHOLD": (1, 50),
    "CIRCUIT_BREAKER_COOLDOWN_SECONDS": (10, 86_400),
    "MIN_METADATA_CHECK_INTERVAL_SECONDS": (0, 86_400),
    "MIN_PROBE_INTERVAL_SECONDS": (0, 86_400),
    "PROBE_DELAY_SECONDS": (0, 60),
}


@dataclass(frozen=True)
class Retention:
    """Local data retention policy."""

    CACHE_RETENTION_DAYS: int = 7
    HISTORY_RETENTION_DAYS: int = 30
    REPORT_RETENTION_DAYS: int = 90
    MAX_DB_SIZE_MB: int = 200


@dataclass(frozen=True)
class ODataSettings:
    """Connection settings for the FactoryLogix OData service."""

    base_url: str = "http://10.62.54.10:6065/odata/"
    entity_set: str = ALLOWED_ENTITY_SET
    use_system_proxy: bool = False
    auth_mode: str = "auto"  # "auto" | "sspi" | "none"
    accept_header: str = "application/json"
    append_format_json: bool = False


@dataclass(frozen=True)
class AnalyticsSettings:
    """Presentation and heuristic parameters for analytics."""

    quantity_unit_label: str = ""
    drop_threshold_percent: float = 25.0
    min_buckets_for_drop_detection: int = 4
    plant_timezone: str = ""


@dataclass(frozen=True)
class CollectorSettings:
    """Centralized background collector (one OData query per cycle)."""

    enabled: bool = True
    interval_seconds: int = 300
    initial_backfill_hours: int = 8
    lookback_minutes: int = 15
    max_backoff_seconds: int = 3600
    recent_activity_minutes: int = 30
    quantity_semantics: str = "auto"  # auto | interval | cumulative
    auto_apply_detected_mapping: bool = True
    probe_recheck_hours: int = 24
    record_retention_days: int = 30
    dashboard_poll_seconds: int = 30


_COLLECTOR_RANGES: dict[str, tuple[int, int]] = {
    "interval_seconds": (300, 3600),
    "initial_backfill_hours": (1, 72),
    "lookback_minutes": (0, 240),
    "max_backoff_seconds": (300, 86_400),
    "recent_activity_minutes": (5, 1440),
    "probe_recheck_hours": (1, 720),
    "record_retention_days": (1, 365),
    "dashboard_poll_seconds": (10, 300),
}


@dataclass(frozen=True)
class AppSettings:
    """Local web server settings."""

    mode: str = "demo"  # "demo" | "live"
    host: str = "127.0.0.1"
    port: int = 8765
    allow_non_localhost: bool = False
    open_browser: bool = False


@dataclass(frozen=True)
class Config:
    """Full validated application configuration."""

    app: AppSettings
    odata: ODataSettings
    limits: Limits
    retention: Retention
    analytics: AnalyticsSettings
    collector: CollectorSettings = field(default_factory=CollectorSettings)
    field_mapping: dict[str, str | None] = field(default_factory=dict)
    base_dir: Path = BASE_DIR

    @property
    def is_demo(self) -> bool:
        return self.app.mode == "demo"

    @property
    def data_dir(self) -> Path:
        return self.base_dir / "data"

    @property
    def logs_dir(self) -> Path:
        return self.base_dir / "logs"

    @property
    def database_path(self) -> Path:
        name = "production_pulse_demo.db" if self.is_demo else "production_pulse.db"
        return self.data_dir / name

    @property
    def metadata_dir(self) -> Path:
        return self.data_dir / ("metadata_demo" if self.is_demo else "metadata")

    def public_limits(self) -> dict[str, Any]:
        """Limits safe to expose to the browser."""
        return dict(self.limits.__dict__)


def _coerce_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"El parámetro {name} debe ser numérico.")
    if isinstance(value, float) and not value.is_integer():
        raise ConfigError(f"El parámetro {name} debe ser un entero.")
    return int(value)


def _build_limits(raw: dict[str, Any]) -> Limits:
    values: dict[str, Any] = {}
    defaults = Limits()
    for key in Limits.__dataclass_fields__:
        if key not in raw:
            values[key] = getattr(defaults, key)
            continue
        if key == "AUTO_REFRESH_ENABLED":
            if not isinstance(raw[key], bool):
                raise ConfigError("AUTO_REFRESH_ENABLED debe ser true o false.")
            values[key] = raw[key]
            continue
        number = _coerce_int(key, raw[key])
        low, high = _LIMIT_RANGES[key]
        if not low <= number <= high:
            raise ConfigError(f"El parámetro {key}={number} está fuera del rango permitido [{low}, {high}].")
        values[key] = number
    unknown = set(raw) - set(Limits.__dataclass_fields__)
    if unknown:
        raise ConfigError(f"Parámetros de límites desconocidos: {sorted(unknown)}")
    return Limits(**values)


def _build_section(cls: type, raw: dict[str, Any], section: str) -> Any:
    unknown = set(raw) - set(cls.__dataclass_fields__)
    if unknown:
        raise ConfigError(f"Parámetros desconocidos en '{section}': {sorted(unknown)}")
    defaults = cls()
    values = {}
    for key, fdef in cls.__dataclass_fields__.items():
        value = raw.get(key, getattr(defaults, key))
        expected = type(getattr(defaults, key))
        if expected is float and isinstance(value, int) and not isinstance(value, bool):
            value = float(value)
        if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            raise ConfigError(f"El parámetro {section}.{key} tiene un tipo inválido.")
        values[key] = value
    return cls(**values)


def _validate_odata(odata: ODataSettings) -> None:
    parsed = urlparse(odata.base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ConfigError("odata.base_url debe ser una URL http(s) válida.")
    if not odata.base_url.endswith("/"):
        raise ConfigError("odata.base_url debe terminar con '/'.")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ConfigError("odata.base_url no debe incluir parámetros, fragmentos ni credenciales.")
    if odata.entity_set != ALLOWED_ENTITY_SET:
        raise ConfigError(f"Solo está autorizada la entidad {ALLOWED_ENTITY_SET}.")


def load_config(path: Path | None = None, overrides: dict[str, Any] | None = None,
                base_dir: Path | None = None) -> Config:
    """Load, merge and validate configuration.

    Args:
        path: path to a JSON file; defaults to ``config.json`` next to this module.
        overrides: nested dict applied on top of the file (used by CLI flags and tests).
        base_dir: directory containing ``data/`` and ``logs/``.
    """
    cfg_path = path or DEFAULT_CONFIG_PATH
    raw: dict[str, Any] = {}
    if cfg_path.exists():
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"config.json no es JSON válido: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("config.json debe contener un objeto JSON.")
    for section, values in (overrides or {}).items():
        if isinstance(values, dict):
            raw.setdefault(section, {}).update(values)
        else:
            raw[section] = values

    app = _build_section(AppSettings, raw.get("app", {}), "app")
    if app.mode not in ("demo", "live"):
        raise ConfigError("app.mode debe ser 'demo' o 'live'.")
    if not 1024 <= app.port <= 65535:
        raise ConfigError("app.port debe estar entre 1024 y 65535.")
    if app.host not in ("127.0.0.1", "localhost") and not app.allow_non_localhost:
        raise ConfigError(
            "Por seguridad la aplicación solo escucha en 127.0.0.1. Para exponerla en red se requiere "
            "autorización de TI y app.allow_non_localhost=true."
        )
    odata = _build_section(ODataSettings, raw.get("odata", {}), "odata")
    _validate_odata(odata)
    if odata.auth_mode not in ("auto", "sspi", "none"):
        raise ConfigError("odata.auth_mode debe ser 'auto', 'sspi' o 'none'.")
    limits = _build_limits(raw.get("limits", {}))
    retention = _build_section(Retention, raw.get("retention", {}), "retention")
    analytics = _build_section(AnalyticsSettings, raw.get("analytics", {}), "analytics")

    collector = _build_section(CollectorSettings, raw.get("collector", {}), "collector")
    for key, (low, high) in _COLLECTOR_RANGES.items():
        value = getattr(collector, key)
        if not low <= value <= high:
            raise ConfigError(f"collector.{key}={value} está fuera del rango permitido [{low}, {high}].")
    if collector.quantity_semantics not in ("auto", "interval", "cumulative"):
        raise ConfigError("collector.quantity_semantics debe ser 'auto', 'interval' o 'cumulative'.")

    mapping_raw = raw.get("field_mapping", {}) or {}
    if not isinstance(mapping_raw, dict):
        raise ConfigError("field_mapping debe ser un objeto.")
    mapping: dict[str, str | None] = {}
    for role in FIELD_ROLES:
        value = mapping_raw.get(role)
        if value is not None and not isinstance(value, str):
            raise ConfigError(f"field_mapping.{role} debe ser texto o null.")
        mapping[role] = value or None

    return Config(app=app, odata=odata, limits=limits, retention=retention,
                  analytics=analytics, collector=collector, field_mapping=mapping, base_dir=base_dir or BASE_DIR)
