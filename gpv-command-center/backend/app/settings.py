"""Configuración de la aplicación.

Toda la configuración proviene de variables de entorno (o de un archivo `.env`
ubicado junto al servicio). Las credenciales NUNCA se leen de archivos del
frontend ni del repositorio: sólo de variables de entorno del servidor.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

APP_VERSION = "1.0.0"
BASE_DIR = Path(__file__).resolve().parents[2]  # gpv-command-center/


class AppMode(str, Enum):
    DEMO = "DEMO"
    REAL = "REAL"


def _load_dotenv(path: Path) -> None:
    """Carga mínima de `.env` (KEY=VALUE). No sobrescribe variables existentes."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    mode: AppMode = AppMode.DEMO
    data_dir: Path = BASE_DIR / "var"
    config_dir: Path = BASE_DIR / "config"
    frontend_dir: Path = BASE_DIR / "frontend"
    session_ttl_minutes: int = 480
    cookie_secure: bool = False
    demo_login_enabled: bool = True
    secret_key: str | None = None

    # Conectores (sin credenciales por defecto)
    odata_base_url: str = ""
    odata_auth: str = "basic"  # basic | bearer | ntlm | none
    odata_username: str = ""
    odata_password: str = field(default="", repr=False)
    odata_token: str = field(default="", repr=False)
    odata_mapping_file: str = "odata_mapping.json"
    xtend_base_url: str = ""
    flx_api_base_url: str = ""
    aux_dir: str = ""
    http_timeout_seconds: float = 10.0
    verify_tls: bool = True
    ca_bundle: str = ""

    # Autenticación corporativa vía proxy inverso de confianza (IIS + Windows Auth).
    # Vacío = deshabilitada. El encabezado sólo se acepta desde las IPs listadas.
    proxy_auth_header: str = ""
    proxy_auth_trusted_ips: tuple[str, ...] = ("127.0.0.1", "::1")
    user_roles_file: str = "user_roles.json"

    # Fuente de datos en modo REAL: odata | aux | none
    real_data_source: str = "none"

    # Interruptor maestro de escrituras en producción. En v1.0 no existe ningún
    # ejecutor real registrado, por lo que aunque se active, toda acción real
    # responde NO DISPONIBLE. Se conserva para fases posteriores.
    allow_production_writes: bool = False

    @property
    def is_demo(self) -> bool:
        return self.mode == AppMode.DEMO

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Settings":
        _load_dotenv(env_file or BASE_DIR / ".env")
        mode_raw = os.environ.get("GPV_MODE", "DEMO").strip().upper()
        mode = AppMode.REAL if mode_raw == "REAL" else AppMode.DEMO
        data_dir = Path(os.environ.get("GPV_DATA_DIR") or BASE_DIR / "var")
        config_dir = Path(os.environ.get("GPV_CONFIG_DIR") or BASE_DIR / "config")
        return cls(
            mode=mode,
            data_dir=data_dir,
            config_dir=config_dir,
            session_ttl_minutes=_int("GPV_SESSION_TTL_MIN", 480),
            cookie_secure=_bool("GPV_COOKIE_SECURE", False),
            # El login de demostración sólo puede existir en modo DEMO.
            demo_login_enabled=_bool("GPV_DEMO_LOGIN_ENABLED", True) and mode == AppMode.DEMO,
            secret_key=os.environ.get("GPV_SECRET_KEY") or None,
            odata_base_url=os.environ.get("GPV_ODATA_BASE_URL", "").strip(),
            odata_auth=os.environ.get("GPV_ODATA_AUTH", "basic").strip().lower(),
            odata_username=os.environ.get("GPV_ODATA_USERNAME", ""),
            odata_password=os.environ.get("GPV_ODATA_PASSWORD", ""),
            odata_token=os.environ.get("GPV_ODATA_TOKEN", ""),
            odata_mapping_file=os.environ.get("GPV_ODATA_MAPPING_FILE", "odata_mapping.json"),
            xtend_base_url=os.environ.get("GPV_XTEND_BASE_URL", "").strip(),
            flx_api_base_url=os.environ.get("GPV_FLX_API_BASE_URL", "").strip(),
            aux_dir=os.environ.get("GPV_AUX_DIR", "").strip(),
            http_timeout_seconds=float(os.environ.get("GPV_HTTP_TIMEOUT", "10") or 10),
            verify_tls=_bool("GPV_VERIFY_TLS", True),
            ca_bundle=os.environ.get("GPV_CA_BUNDLE", "").strip(),
            real_data_source=os.environ.get("GPV_REAL_DATA_SOURCE", "none").strip().lower(),
            proxy_auth_header=os.environ.get("GPV_PROXY_AUTH_HEADER", "").strip(),
            proxy_auth_trusted_ips=tuple(x.strip() for x in os.environ.get("GPV_PROXY_AUTH_TRUSTED_IPS", "127.0.0.1,::1").split(",") if x.strip()),
            user_roles_file=os.environ.get("GPV_USER_ROLES_FILE", "user_roles.json"),
            allow_production_writes=_bool("GPV_ALLOW_PRODUCTION_WRITES", False),
        )
