"""Carga de configuración: YAML + .env + variables de entorno FLKC_*.

Los secretos solo se leen desde el entorno (o un archivo .env local que no se distribuye).
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"

# Variables de entorno que sobrescriben claves de settings.yaml (clave puntuada -> tipo)
_ENV_OVERRIDES: dict[str, tuple[str, type]] = {
    "FLKC_ENVIRONMENT": ("app.environment", str),
    "FLKC_DEFAULT_LANGUAGE": ("app.default_language", str),
    "FLKC_BIND": ("server.bind", str),
    "FLKC_PORT": ("server.preferred_port", int),
    "FLKC_DATABASE": ("paths.database", str),
    "FLKC_DATA_DIR": ("paths.data_dir", str),
    "FLKC_FILES_DIR": ("paths.files_dir", str),
    "FLKC_ATTACHMENTS_DIR": ("paths.attachments_dir", str),
    "FLKC_REPORTS_DIR": ("paths.reports_dir", str),
    "FLKC_LOGS_DIR": ("paths.logs_dir", str),
    "FLKC_LLM_PROVIDER": ("llm.provider", str),
    "FLKC_LLM_BASE_URL": ("llm.base_url", str),
    "FLKC_LLM_MODEL": ("llm.model", str),
    "FLKC_EMBEDDING_PROVIDER": ("rag.embedding_provider", str),
    "FLKC_ODATA_ENABLED": ("connectors.odata.enabled", bool),
    "FLKC_ODATA_BASE_URL": ("connectors.odata.base_url", str),
    "FLKC_SENTIMENT_ENABLED": ("sentiment.enabled", bool),
    "FLKC_LOAD_DEMO": ("demo.load_demo_data", bool),
    "FLKC_CREATE_DEMO_USERS": ("demo.create_demo_users", bool),
}

# Secretos: nunca se escriben en YAML ni en la base de datos.
SECRET_ENV_KEYS = ("FLKC_ODATA_USERNAME", "FLKC_ODATA_PASSWORD", "FLKC_ODATA_TOKEN",
                   "FLKC_SMTP_USERNAME", "FLKC_SMTP_PASSWORD", "FLKC_AD_BIND_PASSWORD")


def _parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def load_dotenv(path: Path) -> dict[str, str]:
    """Parser mínimo de .env (KEY=VALUE). No ejecuta nada ni expande variables."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key.replace("_", "").isalnum():
            values[key] = value
    return values


def _set_dotted(data: dict[str, Any], dotted: str, value: Any) -> None:
    node = data
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _get_dotted(data: dict[str, Any], dotted: str, default: Any = None) -> Any:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


@dataclass
class Settings:
    """Configuración efectiva de la aplicación."""

    data: dict[str, Any]
    root: Path = PROJECT_ROOT
    secrets: dict[str, str] = field(default_factory=dict, repr=False)
    rules: dict[str, Any] = field(default_factory=dict)

    def get(self, dotted: str, default: Any = None) -> Any:
        return _get_dotted(self.data, dotted, default)

    def set(self, dotted: str, value: Any) -> None:
        _set_dotted(self.data, dotted, value)

    def path(self, dotted: str) -> Path:
        """Resuelve una ruta de configuración relativa a la raíz del proyecto."""
        raw = self.get(dotted)
        if not raw:
            raise KeyError(dotted)
        candidate = Path(str(raw))
        return candidate if candidate.is_absolute() else (self.root / candidate)

    def secret(self, key: str) -> str | None:
        return self.secrets.get(key) or None

    def copy(self) -> "Settings":
        return Settings(copy.deepcopy(self.data), self.root, dict(self.secrets), copy.deepcopy(self.rules))

    def ensure_dirs(self) -> None:
        for key in ("paths.data_dir", "paths.files_dir", "paths.attachments_dir", "paths.reports_dir", "paths.logs_dir"):
            self.path(key).mkdir(parents=True, exist_ok=True)
        self.path("paths.database").parent.mkdir(parents=True, exist_ok=True)


def load_settings(root: Path | None = None, overrides: dict[str, Any] | None = None,
                  environ: dict[str, str] | None = None) -> Settings:
    root = root or PROJECT_ROOT
    with open(root / "config" / "settings.yaml", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    rules_path = root / "config" / "rules.yaml"
    rules: dict[str, Any] = {}
    if rules_path.is_file():
        with open(rules_path, encoding="utf-8") as fh:
            rules = yaml.safe_load(fh) or {}

    env: dict[str, str] = {}
    env.update(load_dotenv(root / ".env"))
    env.update(environ if environ is not None else dict(os.environ))

    for env_key, (dotted, kind) in _ENV_OVERRIDES.items():
        if env_key in env and env[env_key] != "":
            raw = env[env_key]
            try:
                value: Any = _parse_bool(raw) if kind is bool else kind(raw)
            except ValueError:
                continue
            _set_dotted(data, dotted, value)

    for dotted, value in (overrides or {}).items():
        _set_dotted(data, dotted, value)

    secrets = {k: env[k] for k in SECRET_ENV_KEYS if env.get(k)}
    return Settings(data=data, root=root, secrets=secrets, rules=rules)
