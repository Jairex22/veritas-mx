"""Estado de sesión de Streamlit, contenedor cacheado y manejo seguro de errores en la interfaz."""
from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from core.errors import CopilotError
from core.logging_setup import get_logger
from core.utils import new_correlation_id
from models.domain import AuthenticatedUser
from security.sanitize import safe_error_message
from services.container import Container, build_container
from ui.i18n import t

log = get_logger("ui")


@st.cache_resource(show_spinner="Iniciando FactoryLogix Knowledge Copilot…")
def get_container() -> Container:
    return build_container()


def container() -> Container:
    return get_container()


def current_user() -> AuthenticatedUser | None:
    return st.session_state.get("user")


def lang() -> str:
    return st.session_state.get("lang", "es")


def tr(key: str) -> str:
    return t(key, lang())


def cid() -> str:
    """Correlation ID por interacción (se renueva en cada ejecución del script)."""
    if "cid" not in st.session_state:
        st.session_state["cid"] = new_correlation_id()
    return st.session_state["cid"]


def require_user() -> AuthenticatedUser:
    user = current_user()
    if user is None:
        st.stop()
    return user


def guard(permission: str) -> AuthenticatedUser:
    user = require_user()
    if not user.can(permission):
        st.error(tr("common.no_permission"))
        st.stop()
    return user


def guard_any(*permissions: str) -> AuthenticatedUser:
    user = require_user()
    if not any(user.can(p) for p in permissions):
        st.error(tr("common.no_permission"))
        st.stop()
    return user


def run_safely(action: Callable[[], Any], success: str | None = None) -> Any:
    """Ejecuta una acción mostrando mensajes seguros (sin trazas, rutas ni secretos)."""
    try:
        result = action()
    except CopilotError as exc:
        st.error(safe_error_message(exc))
        return None
    except Exception as exc:  # noqa: BLE001 - la interfaz nunca debe cerrarse abruptamente
        correlation = cid()
        log.exception("ui action failed cid=%s", correlation)
        try:
            container().errors.record("ui", exc, correlation)
        except Exception:  # noqa: BLE001
            log.error("could not record ui error")
        st.error(f"{safe_error_message(exc)} ID: {correlation}")
        return None
    if success:
        st.success(success)
    return result
