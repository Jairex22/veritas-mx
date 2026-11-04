"""Configuración de la aplicación.

Orden de precedencia: valores por defecto < config.json < ajustes guardados en
SQLite (solo claves de la lista blanca EDITABLE_KEYS). Las banderas de
seguridad (modo real aprobado, Basic sobre HTTP) solo se pueden cambiar en
config.json, nunca desde la interfaz web.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

APP_VERSION = "1.0.0"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULTS: dict[str, Any] = {
    "app": {
        "name": "GPV SMT Quality Intelligence",
        "site": "GPV Americas E-MXG",
        "display_utc_offset": "-06:00",
    },
    "server": {"host": "127.0.0.1", "port": 8765, "open_browser": True},
    "mode": "demo",
    "odata": {
        "base_url": "http://10.62.54.10:6065/odata/",
        "auth_method": "none",
        "credential_source": "env",
        "credential_target": "GPV_SMT_QI_FactoryLogix",
        "timeout_seconds": 10,
        "max_concurrent_requests": 1,
        "max_retries": 1,
        "backoff_seconds": 2.0,
        "max_response_mb": 20,
        "max_pages": 3,
        "metadata_ttl_minutes": 60,
    },
    "security": {
        "live_mode_approved": False,
        "allow_basic_auth_over_http": False,
    },
    "pulse": {
        "auto_refresh_enabled": False,
        "refresh_interval_seconds": 300,
        "max_events": 500,
        "shifts": [],
    },
    "quality": {"default_window_hours": 24, "max_defects": 500, "max_closetime_lookups": 10},
    "trace": {"max_smt_events": 200, "max_quality_rows": 200, "max_history_rows": 500},
    "rework": {
        "repair_keywords": ["REPAIR", "REWORK", "REPARACION", "REPARACIÓN"],
        "process_flows": {},
        "max_batch_events": 1000,
    },
    "paths": {"database": "database/gpv_sqi.sqlite3", "logs": "logs"},
}

# Claves que la pantalla de Configuración puede modificar (rutas con punto).
EDITABLE_KEYS: dict[str, type] = {
    "mode": str,
    "odata.base_url": str,
    "odata.auth_method": str,
    "odata.credential_source": str,
    "odata.timeout_seconds": float,
    "odata.max_retries": int,
    "odata.backoff_seconds": float,
    "odata.max_concurrent_requests": int,
    "pulse.auto_refresh_enabled": bool,
    "pulse.refresh_interval_seconds": int,
    "pulse.max_events": int,
    "quality.default_window_hours": int,
    "rework.repair_keywords": list,
}

LIMITS = {
    "odata.timeout_seconds": (1, 60),
    "odata.max_retries": (0, 2),
    "odata.backoff_seconds": (0.5, 30),
    "odata.max_concurrent_requests": (1, 2),
    "pulse.refresh_interval_seconds": (300, 3600),
    "pulse.max_events": (10, 1000),
    "quality.default_window_hours": (1, 168),
}
CHOICES = {
    "mode": ("demo", "live"),
    "odata.auth_method": ("none", "basic"),
    "odata.credential_source": ("env", "windows_credential_manager"),
}


class ConfigError(ValueError):
    pass


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if k.startswith("_"):
            continue  # claves de comentario
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def get_path(cfg: dict, dotted: str) -> Any:
    cur: Any = cfg
    for part in dotted.split("."):
        cur = cur[part]
    return cur


def set_path(cfg: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = cfg
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def validate_setting(key: str, value: Any) -> Any:
    if key not in EDITABLE_KEYS:
        raise ConfigError(f"La clave {key} no es editable desde la interfaz")
    kind = EDITABLE_KEYS[key]
    try:
        if kind is bool:
            if not isinstance(value, bool):
                raise ConfigError(f"{key}: se esperaba verdadero/falso")
        elif kind is int:
            if isinstance(value, bool):
                raise ConfigError(f"{key}: se esperaba número")
            value = int(value)
        elif kind is float:
            if isinstance(value, bool):
                raise ConfigError(f"{key}: se esperaba número")
            value = float(value)
        elif kind is str:
            if not isinstance(value, str):
                raise ConfigError(f"{key}: se esperaba texto")
            value = value.strip()
        elif kind is list:
            if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                raise ConfigError(f"{key}: se esperaba lista de textos")
            value = [x.strip() for x in value if x.strip()][:20]
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{key}: valor inválido") from exc
    if key in LIMITS:
        lo, hi = LIMITS[key]
        if not lo <= value <= hi:
            raise ConfigError(f"{key}: debe estar entre {lo} y {hi}")
    if key in CHOICES and value not in CHOICES[key]:
        raise ConfigError(f"{key}: valores permitidos {CHOICES[key]}")
    if key == "odata.base_url":
        if not (value.startswith("http://") or value.startswith("https://")) or len(value) > 300:
            raise ConfigError("La URL base debe iniciar con http:// o https://")
        if any(c in value for c in "?#@ ") :
            raise ConfigError("La URL base no puede contener ?, #, @ ni espacios")
        if not value.endswith("/"):
            value += "/"
    return value


def load_config(path: Path | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    path = path or PROJECT_ROOT / "config.json"
    if path.exists():
        try:
            with path.open("r", encoding="utf-8-sig") as fh:
                user = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"No se pudo leer {path.name}: {exc}") from exc
        if not isinstance(user, dict):
            raise ConfigError(f"{path.name} debe contener un objeto JSON")
        if "password" in json.dumps(user).lower() and _contains_password_value(user):
            raise ConfigError("config.json no debe contener contraseñas. Use variables de "
                              "entorno o el Administrador de credenciales de Windows.")
        cfg = deep_merge(cfg, user)
    return cfg


def _contains_password_value(obj: Any) -> bool:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if "password" in k.lower() and isinstance(v, str) and v:
                return True
            if _contains_password_value(v):
                return True
    elif isinstance(obj, list):
        return any(_contains_password_value(x) for x in obj)
    return False


def apply_overrides(cfg: dict, overrides: dict[str, Any]) -> dict:
    out = copy.deepcopy(cfg)
    for key, value in overrides.items():
        try:
            set_path(out, key, validate_setting(key, value))
        except ConfigError:
            continue  # se ignoran overrides inválidos/obsoletos
    return out


def resolve_path(cfg: dict, key: str) -> Path:
    p = Path(cfg["paths"][key])
    return p if p.is_absolute() else PROJECT_ROOT / p


def public_config(cfg: dict) -> dict:
    """Vista de la configuración segura para la UI (sin secretos)."""
    return {
        "app": cfg["app"],
        "mode": cfg["mode"],
        "odata": {k: cfg["odata"][k] for k in (
            "base_url", "auth_method", "credential_source", "timeout_seconds", "max_retries",
            "backoff_seconds", "max_concurrent_requests")},
        "security": dict(cfg["security"]),
        "pulse": dict(cfg["pulse"]),
        "quality": dict(cfg["quality"]),
        "rework": {"repair_keywords": cfg["rework"]["repair_keywords"],
                   "process_flows_configured": sorted(cfg["rework"]["process_flows"].keys())},
        "editable_keys": sorted(EDITABLE_KEYS),
        "version": APP_VERSION,
    }
