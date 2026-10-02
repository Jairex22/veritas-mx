"""Fixtures compartidas: contenedores aislados en directorios temporales (nunca tocan data/ real)."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import load_settings  # noqa: E402
from models.domain import SYSTEM_USER, AuthenticatedUser  # noqa: E402
from services.container import Container, build_container  # noqa: E402


def make_settings(base: Path, **overrides):
    values = {
        "paths.data_dir": str(base / "data"), "paths.database": str(base / "data" / "test.db"),
        "paths.files_dir": str(base / "files"), "paths.attachments_dir": str(base / "attachments"),
        "paths.reports_dir": str(base / "reports"), "paths.logs_dir": str(base / "logs"),
        "llm.provider": "none", "connectors.odata.enabled": False,
    }
    values.update(overrides)
    return load_settings(overrides=values, environ={})


@pytest.fixture(scope="session")
def demo_container(tmp_path_factory) -> Container:
    """Contenedor con datos DEMO (solo lectura en las pruebas que lo usan)."""
    return build_container(make_settings(tmp_path_factory.mktemp("demo")))


@pytest.fixture()
def container(tmp_path) -> Container:
    """Contenedor DEMO aislado por prueba (para pruebas que modifican estado)."""
    return build_container(make_settings(tmp_path))


@pytest.fixture()
def empty_container(tmp_path) -> Container:
    return build_container(make_settings(tmp_path, **{"demo.load_demo_data": False, "demo.create_demo_users": False}))


def user_for(c: Container, role: str, username: str | None = None) -> AuthenticatedUser:
    """Usuario autenticado sintético con los permisos reales del rol."""
    name = username or f"test_{role.lower().replace(' ', '_')}"
    return replace(SYSTEM_USER, id=f"id-{name}", username=name, display_name=name, role=role,
                   permissions=c.policy.permissions_for(role), clearance=c.policy.clearance_for(role))


def real_user(c: Container, username: str) -> AuthenticatedUser:
    row = c.auth.users.get_by_username(username)
    assert row is not None, username
    return c.auth.build_user(row)


MD_DOC = """# Prueba - Procedimiento de calibración de torque

## Calibración del torquímetro de la estación T1

Palabras clave: torquímetro, calibración, torque

### Respuesta breve
El torquímetro de la estación T1 se calibra cada turno con el patrón certificado.

### Pasos
1. Toma el patrón certificado del gabinete.
2. Aplica tres mediciones y registra los valores.
3. Compara contra la tolerancia de la hoja de ajuste.

### Cuándo escalar
Escala a Calidad si alguna medición sale de tolerancia.
"""
